#!/usr/bin/env python3
"""Real Gazebo rover bridge — same HTTP contract as bridge/mock.py, but drives a
REAL kinematic rover cube in Gazebo, cell-by-cell (A* over the grid), to the
fire. Runs INSIDE the sverk_sitl container; shares drone-1's gz partition (d0)
so the rover rolls across the same aruco field the drone mapped.

  /navigate {from,to,grid} -> A* path -> teleport the cube cell-by-cell,
                              streaming {pose,progress} ... {status:arrived}
  /pose  /healthz  /land  /takeoff(no-op)

Reuses bridge/gazebo/sim_driver.py (gz Transport set_pose) and bridge/mock.py's
A*. GZ_PARTITION + grid mapping are set in-process before importing sim_driver.

Env: PORT(9005) GZ_PARTITION(d0) GZ_WORLD(obrik_aruco6x6)
     CELL_SIZE(0.6) FIELD_ORIGIN(-1.5) FIRE_CELL(5,5) ROVER_START(0,0)
"""
from __future__ import annotations
import json, os, time, threading, struct, zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "9005"))
CELL = os.environ.get("CELL_SIZE", "0.6")
ORIGIN = os.environ.get("FIELD_ORIGIN", "-1.5")
# configure sim_driver's grid + partition BEFORE importing it (module reads env
# at import time and creates its gz Node in the chosen partition)
# partition: d0 in the partitioned setup; unset/empty => the single shared world
_gp = os.environ.get("GZ_PARTITION")
if _gp in ("", "none", "default"):
    os.environ.pop("GZ_PARTITION", None)
elif _gp is None:
    os.environ["GZ_PARTITION"] = "d0"
os.environ["GZ_WORLD"] = os.environ.get("GZ_WORLD", "obrik_aruco6x6")
os.environ["CELL_SIZE_X"] = CELL
os.environ["CELL_SIZE_Y"] = CELL
os.environ["FIELD_ORIGIN_X"] = ORIGIN
os.environ["FIELD_ORIGIN_Y"] = ORIGIN
os.environ["DRONES"] = ""                    # only rover + fire, no mock drone cubes
os.environ.setdefault("FIRE_CELL", "5,5")
os.environ.setdefault("ROVER_START", "0,0")
os.environ.setdefault("ROVER_Z", "0.12")
os.environ.setdefault("NAV_STEP_SEC", "0.18")

import sys
sys.path.insert(0, "/tmp")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "gazebo"))
import sim_driver as sd          # noqa: E402
from mock import astar           # noqa: E402

NAV_STEP = float(os.environ.get("NAV_STEP_SEC", "0.18"))

# --- top-down overview snapshot: subscribe to the world's skycam once and save a
# frame of the WHOLE field after every rover step, so there is a top-down photo
# per move (the cube teleports faster than the 4 Hz skycam sampler, so a separate
# continuous capturer would miss the drive). Best-effort: no gz bindings / no
# frame yet => silently skips. OVERVIEW_STEPS=0 disables.
_OV_DIR = os.environ.get("OVERVIEW_DIR", "/tmp/fleet/overview")
_OV_ON = os.environ.get("OVERVIEW_STEPS", "1") not in ("0", "", "false", "no")
_ov = {"w": 0, "h": 0, "buf": None, "i": 0}
_ov_lock = threading.Lock()


def _png(path, w, h, data):
    raw = b"".join(b"\x00" + data[y * w * 3:(y + 1) * w * 3] for y in range(h))
    def ch(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    open(path, "wb").write(
        b"\x89PNG\r\n\x1a\n"
        + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + ch(b"IDAT", zlib.compress(raw, 6)) + ch(b"IEND", b""))


def _ov_start():
    if not _OV_ON:
        return
    try:
        from gz.transport13 import Node
        from gz.msgs10.image_pb2 import Image
        os.makedirs(_OV_DIR, exist_ok=True)
        topic = os.environ.get(
            "SKYCAM_TOPIC",
            f"/world/{os.environ['GZ_WORLD']}/model/skycam_over/link/l/sensor/cam/image")

        def cb(m):
            with _ov_lock:
                _ov.update(w=m.width, h=m.height, buf=bytes(m.data))
        node = Node()
        node.subscribe(Image, topic, cb)
        globals()["_ov_node"] = node          # keep the subscription alive
        print(f"[rover_bridge] overview snapshots -> {_OV_DIR} ({topic})", flush=True)
    except Exception as e:
        print(f"[rover_bridge] overview subscribe failed: {e}", flush=True)


def _ov_snap(tag=""):
    if not _OV_ON:
        return
    with _ov_lock:
        w, h, buf, i = _ov["w"], _ov["h"], _ov["buf"], _ov["i"]
        _ov["i"] += 1
    if buf and w:
        try:
            _png(f"{_OV_DIR}/latest.png", w, h, buf[:w * h * 3])
            _png(f"{_OV_DIR}/step_{i:04d}_{tag}.png", w, h, buf[:w * h * 3])
        except Exception as e:
            print(f"[rover_bridge] snap err: {e}", flush=True)


# --- per-cell skycam tiles: crop the fixed top-down frame into ALIGNED cell tiles.
# In multi-instance SITL the drones don't reliably reach a commanded cell, so an
# overhead crop is the dependable "photo per cell". Calibrated to the skycam pose
# + 0.8m field via the 4 aruco pads: cell (cx,cy) centre px = (X0+PXC*cy, Y0-PXC*cx)
# (a -90deg camera rotation). Env-overridable if the skycam/field is retuned.
TILE_X0 = float(os.environ.get("TILE_X0", "135.5"))
TILE_Y0 = float(os.environ.get("TILE_Y0", "763.5"))
TILE_PXC = float(os.environ.get("TILE_PXC", "125.6"))     # skycam px per cell
TILE_HALF = float(os.environ.get("TILE_HALF", "0.6"))     # crop half-size in cells
TILE_OUT = int(os.environ.get("TILE_OUT", "150"))


def _tile_jpeg(cx, cy):
    """Crop the latest skycam frame to cell (cx,cy) -> small JPEG bytes (None if
    no frame / crop fails). Uses the in-memory RGB buffer (no PNG decode)."""
    with _ov_lock:
        w, h, buf = _ov["w"], _ov["h"], _ov["buf"]
    if not buf or not w:
        return None
    try:
        from PIL import Image
        import io
        # ROTATE_270 = 90deg CW: the skycam images cell-x on its VERTICAL axis and
        # cell-y on horizontal (from the aruco pads), but the dashboard grid is
        # col=cx,row=cy. Rotating the frame 90 CW aligns the axes so the per-cell
        # tiles assemble into ONE coherent map (else it looks like a scrambled
        # puzzle). After the rotation cell (cx,cy) centre = (X0+PXC*cx, X0+PXC*cy).
        im = Image.frombytes("RGB", (w, h), buf[:w * h * 3]).transpose(Image.ROTATE_270)
        px = TILE_X0 + TILE_PXC * cx
        py = TILE_X0 + TILE_PXC * cy
        half = TILE_PXC * TILE_HALF
        tile = im.crop((px - half, py - half, px + half, py + half)).resize((TILE_OUT, TILE_OUT))
        b = io.BytesIO()
        tile.save(b, "JPEG", quality=62)
        return b.getvalue()
    except Exception as e:  # noqa: BLE001
        print(f"[rover_bridge] tile err: {e}", flush=True)
        return None


# --- real LED beacon: a bright emissive box that rides above the rover when the
# beacon is on (city_missions: migалка during water dwell / delivery). off = sunk.
_LED = {"state": "off"}
BEACON_SDF = """<?xml version="1.0"?>
<sdf version="1.9"><model name="rover_beacon"><static>true</static><pose>0 0 -5 0 0 0</pose>
 <link name="l"><visual name="v"><geometry><box><size>0.12 0.12 0.12</size></box></geometry>
  <material><ambient>1 0.1 0.1 1</ambient><diffuse>1 0.2 0.2 1</diffuse><emissive>1 0.15 0.05 1</emissive></material></visual>
 <light name="bl" type="point"><diffuse>1 0.3 0.1 1</diffuse><attenuation><range>1.2</range><linear>0.6</linear></attenuation><cast_shadows>false</cast_shadows></light></link></model></sdf>
"""


def _beacon(on: bool):
    """Place the beacon above the rover (on) or underground (off)."""
    try:
        if on:
            p = sd._all_poses().get("rover")
            if p:
                sd.set_pose("rover_beacon", p[0], p[1], sd.ROVER_Z + 0.35, 0.0)
        else:
            sd.set_pose("rover_beacon", 0.0, 0.0, -5.0, 0.0)
    except Exception:
        pass


def _spawn():
    try:
        sd.cmd_spawn()           # prints JSON; creates rover + fire in the world
        print(f"[rover_bridge] spawned rover+fire in {os.environ.get('GZ_PARTITION','default')}", flush=True)
    except Exception as e:
        print(f"[rover_bridge] spawn error: {e}", flush=True)
    try:
        import tempfile
        f = os.path.join(tempfile.gettempdir(), "rover_beacon.sdf")
        open(f, "w").write(BEACON_SDF)
        sd.create_from_file(f, "rover_beacon")
    except Exception as e:
        print(f"[rover_bridge] beacon spawn error: {e}", flush=True)


def _rover_cell():
    try:
        poses = sd._all_poses()
        p = poses.get("rover")
        if p:
            return sd.m_to_cell(p[0], p[1])
    except Exception:
        pass
    return [0, 0]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("content-length", 0))
        return json.loads(self.rfile.read(n).decode()) if n else {}

    def do_GET(self):
        if self.path == "/healthz":
            return self._json(200, {"ok": True, "agent": "rover"})
        if self.path == "/pose":
            return self._json(200, {"xy": _rover_cell(), "heading": 0.0})
        if self.path.startswith("/tile"):
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query)
            try:
                cx, cy = int(q["cx"][0]), int(q["cy"][0])
            except Exception:
                return self._json(400, {"error": "cx,cy required"})
            data = _tile_jpeg(cx, cy)
            if data is None:
                return self._json(404, {"error": "no skycam frame"})
            self.send_response(200)
            self.send_header("content-type", "image/jpeg")
            self.send_header("content-length", str(len(data)))
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        try:
            body = self._body()
        except Exception as e:
            return self._json(400, {"error": f"bad json: {e}"})
        if self.path in ("/land", "/takeoff"):
            return self._json(200, {"ok": True})
        if self.path == "/led":
            eff = str(body.get("effect") or ("on" if body.get("on") else "off")).lower()
            _LED["state"] = eff
            _beacon(eff in ("on", "blink"))
            return self._json(200, {"ok": True, "led": eff})
        if self.path == "/dwell":
            return self._dwell(body)
        if self.path == "/move":
            return self._move_to(body)
        if self.path == "/navigate":
            # {to} alone -> drive to a cell (city_rover); {from,to,grid} -> stream (survey)
            if body.get("from") is None and isinstance(body.get("to"), list):
                return self._move_to(body)
            return self._navigate(body)
        return self._json(404, {"error": "not found"})

    def _dwell(self, body):
        """Hold the rover stationary for `seconds` with the LED as asked; return the
        regulation evidence (stationary_seconds + led + cell). Real wall-clock wait."""
        secs = float(body.get("seconds", 0))
        led = str(body.get("led") or _LED["state"] or "off").lower()
        _LED["state"] = led
        _beacon(led in ("on", "blink"))
        cell0 = _rover_cell()
        t0 = time.time()
        time.sleep(max(0.0, secs))
        cell1 = _rover_cell()
        stayed = round(time.time() - t0, 2)
        return self._json(200, {"ok": True, "cell": cell1,
                                "stationary_seconds": stayed,
                                "moved": cell0 != cell1,
                                "led": led in ("on", "blink")})

    def _move_to(self, body):
        """Drive the cube from its current cell to `to`, cell-by-cell (A* over an
        optional grid, else free). Beacon rides along if lit. Returns final pose."""
        to = body.get("to")
        if not isinstance(to, list):
            return self._json(400, {"error": "to:[x,y] required"})
        frm = _rover_cell()
        grid = body.get("grid")
        if not isinstance(grid, list):
            n = max(int(to[0]), int(to[1]), frm[0], frm[1], 5) + 1
            grid = [[0] * n for _ in range(n)]
        path = astar(grid, frm, to) or [frm, to]
        for c in path:
            x, y = sd.cell_to_m(c[0], c[1])
            sd.set_pose("rover", x, y, sd.ROVER_Z, 0.0)
            if _LED["state"] in ("on", "blink"):
                _beacon(True)
            time.sleep(NAV_STEP)
            _ov_snap(f"{int(c[0])}-{int(c[1])}")
        return self._json(200, {"ok": True, "pose": [int(to[0]), int(to[1])],
                                "cells": len(path)})

    def _navigate(self, body):
        frm, to, grid = body.get("from"), body.get("to"), body.get("grid")
        if not (isinstance(frm, list) and isinstance(to, list) and isinstance(grid, list)):
            return self._json(400, {"error": "from/to/grid required"})
        path = astar(grid, frm, to)
        self.send_response(200)
        self.send_header("content-type", "application/x-ndjson")
        self.end_headers()

        def emit(o):
            self.wfile.write((json.dumps(o) + "\n").encode()); self.wfile.flush()
        if not path:
            return emit({"status": "blocked", "reason": "no path"})
        n = len(path)
        for i, c in enumerate(path):
            x, y = sd.cell_to_m(c[0], c[1])
            sd.set_pose("rover", x, y, sd.ROVER_Z, 0.0)
            emit({"pose": [int(c[0]), int(c[1])], "progress": round((i + 1) / n, 3)})
            time.sleep(NAV_STEP)
            _ov_snap(f"{int(c[0])}-{int(c[1])}")
        emit({"status": "arrived", "pose": [int(to[0]), int(to[1])]})


def main():
    _spawn()
    _ov_start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[rover_bridge] REAL rover on :{PORT} partition={os.environ.get('GZ_PARTITION','default')} "
          f"world={os.environ['GZ_WORLD']}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
