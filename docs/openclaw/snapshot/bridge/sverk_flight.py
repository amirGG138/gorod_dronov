#!/usr/bin/env python3
"""Flight primitive that drives the REAL sverk offboard stack via sverk_interfaces.

Drop-in replacement for fleet_flight.Drone (same method/attribute surface), but
instead of talking MAVLink to PX4 directly it calls the sverk `offboard_control`
ROS2 node's services (Navigate / Land / GetTelemetry) through the `sverk_interfaces`
facade. This is the "работает через sverk interfaces" path: every command a survey
drone issues goes offboard_control -> uXRCE-DDS -> PX4, exactly as on hardware.

Per-drone isolation: instance i talks to the namespaced node /px4_i (offboard_
namespace="/px4_{i}"). In the 4-container topology each bridge container runs one
offboard_control (/px4_i) + one of these; they share the single gz world's DDS
graph (one MicroXRCEAgent) but each drone is a separate process/participant.

FRAMES. offboard_control's `map` frame is ENU (x=East, y=North, z=Up); it is the
PX4 local origin (each drone's spawn) and offboard_control publishes map->base_link
from the EKF, so no aruco localization is required to fly (aruco is a separate
reality-check, see real_bridge). To keep real_bridge's NED cell math unchanged we
present the SAME local-NED interface as fleet_flight.Drone:

    fleet NED (north, east, down)  <->  sverk map ENU (east, north, up)
    pos_ned = (map.y, map.x, -map.z)
    goto(north, east, up) -> navigate(x=east, y=north, z=up, frame_id="map")

HOLD. offboard_control's setpoint timer is the only setpoint publisher; with the
launch param auto_release:=false it streams the last target forever, giving true
position hold between cell hops (same effect as fleet_flight's 20 Hz stream). Launch
the offboard nodes with auto_release:=false (see scripts/sverk_bridges.sh); if it is
left true the node releases on arrival and the drone sinks — SverkDrone re-issues the
hold target on reached() as a best-effort guard, but auto_release:=false is correct.
"""
from __future__ import annotations
import math
import os
import threading
import time

TAKEOFF_Z = float(os.environ.get("TAKEOFF_Z_M", "1.5"))  # metres above spawn (up)
REACH_TOL = float(os.environ.get("REACH_TOL_M", "0.35"))
NAV_SPEED = float(os.environ.get("NAV_SPEED_MS", "1.2"))
FRAME = os.environ.get("SVERK_FRAME", "map")             # рабочий кадр полёта
# Взлёт РЕАЛЬНОГО дрона (лётный рецепт): подъём по body — относительный, работает
# когда aruco-маркеры с земли НЕ видны; на высоте перехват в рабочий кадр
# (aruco_map). В SITL оба кадра = map, поведение прежнее.
TAKEOFF_FRAME = os.environ.get("TAKEOFF_FRAME", FRAME)
FRAME_WAIT_SEC = float(os.environ.get("FRAME_WAIT_SEC", "8"))  # ждать aruco после взлёта
POS_TTL = 0.2   # s: телеметрию не дёргаем чаще (сервис-вызов крутит ноду)
KEEPALIVE_SEC = float(os.environ.get("KEEPALIVE_SEC", "4"))  # idle OFFBOARD warm-up


class Drone:
    """sverk_interfaces-backed drone with the fleet_flight.Drone interface."""

    def __init__(self, inst: int):
        self.inst = int(inst)
        self.ns = os.environ.get("OFFBOARD_NS", f"/px4_{self.inst}")
        self.port = 14540 + self.inst   # informational parity with fleet_flight
        # target in local NED (north, east, up) — real_bridge mutates tx/ty directly
        self.tx = 0.0
        self.ty = 0.0
        self.tz = TAKEOFF_Z
        self.tyaw = 0.0
        self._pos = (0.0, 0.0, 0.0)     # cached local NED (north, east, down)
        self._pos_ts = 0.0
        self.flying = False             # start LANDED; takeoff() lifts it
        self.paused = False
        self._d = None                  # sverk_interfaces facade
        self._lock = threading.Lock()   # facade spins the node per call — serialize
        self._run = False               # keep-alive thread flag

    # ---- lifecycle ----------------------------------------------------------
    def connect(self, timeout=25) -> bool:
        import sverk_interfaces
        name = f"openclaw_flight_px4_{self.inst}"
        self._d = sverk_interfaces.init(
            Nodename=name,
            offboard_namespace=self.ns,
            fcu_namespace=f"{self.ns}/fmu_control",
        )
        # ждём, пока offboard_control поднимет сервис и даст конечную телеметрию.
        # На реальном борте на земле aruco_map пуст (маркеры не видны) — связь
        # подтверждаем телеметрией map (EKF, есть всегда); рабочий кадр борт
        # поймает после body-взлёта (_anchor_frame).
        deadline = time.time() + timeout
        while time.time() < deadline:
            t = self._telemetry(timeout=2.0)
            if t is not None:
                self._store_pos(t)
                return True
            if TAKEOFF_FRAME != FRAME:
                try:
                    with self._lock:
                        tm = self._d.control.get_telemetry(frame_id="map", timeout=2.0)
                    if tm is not None and math.isfinite(float(tm.z)):
                        return True
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(0.5)
        return False

    def start(self):
        """Start the keep-alive: between survey commands a drone sits idle, and if
        OFFBOARD gets no fresh setpoint it drops to AUTO.LOITER and disarms (seen on
        3/4 drones mid-run). Every few seconds, ONLY while parked at the target
        (reached), re-issue the hold navigate to keep OFFBOARD warm. Crucially it
        does NOT fire during an active approach — re-navigating mid-flight re-inits
        the C++ trajectory and the drone never translates (the earlier bug)."""
        self._run = True
        threading.Thread(target=self._keepalive, daemon=True).start()

    def _keepalive(self):
        # Recover OFFBOARD dropout: between/after survey commands a drone can fall
        # out of OFFBOARD to AUTO.LOITER and disarm (seen on drones 2-4 under the
        # shared-agent DDS load). Poll armed/mode; re-issue navigate(auto_arm=True)
        # to the CURRENT target ONLY when actually dropped — during a normal
        # approach the drone is armed+OFFBOARD, so this never fires mid-flight and
        # cannot cause the trajectory-reset stall.
        while self._run:
            time.sleep(KEEPALIVE_SEC)
            if not (self.flying and not self.paused):
                continue
            try:
                with self._lock:
                    t = self._d.control.get_telemetry(frame_id=FRAME, timeout=2.0)
                armed = bool(getattr(t, "armed", True))
                mode = str(getattr(t, "mode", "OFFBOARD"))
                if not armed or mode != "OFFBOARD":
                    self._navigate(self.tx, self.ty, self.tz, auto_arm=True)
            except Exception:  # noqa: BLE001
                pass

    def stop(self):
        self._run = False
        try:
            if self._d is not None:
                self._d.close()
        except Exception:  # noqa: BLE001
            pass

    # ---- telemetry ----------------------------------------------------------
    def _telemetry(self, timeout=2.0):
        try:
            with self._lock:
                t = self._d.control.get_telemetry(frame_id=FRAME, timeout=timeout)
        except Exception:  # noqa: BLE001
            return None
        if t is None:
            return None
        try:
            if not all(math.isfinite(float(getattr(t, k))) for k in ("x", "y", "z")):
                return None
        except Exception:  # noqa: BLE001
            return None
        return t

    def _store_pos(self, t):
        # map ENU (x=E, y=N, z=U) -> local NED (north, east, down)
        self._pos = (float(t.y), float(t.x), -float(t.z))
        self._pos_ts = time.monotonic()

    def _refresh(self, force=False):
        if force or (time.monotonic() - self._pos_ts) > POS_TTL:
            t = self._telemetry()
            if t is not None:
                self._store_pos(t)

    @property
    def pos(self):
        self._refresh()
        return self._pos

    def rel_alt(self) -> float:
        self._refresh()
        return -self._pos[2]           # up (m)

    def airborne(self) -> bool:
        return self.rel_alt() > 0.6

    # ---- flight -------------------------------------------------------------
    def _navigate(self, north, east, up, auto_arm=True, frame=None):
        # local NED (north, east, up) -> ENU кадра (x=east, y=north, z=up).
        # auto_arm=True ALWAYS: self-healing. If a drone drops out of OFFBOARD
        # (sank to ground -> land-detector disarm), navigate would otherwise fail
        # "Copter is not in OFFBOARD mode, use auto_arm?" and never recover; with
        # auto_arm it re-arms + re-enters OFFBOARD (no-op if already flying).
        with self._lock:
            return self._d.control.navigate(
                x=float(east), y=float(north), z=float(abs(up)), yaw=0.0,
                speed=NAV_SPEED, frame_id=(frame or FRAME), auto_arm=bool(auto_arm))

    def _alt_map(self) -> float:
        """Высота из EKF (map) — доступна всегда, в отличие от aruco_map с земли."""
        try:
            with self._lock:
                t = self._d.control.get_telemetry(frame_id="map", timeout=2.0)
            z = float(t.z)
            return z if math.isfinite(z) else 0.0
        except Exception:  # noqa: BLE001
            return 0.0

    def takeoff(self, z=None):
        """Arm + climb, then anchor in the working frame.

        Real-drone recipe: climb in TAKEOFF_FRAME (body — relative, needs no
        localization: aruco markers are usually NOT visible from the ground),
        then at altitude re-anchor in FRAME (aruco_map): read the marker-based
        position and issue the hold there. In SITL both frames are `map` and this
        degenerates to the old behaviour. Retries the arm/OFFBOARD handshake
        until the drone is actually airborne."""
        self.tz = abs(z if z is not None else TAKEOFF_Z)
        self.paused = False
        self.flying = True
        body_climb = TAKEOFF_FRAME != FRAME
        if not body_climb:
            self._refresh(force=True)
            self.tx, self.ty = self._pos[0], self._pos[1]
        for _ in range(6):                       # ~30s of arm/climb retries
            if body_climb:
                # body: (0,0,+z) = вертикальный подъём над точкой старта
                self._navigate(0.0, 0.0, self.tz, auto_arm=True, frame=TAKEOFF_FRAME)
            else:
                self._navigate(self.tx, self.ty, self.tz, auto_arm=True)
            t0 = time.time()
            while time.time() - t0 < 5:
                time.sleep(0.5)
                alt = self._alt_map() if body_climb else self.rel_alt()
                if alt > self.tz * 0.6:
                    if body_climb:
                        self._anchor_frame()
                    return
        # left grounded — subsequent goto() still carries auto_arm and will retry

    def _anchor_frame(self):
        """После body-взлёта: перехватиться в рабочий кадр (aruco_map) — держать
        ТЕКУЩУЮ позицию по маркерам. Без телеметрии кадра честно шумим: дальше
        goto() в этом кадре упадёт в сервисе, а не полетит вслепую."""
        deadline = time.time() + FRAME_WAIT_SEC
        while time.time() < deadline:
            t = self._telemetry(timeout=2.0)
            if t is not None:
                self._store_pos(t)
                self.tx, self.ty = self._pos[0], self._pos[1]
                self._navigate(self.tx, self.ty, self.tz, auto_arm=True)
                print(f"[sverk_flight {self.inst}] anchored in {FRAME} at "
                      f"({self.tx:.2f},{self.ty:.2f},{self.tz:.2f})", flush=True)
                return
            time.sleep(0.5)
        print(f"[sverk_flight {self.inst}] WARN: no {FRAME} telemetry "
              f"{FRAME_WAIT_SEC:.0f}s after takeoff (markers not visible?) — "
              "holding body climb, goto() will fail honestly", flush=True)

    def goto(self, x, y, z=TAKEOFF_Z, yaw=None):
        """x=north, y=east, z=up (metres). Matches fleet_flight.goto semantics."""
        self.tx, self.ty, self.tz = float(x), float(y), abs(z)
        if yaw is not None:
            self.tyaw = yaw
        self._navigate(self.tx, self.ty, self.tz, auto_arm=True)

    def reached(self) -> bool:
        # Pure check — do NOT re-issue navigate here. offboard_control is launched
        # with auto_release:=false, so it keeps streaming the last navigate target
        # (position hold); calling navigate again on every poll re-inits the C++
        # SpeedController trajectory and the drone restarts its approach forever
        # (never progresses). goto() issues navigate exactly once.
        self._refresh()
        dx = self._pos[0] - self.tx
        dy = self._pos[1] - self.ty
        dz = (-self._pos[2]) - self.tz
        return math.sqrt(dx * dx + dy * dy + dz * dz) < REACH_TOL

    def picture(self, timeout=3.0):
        """Кадр бортовой камеры (sensor_msgs/Image, raw) через фасад
        sverk_interfaces — тот же узел, что летает; лок обязателен (фасад
        крутит spin_once на вызов)."""
        with self._lock:
            return self._d.image.take_picture(timeout=timeout, raw=True)

    def aruco_onboard(self, timeout=1.5):
        """Бортовой aruco-стек (aruco_det_loc) вместо cv2: один снимок состояния
        (ids видимых маркеров, позиция в aruco_map) подпиской на
        /aruco/det/markers (aruco_det_loc/MarkerArray) и /aruco/loc/pose_cov
        (PoseWithCovarianceStamped). QoS sensor-data: best-effort sub принимает
        и reliable, и best-effort паблишеры. Возврат: (ids, (x, y) | None)."""
        import rclpy
        from rclpy.qos import qos_profile_sensor_data
        from geometry_msgs.msg import PoseWithCovarianceStamped
        from aruco_det_loc.msg import MarkerArray
        got_m, got_p = [], []
        with self._lock:
            node = self._d.image._node
            s1 = node.create_subscription(
                MarkerArray, "/aruco/det/markers",
                lambda m: got_m.append(m), qos_profile_sensor_data)
            s2 = node.create_subscription(
                PoseWithCovarianceStamped, "/aruco/loc/pose_cov",
                lambda m: got_p.append(m), qos_profile_sensor_data)
            deadline = time.monotonic() + timeout
            try:
                while (not got_m or not got_p) and time.monotonic() < deadline:
                    rclpy.spin_once(node, timeout_sec=0.1)
            finally:
                node.destroy_subscription(s1)
                node.destroy_subscription(s2)
        ids = [int(mk.id) for mk in got_m[-1].markers] if got_m else []
        pose = None
        if got_p:
            p = got_p[-1].pose.pose.position
            if math.isfinite(float(p.x)) and math.isfinite(float(p.y)):
                pose = (float(p.x), float(p.y))
        return ids, pose

    def land(self):
        self.flying = False
        try:
            with self._lock:
                self._d.control.land(timeout=15.0)
        except Exception:  # noqa: BLE001
            pass

    def pause(self):
        """Battery-swap: land + freeze until resume()."""
        self.paused = True
        self.land()
        self.flying = False

    def resume(self):
        self.takeoff()


class Fleet:
    def __init__(self, n: int):
        self.drones = [Drone(i) for i in range(n)]

    def connect_all(self):
        for d in self.drones:
            ok = d.connect()
            print(f"drone {d.inst} ({d.ns}) connect: {'OK' if ok else 'FAIL'}", flush=True)

    def start_all(self):
        for d in self.drones:
            d.start()


def selftest(inst: int):
    """python3 sverk_flight.py selftest <inst> — fly one drone a 2 m box."""
    d = Drone(inst)
    print(f"connect /px4_{inst}: {'OK' if d.connect() else 'FAIL'}", flush=True)
    d.start()
    print(f"pos(NED n,e,d)={tuple(round(v,2) for v in d.pos)}", flush=True)
    d.takeoff(z=TAKEOFF_Z)
    for s in range(20):
        time.sleep(1)
        if d.rel_alt() > TAKEOFF_Z * 0.7:
            break
    print(f"airborne, alt={d.rel_alt():.2f}", flush=True)
    for (n, e) in [(1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]:
        d.goto(n, e, z=TAKEOFF_Z)
        for s in range(30):
            time.sleep(1)
            if d.reached():
                break
        p = d.pos
        print(f"-> target N={n} E={e}: pos N={p[0]:.2f} E={p[1]:.2f} alt={d.rel_alt():.2f} "
              f"{'REACHED' if d.reached() else 'timeout'}", flush=True)
    print("landing", flush=True)
    d.land()


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    inst = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    if cmd == "selftest":
        selftest(inst)
