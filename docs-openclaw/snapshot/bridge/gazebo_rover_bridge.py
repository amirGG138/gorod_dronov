#!/usr/bin/env python3
"""Gazebo rover bridge — the §6 HTTP sidecar for a rover that lives in the
REAL Gazebo (Harmonic) sim, not the mock. Same contract as bridge/mock.py
(`/navigate` streams pose frames, `/pose`, `/healthz`, no-op `/land`+`/takeoff`),
so the rover agent role and the openclaw stack don't change — only BRIDGE_URL.

It drives a mock rover = a kinematic cube inside the `sverk_sitl` container by
shelling `docker exec ... rover_driver.py` (which talks to gz Transport). The
cube is teleported along A->B and you watch it roll to the fire in the Gazebo
window. Keeping gz on the container side (via docker exec) means the host needs
no ROS2/Gazebo install — only the docker CLI.

Env: PORT(9105) CONTAINER(sverk_sitl) GZ_WORLD(obrik_aruco) CELL_SIZE_M(0.8)
     FIELD_ORIGIN_X/Y(0) ROVER_Z(0.2) ROVER_START("0,0") FIRE_CELL("4,4")
     NAV_STEP_SEC(0.12) ROVER_SPEED_MS(0.6) DRIVER_SRC(bridge/gazebo/rover_driver.py)
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(os.environ.get("PORT", "9105"))
CONTAINER = os.environ.get("CONTAINER", "sverk_sitl")
HERE = Path(__file__).resolve().parent
DRIVER_SRC = Path(os.environ.get("DRIVER_SRC", HERE / "gazebo" / "sim_driver.py"))
DRIVER_DST = "/tmp/sim_driver.py"

# env forwarded into the container so cell<->metre mapping + fire location match
_FWD = ("GZ_WORLD", "CELL_SIZE_X", "CELL_SIZE_Y", "FIELD_ORIGIN_X", "FIELD_ORIGIN_Y",
        "DRONE_Z", "ROVER_Z", "FIRE_Z", "ROVER_START", "FIRE_CELL", "DRONES",
        "NAV_STEP_SEC", "ROVER_SPEED_MS")


def _exec_env() -> list[str]:
    out = []
    for k in _FWD:
        if os.environ.get(k) is not None:
            out += ["-e", f"{k}={os.environ[k]}"]
    return out


def _driver_cmd(args: list[str]) -> list[str]:
    return ["docker", "exec", *_exec_env(), CONTAINER, "python3", DRIVER_DST, *args]


def _run_driver(args: list[str], timeout: float = 15.0) -> dict:
    """Run a one-shot driver command, return the last JSON line it printed."""
    p = subprocess.run(_driver_cmd(args), capture_output=True, text=True, timeout=timeout)
    last = {}
    for line in (p.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                last = json.loads(line)
            except json.JSONDecodeError:
                pass
    if not last and p.returncode != 0:
        return {"error": (p.stderr or "driver failed").strip()[:300]}
    return last


def _copy_driver() -> None:
    subprocess.run(["docker", "cp", str(DRIVER_SRC), f"{CONTAINER}:{DRIVER_DST}"],
                   capture_output=True, text=True, timeout=15)


def _container_up() -> bool:
    p = subprocess.run(["docker", "exec", CONTAINER, "true"],
                       capture_output=True, text=True, timeout=8)
    return p.returncode == 0


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_body(self) -> dict:
        n = int(self.headers.get("content-length", 0))
        return json.loads(self.rfile.read(n).decode()) if n else {}

    def do_GET(self):
        if self.path == "/healthz":
            return self._json(200, {"ok": _container_up(), "container": CONTAINER,
                                    "sim": "gazebo", "world": os.environ.get("GZ_WORLD", "obrik_aruco")})
        if self.path == "/pose":
            r = _run_driver(["pose"])
            if "xy" in r:
                return self._json(200, r)
            return self._json(503, {"error": r.get("error", "no pose")})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        try:
            body = self._read_body()
        except Exception as exc:  # strict boundary (§11)
            return self._json(400, {"error": f"bad json: {exc}"})
        # rover doesn't fly; land/takeoff are no-ops so pause/resume still work
        if self.path in ("/land", "/takeoff"):
            landed = self.path == "/land"
            r = _run_driver(["pose"])
            return self._json(200, {"ok": True, "landed": landed,
                                    "pose": r.get("xy", [0, 0])})
        if self.path == "/navigate":
            return self._navigate(body)
        return self._json(404, {"error": "not found"})

    def _navigate(self, body):
        frm = body.get("from")
        to = body.get("to")
        if not (isinstance(frm, list) and isinstance(to, list)
                and len(frm) == 2 and len(to) == 2):
            return self._json(400, {"error": "from/to must be [x,y] cells"})
        args = ["drive", str(frm[0]), str(frm[1]), str(to[0]), str(to[1])]
        try:
            proc = subprocess.Popen(_driver_cmd(args), stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True)
        except Exception as exc:  # noqa: BLE001
            return self._json(500, {"error": f"drive failed: {exc}"})
        self.send_response(200)
        self.send_header("content-type", "application/x-ndjson")
        self.end_headers()
        try:
            for line in proc.stdout:
                line = line.strip()
                if line.startswith("{"):
                    self.wfile.write((line + "\n").encode())
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            proc.kill()
            return
        proc.wait(timeout=5)


def main():
    print(f"[gazebo-rover] bridge on :{PORT} -> container {CONTAINER} "
          f"world={os.environ.get('GZ_WORLD', 'obrik_aruco')} "
          f"fire={os.environ.get('FIRE_CELL', '4,4')}", flush=True)
    if _container_up():
        _copy_driver()
        r = _run_driver(["spawn"], timeout=20)
        print(f"[gazebo-rover] spawn: {json.dumps(r)}", flush=True)
    else:
        print(f"[gazebo-rover] WARNING: container {CONTAINER} not reachable — "
              "start the sim first", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
