#!/usr/bin/env python3
"""Reliable multi-drone offboard flight primitive for the partitioned SITL fleet.

The sverk offboard_control ROS2 node's arming handshake does not scale to 4
vehicles under one container's DDS load (arming-confirmation timeouts). PX4
OFFBOARD via MAVLink, however, is rock-solid for every instance. This module
drives each drone directly: one control thread per vehicle streams position
setpoints at 20 Hz, arms, switches to OFFBOARD once, and then just follows a
mutable target (x, y, z, yaw) in the vehicle's local NED frame.

Ports: instance i -> udp:127.0.0.1:(14540+i)  (PX4 SITL onboard MAVLink).
Frame: setpoints are local NED relative to each drone's EKF origin (its spawn).
Since every drone lives in its own gz partition at spawn (0,0), local NED == the
shared survey field frame, so field cell (fx, fy) maps directly to a setpoint.

Run inside the sverk_sitl container. Used by the openclaw survey bridge, and
standalone-testable:  python3 fleet_flight.py selftest 4
"""
from __future__ import annotations
import sys, time, threading, math
from pymavlink import mavutil

TAKEOFF_Z = 3.0          # metres above spawn (survey altitude)
REACH_TOL = 0.35         # metres: consider a target reached within this radius
STREAM_HZ = 20.0


class Drone:
    def __init__(self, inst: int):
        self.inst = inst
        self.port = 14540 + inst
        self.m = mavutil.mavlink_connection(f"udp:127.0.0.1:{self.port}")
        self.tx = 0.0
        self.ty = 0.0
        self.tz = -TAKEOFF_Z       # NED down-negative == up
        self.tyaw = 0.0
        self.pos = (0.0, 0.0, 0.0)  # current local NED
        self._z0 = 0.0
        self._run = False
        self._armed_ok = False
        self._thread = None
        self.flying = False    # start LANDED; takeoff() lifts it
        self.paused = False    # battery-swap freeze

    def connect(self, timeout=20) -> bool:
        if not self.m.wait_heartbeat(timeout=timeout):
            return False
        self.m.mav.request_data_stream_send(
            self.m.target_system, self.m.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL, 15, 1)
        return True

    def _send_sp(self):
        # proven position-only mask: ignore vel/acc/yaw/yaw_rate, use x,y,z
        mask = 0b0000_111_111_111_000
        self.m.mav.set_position_target_local_ned_send(
            0, self.m.target_system, self.m.target_component,
            mavutil.mavlink.MAV_FRAME_LOCAL_NED, mask,
            self.tx, self.ty, self.tz, 0, 0, 0, 0, 0, 0, 0, 0)

    def _cmd(self, c, *p):
        p = list(p) + [0] * (7 - len(p))
        self.m.mav.command_long_send(self.m.target_system, self.m.target_component, c, 0, *p)

    def _loop(self):
        # Drones start LANDED and only take off when told (takeoff()). Streaming
        # OFFBOARD setpoints + arming happens only while `flying`; landing stops
        # the stream and lets PX4's NAV_LAND settle. `paused` = battery-swap hold.
        primed = False
        last_arm_retry = 0.0
        while self._run:
            msg = self.m.recv_match(type=["LOCAL_POSITION_NED", "HEARTBEAT"], blocking=False)
            if msg:
                t = msg.get_type()
                if t == "LOCAL_POSITION_NED":
                    self.pos = (msg.x, msg.y, msg.z)
                elif t == "HEARTBEAT":
                    self._armed_ok = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            if self.flying and not self.paused:
                if not primed:                       # (re)take off: prime then arm
                    for _ in range(20):
                        self._send_sp(); time.sleep(1.0 / STREAM_HZ)
                    self._cmd(mavutil.mavlink.MAV_CMD_DO_SET_MODE,
                              mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 6, 0)
                    self._cmd(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
                    primed = True; last_arm_retry = time.time()
                self._send_sp()
                if not self._armed_ok and time.time() - last_arm_retry > 2.0:
                    self._cmd(mavutil.mavlink.MAV_CMD_DO_SET_MODE,
                              mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 6, 0)
                    self._cmd(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
                    last_arm_retry = time.time()
            else:
                primed = False                        # so the next takeoff re-primes
            time.sleep(1.0 / STREAM_HZ)

    def start(self):
        self._run = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def takeoff(self, z=None):
        """Arm + climb to survey altitude from the current ground position."""
        self.tx, self.ty = self.pos[0], self.pos[1]
        self.tz = -abs(z if z is not None else TAKEOFF_Z)
        self.paused = False
        self.flying = True

    def airborne(self) -> bool:
        return self.rel_alt() > 0.6

    def goto(self, x, y, z=TAKEOFF_Z, yaw=None):
        self.tx, self.ty, self.tz = x, y, -abs(z)
        if yaw is not None:
            self.tyaw = yaw

    def reached(self) -> bool:
        dx = self.pos[0] - self.tx
        dy = self.pos[1] - self.ty
        dz = self.pos[2] - self.tz
        return math.sqrt(dx*dx + dy*dy + dz*dz) < REACH_TOL

    def rel_alt(self) -> float:
        return -self.pos[2]

    def land(self):
        """Land at the current x,y and stay down (stops offboard so NAV_LAND
        completes + disarms)."""
        self.flying = False
        self._cmd(mavutil.mavlink.MAV_CMD_NAV_LAND, 0, 0, 0, float("nan"), 0, 0, 0)

    def pause(self):
        """Battery-swap: land + freeze (no re-arm) until resume()."""
        self.paused = True
        self._cmd(mavutil.mavlink.MAV_CMD_NAV_LAND, 0, 0, 0, float("nan"), 0, 0, 0)

    def resume(self):
        self.takeoff()

    def stop(self):
        self._run = False


class Fleet:
    def __init__(self, n: int):
        self.drones = [Drone(i) for i in range(n)]

    def connect_all(self):
        for d in self.drones:
            ok = d.connect()
            print(f"drone {d.inst} (port {d.port}) connect: {'OK' if ok else 'FAIL'}", flush=True)

    def start_all(self):
        for d in self.drones:
            d.start()

    def wait_reached(self, timeout=30) -> bool:
        t0 = time.time()
        while time.time() - t0 < timeout:
            if all(d.reached() for d in self.drones):
                return True
            time.sleep(0.5)
        return False


def selftest(n: int):
    fleet = Fleet(n)
    fleet.connect_all()
    fleet.start_all()
    # spread targets to distinct cells (each in own world, same coords ok)
    cells = [(1.0, 1.0), (-1.0, 1.0), (1.0, -1.0), (-1.0, -1.0)]
    print("taking off + flying to cells...", flush=True)
    for i, d in enumerate(fleet.drones):
        d.goto(*cells[i % len(cells)], z=TAKEOFF_Z)
    for s in range(20):
        time.sleep(2)
        line = "  ".join(f"d{d.inst}:({d.pos[0]:.1f},{d.pos[1]:.1f},{d.rel_alt():.1f}){'R' if d.reached() else ''}"
                          for d in fleet.drones)
        print(f"[{s*2:>3}s] {line}", flush=True)
        if all(d.reached() for d in fleet.drones):
            print("ALL REACHED", flush=True); break
    print("holding 5s then landing", flush=True)
    time.sleep(5)
    for d in fleet.drones:
        d.land()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    if cmd == "selftest":
        selftest(n)
