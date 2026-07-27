#!/usr/bin/env python3
"""Real ROS2/PX4 bridge sidecar — same HTTP contract as bridge/mock.py, but every
action drives a REAL PX4 SITL drone (via MAVLink OFFBOARD) in its own Gazebo
partition. Drop-in: point a survey drone's BRIDGE_URL at this instead of the mock
and the unchanged openclaw agents fly real drones.

  drone-N  ->  PX4 instance (N-1)  ->  MAVLink udp:127.0.0.1:(14540+N-1)
           ->  gz partition d(N-1), model x500_obrik_base_(N-1)

Contract (subset the survey uses): /pose /photograph {cell} /analyze
/navigate {from,to,grid} /move {to} /land /takeoff /led /healthz.

Cell<->metres: the WxH cell field maps to the aruco grid. cell (cx,cy) center in
the drone's local NED frame = (FIELD_ORIGIN + cx*CELL, FIELD_ORIGIN + cy*CELL).
Each drone spawns at NED (0,0) in its own partition, so the mapping is identical
for every drone. Run INSIDE the sverk_sitl container (has MAVLink + gz).

Env: AGENT_ID=drone-N | INSTANCE=k, PORT, GZ_PARTITION=dk, WORLD,
     CELL_SIZE(0.6) FIELD_ORIGIN(-1.5) TAKEOFF_Z(3.0) SCENARIO FIXTURES BLACKBOARD.
"""
from __future__ import annotations
import json, os, re, time, struct, zlib, threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

# Flight backend: `sverk` drives the real sverk offboard_control node via
# sverk_interfaces (Navigate/Land/GetTelemetry over uXRCE-DDS -> PX4); `mavlink`
# uses the direct-MAVLink fallback. Same Drone interface either way, so the rest
# of this bridge (gz camera, cv2-aruco reality, VLM, cell math) is unchanged.
BACKEND = os.environ.get("FLIGHT_BACKEND", "mavlink").lower()
if BACKEND == "sverk":
    from sverk_flight import Drone, TAKEOFF_Z as DEF_Z
else:
    from fleet_flight import Drone, TAKEOFF_Z as DEF_Z

AGENT = os.environ.get("AGENT_ID", "drone-1")
def _inst_from_agent() -> int:
    m = re.search(r"(\d+)", AGENT)
    return (int(m.group(1)) - 1) if m else 0
INSTANCE = int(os.environ.get("INSTANCE", _inst_from_agent()))
PORT = int(os.environ.get("PORT", str(9001 + INSTANCE)))
WORLD = os.environ.get("WORLD", "obrik_aruco6x6")
CELL = float(os.environ.get("CELL_SIZE", "0.6"))
ORIGIN = float(os.environ.get("FIELD_ORIGIN", "-1.5"))
ALT = float(os.environ.get("TAKEOFF_Z", str(DEF_Z)))
SCENARIO = os.environ.get("SCENARIO", "survey-city")
FIXTURES = Path(os.environ.get("FIXTURES", "/tmp/test_fixtures"))
ARTIFACTS = Path(os.environ.get("ARTIFACTS_DIR", "/tmp/fleet/artifacts"))
ARTIFACTS.mkdir(parents=True, exist_ok=True)
# per-cell preview thumbnail: the full 1280x960 nadir PNG is kept for debug, but
# the dashboard only needs a tiny image per cell, so we also save a downscaled
# JPEG (PHOTO_THUMB_MAX px, quality PHOTO_THUMB_Q) that the viz proxies to the
# browser. ~6-10 KB/cell => cheap to overlay the whole 6x6 field.
THUMB_MAX = int(os.environ.get("PHOTO_THUMB_MAX", "240"))
THUMB_Q = int(os.environ.get("PHOTO_THUMB_Q", "55"))
# keep the central fraction of the wide-FOV frame = the cell directly under the
# drone; the periphery images neighbour cells + the sides of 3D buildings.
PHOTO_CROP = float(os.environ.get("PHOTO_CROP", "0.5"))
MODEL = f"x500_obrik_base_{INSTANCE}"
IMG_TOPIC = f"/world/{WORLD}/model/{MODEL}/link/rpi_camera_link/sensor/imager/image"

REACH_TIMEOUT = float(os.environ.get("REACH_TIMEOUT", "30"))
INSPECT_Z = float(os.environ.get("INSPECT_Z", "1.3"))     # descend to inspect a cell
INSPECT_SETTLE = float(os.environ.get("INSPECT_SETTLE", "3.5"))
# Camera framing offset (cells): logical cell C is imaged from cell C-(OFFX,OFFY)
# and pose adds it back. The obrik rpi_camera is mounted NADIR (model pose pitch
# 90deg = straight down), so a drone over cell C images C and the geometrically
# correct offset is 0. The old 0.6 m obrik survey ran with 1 as an empirical
# fudge; on the 0.8 m Domiki map that mislabels every photo by one cell AND flies
# edge cells off the map (blank frames), so the city run sets CAM_OFF*=0.
CAM_OFFX = int(os.environ.get("CAM_OFFX", "1"))
CAM_OFFY = int(os.environ.get("CAM_OFFY", "1"))
ANALYZE_SETTLE = float(os.environ.get("ANALYZE_SETTLE", "2.0"))
# hover-settle before a /photograph: the body-fixed nadir camera tilts with the
# airframe, so a shot taken while the drone is still banking from the approach
# images the horizon (grey half-frames). Let it level out first.
PHOTO_SETTLE = float(os.environ.get("PHOTO_SETTLE", "1.5"))
# constant offset between the marker the camera centres on and the drone's own
# cell (camera framing). calibrated aruco cell = raw - (ARUCO_OFFX, ARUCO_OFFY).
ARUCO_OFFX = int(os.environ.get("ARUCO_OFFX", "1"))
ARUCO_OFFY = int(os.environ.get("ARUCO_OFFY", "-1"))


VLM_ON = os.environ.get("VLM_FIRE", "1") not in ("0", "", "false", "no")
VLM_MODEL = os.environ.get("MODEL_VISION") or os.environ.get("MODEL", "gemma4-vlm")
VLM_BASE = os.environ.get("SVERK_API_BASE", "https://ai.sverk.tech/v1").rstrip("/")
VLM_KEY = os.environ.get("SVERK_API_KEY", "")
# Realistic wide-FOV nadir camera: at survey altitude ONE frame sees several
# cells, so a fire is visible from neighbours too. The discriminator is WHERE the
# fire sits in the frame — directly under the drone => CENTRE => this cell; a
# neighbour sees it pushed to an EDGE. The VLM reports both fire and its position;
# analyze() attributes the fire to a cell only when it's centred (= under the
# drone). The per-frame direction (POS) is also returned so a coordinator can
# cross-match neighbouring frames ("fire is to the RIGHT of this cell").
# Целевой объект детекции настраивается env-ом (на демо огня может не быть):
#   VLM_TARGET      — имя объекта («пожар», «жёлтый куб», «человек» ...)
#   VLM_TARGET_DESC — как он выглядит для VLM
# Токен ответа остаётся FIRE=yes|no — это wire-протокол «цель найдена», не огонь.
VLM_TARGET = os.environ.get("VLM_TARGET", "пожар")
VLM_TARGET_DESC = os.environ.get(
    "VLM_TARGET_DESC", "яркий ОРАНЖЕВО-КРАСНЫЙ светящийся объект")
_VLM_SYS = _VLM_USR = ""


def _rebuild_vlm_prompts():
    """Промпты собираются из текущей цели; цель меняется на лету (POST /target)."""
    global _VLM_SYS, _VLM_USR
    _VLM_SYS = (f"Ты — детектор цели для дрона. ЦЕЛЬ: {VLM_TARGET} — {VLM_TARGET_DESC}. "
                "Кадр — вид строго вниз (надир) на поле с ARUCO-маркерами (чёрно-белые "
                "квадраты). Дрон висит над проверяемой клеткой; из-за широкого обзора "
                "цель соседней клетки видна у КРАЯ кадра, а цель ЭТОЙ клетки — "
                "в ЦЕНТРЕ. Определи: есть ли цель и ГДЕ она в кадре.")
    _VLM_USR = (f"Есть ли в кадре цель ({VLM_TARGET}: {VLM_TARGET_DESC}) и где она? "
                "Ответь СТРОГО двумя полями: FIRE=yes|no  POS=center|top|bottom|left|right|none "
                "(POS=center только если цель в центральной трети кадра, прямо под дроном; "
                "если цели нет — POS=none). Затем одно предложение.")


_rebuild_vlm_prompts()


def set_target(name: str, desc: str = "") -> None:
    global VLM_TARGET, VLM_TARGET_DESC
    VLM_TARGET = (name or VLM_TARGET).strip()[:80]
    if desc.strip():
        VLM_TARGET_DESC = desc.strip()[:200]
    _rebuild_vlm_prompts()
    print(f"[bridge {AGENT}] VLM target -> {VLM_TARGET} ({VLM_TARGET_DESC})", flush=True)


def vlm_fire(png: bytes):
    """Ask gemma4-vlm for fire + its position in the frame. Returns
    (centred_fire|None, confidence, reason, pos). centred_fire is True only when a
    fire is present AND centred (directly under the drone). pos in
    {center,top,bottom,left,right,none}. None => VLM unavailable (map fallback)."""
    import base64, urllib.request
    try:
        b64 = base64.b64encode(png).decode()
        payload = {"model": VLM_MODEL, "max_tokens": 120, "messages": [
            {"role": "system", "content": _VLM_SYS},
            {"role": "user", "content": [
                {"type": "text", "text": _VLM_USR},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]}
        req = urllib.request.Request(VLM_BASE + "/chat/completions",
                                     data=json.dumps(payload).encode(),
                                     headers={"content-type": "application/json",
                                              "authorization": f"Bearer {VLM_KEY}"},
                                     method="POST")
        r = json.loads(urllib.request.urlopen(req, timeout=45).read().decode())
        txt = (r["choices"][0]["message"].get("content") or "").strip()
        flat = txt.lower().replace(" ", "")
        has_fire = ("fire=yes" in flat) and ("fire=no" not in flat)
        m = re.search(r"pos=(center|top|bottom|left|right|none)", flat)
        pos = m.group(1) if m else ("center" if has_fire else "none")
        centred = has_fire and pos == "center"
        return centred, (0.95 if centred else 0.9), txt[:160], pos
    except Exception as e:
        return None, 0.0, f"vlm_err:{type(e).__name__}", "none"


def vlm_describe(png: bytes) -> str:
    """Свободное описание кадра (для выбора нового объекта-цели оператором)."""
    import base64, urllib.request
    try:
        b64 = base64.b64encode(png).decode()
        payload = {"model": VLM_MODEL, "max_tokens": 150, "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": "Перечисли 3-5 главных объектов в кадре, "
                                         "коротко по-русски, одной строкой."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]}
        req = urllib.request.Request(VLM_BASE + "/chat/completions",
                                     data=json.dumps(payload).encode(),
                                     headers={"content-type": "application/json",
                                              "authorization": f"Bearer {VLM_KEY}"},
                                     method="POST")
        r = json.loads(urllib.request.urlopen(req, timeout=45).read().decode())
        return (r["choices"][0]["message"].get("content") or "").strip()[:400]
    except Exception as e:  # noqa: BLE001
        return f"vlm_err:{type(e).__name__}"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# In the partitioned setup each drone owns its world and spawns at (0,0), so
# SPAWN_*=0. In a single shared world drones spawn at different corners; the
# drone's local NED origin = its spawn world pos, so cell<->NED must subtract it
# to keep ONE shared field grid across all drones.
SPAWN_X = float(os.environ.get("SPAWN_X", "0"))
SPAWN_Y = float(os.environ.get("SPAWN_Y", "0"))
# a shared-world drone (INSTANCE>0) launched WITHOUT explicit SPAWN_* is the
# classic silent-geometry bug (grid shifted by the spawn offset -> off-field
# flight + grey frames) — say it loudly at startup instead of flying it
if "SPAWN_X" not in os.environ and int(os.environ.get("INSTANCE", "0") or 0) > 0:
    print("[bridge] WARN: INSTANCE>0 without SPAWN_X/Y in env — shared-world "
          "cell<->NED will be shifted by this drone's spawn offset "
          "(pass SPAWN_X/SPAWN_Y, see scripts/city_real_full.sh)", flush=True)


def cell_to_ned(cx, cy):
    return (ORIGIN + float(cx) * CELL - SPAWN_X, ORIGIN + float(cy) * CELL - SPAWN_Y)


def ned_to_cell(x, y):
    return [int(round((x + SPAWN_X - ORIGIN) / CELL)),
            int(round((y + SPAWN_Y - ORIGIN) / CELL))]


def load_map() -> dict:
    try:
        return json.loads((FIXTURES / SCENARIO / "map.json").read_text())
    except Exception:
        return {}


# ---- gz camera capture (partition-aware; GZ_PARTITION set in this process) ----
_cam_lock = threading.Lock()
_last_img = {"png": None, "ts": 0.0}


def _rgb_to_png(path: Path, w: int, h: int, data: bytes) -> None:
    raw = b"".join(b"\x00" + data[y * w * 3:(y + 1) * w * 3] for y in range(h))

    def chunk(tag, d):
        return struct.pack(">I", len(d)) + tag + d + struct.pack(">I", zlib.crc32(tag + d) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def _save_thumb(src_png: Path, dst_jpg: Path) -> bool:
    """Downscale the nadir PNG to a small JPEG for the dashboard preview, keeping
    the CENTRAL crop = the cell directly under the drone (the wide FOV also images
    neighbour cells + building sides). PIL is present in the sverk image;
    best-effort (a failure just means no preview)."""
    try:
        from PIL import Image
        im = Image.open(src_png)
        if 0 < PHOTO_CROP < 1:                       # keep the central nadir cell
            w, h = im.size
            cw, ch = int(w * PHOTO_CROP), int(h * PHOTO_CROP)
            l, t = (w - cw) // 2, (h - ch) // 2
            im = im.crop((l, t, l + cw, t + ch))
        im.thumbnail((THUMB_MAX, THUMB_MAX))
        im.convert("RGB").save(dst_jpg, "JPEG", quality=THUMB_Q, optimize=True)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[bridge {AGENT}] thumb err: {e}", flush=True)
        return False


class Camera:
    """Latest downward frame. Two backends:
    gz (SITL) — подписка на gz-топик модели; sverk (реальный борт) — кадр по
    запросу через sverk_interfaces image (/camera_1/image_raw), тот же фасад,
    которым летим. Выбор автоматический: нет gz → пробуем sverk."""
    def __init__(self):
        self.ok = False
        self.w = self.h = 0
        self.buf = None
        self.mode = "none"
        self._img = None  # standalone image facade (when FLIGHT not connected)
        try:
            from gz.transport13 import Node
            from gz.msgs10.image_pb2 import Image
            self._Image = Image
            self.node = Node()
            self.node.subscribe(Image, IMG_TOPIC, self._cb)
            self.ok = True
            self.mode = "gz"
        except Exception as e:
            if BACKEND == "sverk":
                # пробуем свой image-фасад (независимо от flight controller)
                try:
                    import sverk_interfaces
                    self._img = sverk_interfaces.init(
                        Nodename=f"openclaw_cam_{INSTANCE}",
                        offboard_namespace=f"/px4_{INSTANCE}",
                        fcu_namespace=f"/px4_{INSTANCE}/fmu_control",
                    )
                    self.ok = True
                    self.mode = "sverk"
                    print(f"[bridge {AGENT}] camera: onboard via own sverk_interfaces "
                          f"(/camera_1/image_raw)", flush=True)
                except Exception as e2:
                    print(f"[bridge {AGENT}] camera unavailable: gz={e}, "
                          f"sverk={e2}", flush=True)
            else:
                print(f"[bridge {AGENT}] camera unavailable: {e}", flush=True)

    def _cb(self, msg):
        with _cam_lock:
            self.w, self.h, self.buf = msg.width, msg.height, bytes(msg.data)

    def _snap_sverk(self, path: Path) -> bool:
        try:
            msg = FLIGHT.d.picture(timeout=3.0)
            if msg is None:
                return False
            w, h, enc = int(msg.width), int(msg.height), str(msg.encoding)
            import numpy as np
            a = np.frombuffer(bytes(msg.data), dtype=np.uint8)
            a = a.reshape(h, int(msg.step))[:, :w * 3].reshape(h, w, 3)
            if enc == "bgr8":
                a = a[:, :, ::-1]                  # BGR -> RGB
            elif enc != "rgb8":
                print(f"[bridge {AGENT}] camera: encoding {enc} не поддержан",
                      flush=True)
                return False
            _rgb_to_png(path, w, h, a.tobytes())
            return True
        except Exception as e:  # noqa: BLE001
            print(f"[bridge {AGENT}] camera snap err: {e}", flush=True)
            return False

    def snap(self, path: Path) -> bool:
        if self.mode == "sverk":
            return self._snap_sverk(path)
        with _cam_lock:
            w, h, buf = self.w, self.h, self.buf
        if not buf or w == 0:
            return False
        try:
            _rgb_to_png(path, w, h, buf[:w * h * 3])
            return True
        except Exception:
            return False


# ---- cv2 ArUco localisation (independent reality-check of drone position) ------
# The ROS2 aruco->EKF flight path can be unstable, so we do NOT navigate by it;
# instead a persistent cv2 detector reads each camera frame and reports which
# marker/cell is under the drone. Persistent = imports cv2 + the map ONCE, so
# every probe is a fast stdin/stdout round-trip (not a ~1s subprocess spawn).
import subprocess, threading
ARUCO_LIB = os.environ.get("ARUCO_LIB", "/tmp/cvlib")
ARUCO_SCRIPT = os.environ.get("ARUCO_SCRIPT", "/tmp/aruco_cell.py")
ARUCO_ON = (os.environ.get("ARUCO_NAV", "1") not in ("0", "", "false", "no")
            and Path(ARUCO_SCRIPT).exists())


class ArucoService:
    """One long-running aruco detector process, queried over stdin/stdout."""
    def __init__(self):
        self.proc = None
        self.lock = threading.Lock()
        if not ARUCO_ON:
            return
        try:
            env = dict(os.environ, PYTHONPATH=ARUCO_LIB)
            self.proc = subprocess.Popen(["python3", ARUCO_SCRIPT, "--service"],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         text=True, env=env, bufsize=1)
            self.proc.stdout.readline()  # READY
            print(f"[bridge {AGENT}] aruco reality-check service up", flush=True)
        except Exception as e:
            print(f"[bridge {AGENT}] aruco service failed: {e}", flush=True)
            self.proc = None

    def probe(self, path):
        if not self.proc:
            return None
        with self.lock:
            try:
                self.proc.stdin.write(str(path) + "\n"); self.proc.stdin.flush()
                line = self.proc.stdout.readline()
                return json.loads(line) if line else None
            except Exception:
                return None


ARUCO = ArucoService()


def aruco_probe(cam):
    """Snap the camera, return {cell,on_field,n} — the drone's REAL cell from the
    markers it sees (drift-immune). on_field=False => it is off the marker map.
    Реальный борт (нет cv2-сервиса): состояние берём у БОРТОВОГО aruco-стека
    (aruco_det_loc: /aruco/det/markers + /aruco/loc/pose_cov) через фасад."""
    if ARUCO_ON and ARUCO.proc:
        tmp = ARTIFACTS / f"{AGENT}-aruco.png"
        if not cam.snap(tmp):
            return None
        return ARUCO.probe(tmp)
    if BACKEND == "sverk" and FLIGHT.connected:
        try:
            ids, pose = FLIGHT.d.aruco_onboard()
        except Exception as e:  # noqa: BLE001
            print(f"[bridge {AGENT}] onboard aruco err: {e}", flush=True)
            return None
        cell = None
        if pose is not None:
            # как считает полёт: north=ENU y -> cx, east=ENU x -> cy (знаки осей
            # мата сверяются на стенде вместе с полётными)
            cell = ned_to_cell(pose[1], pose[0])
        return {"cell": cell, "on_field": bool(ids), "n": len(ids)}
    return None


# ---- flight controller (one real PX4 drone) -----------------------------------
class Flight:
    def __init__(self):
        self.d = Drone(INSTANCE)
        self.connected = self.d.connect(timeout=25)
        if self.connected:
            self.d.start()   # control thread runs; drone stays LANDED until first move
            print(f"[bridge {AGENT}] flight ctrl on inst {INSTANCE} (port {self.d.port}) — landed, waiting for command", flush=True)
        else:
            print(f"[bridge {AGENT}] NO MAVLINK on inst {INSTANCE}", flush=True)

    def move_cell(self, cx, cy, block=True) -> list:
        cx, cy = int(cx), int(cy)
        if not self.d.flying:               # first command -> arm + climb to alt
            self.d.takeoff(z=ALT)
            t0 = time.time()
            while time.time() - t0 < 18 and self.d.rel_alt() < ALT * 0.7:
                time.sleep(0.4)
        nx, ny = cell_to_ned(cx - CAM_OFFX, cy - CAM_OFFY)
        self.d.goto(nx, ny, z=ALT)
        if block:
            t0 = time.time()
            while time.time() - t0 < REACH_TIMEOUT and not self.d.reached():
                time.sleep(0.3)
        # aruco correction — LIGHT: one probe. If the drone drifted OFF the marker
        # map (the failure that broke far-verifier votes), pull back toward the
        # target's world position and re-probe once. On-field sweeps skip straight
        # through (no per-cell servoing => the survey stays fast).
        if ARUCO_ON:
            a = aruco_probe(CAM)
            if a and not a.get("on_field"):
                self.d.tx += (cx - a["cell"][0]) * CELL if a.get("cell") else (nx - self.d.tx)
                self.d.ty += (cy - a["cell"][1]) * CELL if a.get("cell") else (ny - self.d.ty)
                self.d.goto(nx, ny, z=ALT)
                t0 = time.time()
                while time.time() - t0 < 10 and not self.d.reached():
                    time.sleep(0.3)
        return self.pose_cell()

    def set_cell(self, cx, cy):
        """Tell the drone which cell it is ACTUALLY over (arbitrary start /
        kill-switch recovery): recalibrate the spawn offset so the current
        physical position maps to (cx,cy). Everything downstream (pose, move,
        home) then works from this cell — the scenario can start anywhere."""
        global SPAWN_X, SPAWN_Y
        SPAWN_X = ORIGIN + int(cx) * CELL - self.d.pos[0]
        SPAWN_Y = ORIGIN + int(cy) * CELL - self.d.pos[1]
        return self.pose_cell()

    def home_cell(self):
        return ned_to_cell(0.0, 0.0)      # spawn point == this drone's NED origin

    def land_home(self):
        """Fly back to the start cell, then land there."""
        if self.d.airborne():
            h = self.home_cell()
            self.move_cell(h[0], h[1])
        self.d.land()

    def aruco(self):
        return aruco_probe(CAM)

    def pose_cell(self) -> list:
        # EKF is fast; report the imaged cell. (aruco is used for off-field
        # correction in move_cell + on_field gating in analyze, not every pose.)
        a2 = ned_to_cell(self.d.pos[0], self.d.pos[1])
        return [a2[0] + CAM_OFFX, a2[1] + CAM_OFFY]

    def rel_alt(self) -> float:
        return self.d.rel_alt()


FLIGHT = Flight()
CAM = Camera()
MAP = load_map()


def cell_truth(cell) -> str:
    cx, cy = int(cell[0]), int(cell[1])
    fire = MAP.get("fire") or MAP.get("cargo")
    if isinstance(fire, list) and [int(fire[0]), int(fire[1])] == [cx, cy]:
        return "cargo"
    for d in MAP.get("decoys") or []:
        if isinstance(d, list) and [int(d[0]), int(d[1])] == [cx, cy]:
            return "decoy"
    return "empty"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("content-length", 0))
        return json.loads(self.rfile.read(n).decode()) if n else {}

    def do_GET(self):
        if self.path == "/healthz":
            return self._json(200, {"ok": True, "agent": AGENT, "instance": INSTANCE,
                                    "connected": FLIGHT.connected})
        if urlparse(self.path).path == "/frame":       # /frame?t=... от <img>
            # свежий кадр камеры как PNG — для живого просмотра в браузере
            tmp = ARTIFACTS / f"{AGENT}-live.png"
            if not CAM.snap(tmp):
                return self._json(503, {"error": "no frame"})
            data = tmp.read_bytes()
            self.send_response(200)
            self.send_header("content-type", "image/png")
            self.send_header("content-length", str(len(data)))
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == "/describe":
            # что VLM видит в кадре ПРЯМО СЕЙЧАС (для выбора нового объекта-цели)
            tmp = ARTIFACTS / f"{AGENT}-live.png"
            if not CAM.snap(tmp):
                return self._json(503, {"error": "no frame"})
            _, _, txt, _ = vlm_fire(tmp.read_bytes())
            desc = vlm_describe(tmp.read_bytes())
            return self._json(200, {"see": desc, "target": VLM_TARGET,
                                    "verdict": txt, "ts": now_iso()})
        if self.path == "/vision":
            html = ("<!doctype html><meta charset=utf-8><title>drone vision</title>"
                    "<body style='background:#0d1117;color:#c9d1d9;font:14px system-ui;"
                    "margin:0;padding:12px'><h3 style='margin:4px 0'>\U0001F441 "
                    f"{AGENT} — живой кадр + глаза VLM</h3>"
                    "<div style='margin:6px 0'>цель: <input id=t placeholder='что искать' "
                    "style='background:#161b22;color:#c9d1d9;border:1px solid #30363d;"
                    "border-radius:6px;padding:4px 8px;width:160px'> "
                    "<input id=td placeholder='как выглядит (для VLM)' "
                    "style='background:#161b22;color:#c9d1d9;border:1px solid #30363d;"
                    "border-radius:6px;padding:4px 8px;width:280px'> "
                    "<button onclick='setT()' style='background:#1b222c;color:#c9d1d9;"
                    "border:1px solid #30363d;border-radius:6px;padding:4px 12px;"
                    "cursor:pointer'>сменить цель</button> "
                    "<b id=cur style='color:#3fb950'></b></div>"
                    "<img id=f style='max-width:96vw;max-height:60vh;border-radius:8px'>"
                    "<pre id=d style='white-space:pre-wrap;background:#161b22;"
                    "padding:10px;border-radius:8px'>жду VLM…</pre><script>"
                    f"cur.textContent={json.dumps(VLM_TARGET)};"
                    "setInterval(()=>{f.src='/frame?t='+Date.now()},1500);"
                    "async function setT(){const r=await(await fetch('/target',{method:'POST',"
                    "body:JSON.stringify({target:t.value,desc:td.value})})).json();"
                    "cur.textContent=r.target;}"
                    "async function poll(){try{const r=await(await fetch('/describe')).json();"
                    "cur.textContent=r.target;"
                    "d.textContent='ВИЖУ: '+(r.see||'—')+'\\n\\nВЕРДИКТ ПО ЦЕЛИ ('+r.target+'): '"
                    "+(r.verdict||'—')+'\\n'+r.ts;}catch(e){d.textContent='err '+e}"
                    "setTimeout(poll,6000)}poll();</script>")
            data = html.encode()
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == "/pose":
            xy = FLIGHT.pose_cell()
            resp = {"xy": xy, "heading": 0.0, "alt": round(FLIGHT.rel_alt(), 2)}
            a = FLIGHT.aruco()          # independent cv2-aruco reality-check
            if a is not None:
                raw = a.get("cell")
                ac = [raw[0] - ARUCO_OFFX, raw[1] - ARUCO_OFFY] if raw else None
                resp["aruco_cell"] = ac              # calibrated to the drone's cell
                resp["on_field"] = a.get("on_field")
                resp["markers"] = a.get("n", 0)
                # True when the camera CONFIRMS the reported cell (else: off-field
                # or EKF/aruco mismatch -> position not trustworthy)
                resp["reality_ok"] = bool(a.get("on_field") and ac == xy)
            return self._json(200, resp)
        if self.path.startswith("/artifact/"):
            f = ARTIFACTS / os.path.basename(urlparse(self.path).path)
            if f.exists():
                data = f.read_bytes()
                ct = "image/jpeg" if f.suffix.lower() in (".jpg", ".jpeg") else "image/png"
                self.send_response(200)
                self.send_header("content-type", ct)
                self.send_header("content-length", str(len(data)))
                self.send_header("cache-control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(data)
                return
            return self._json(404, {"error": "no artifact"})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        try:
            body = self._body()
        except Exception as e:
            return self._json(400, {"error": f"bad json: {e}"})
        p = self.path
        if p == "/target":
            # смена цели VLM на лету (со страницы /vision): {"target": "...", "desc": "..."}
            set_target(str(body.get("target") or ""), str(body.get("desc") or ""))
            return self._json(200, {"ok": True, "target": VLM_TARGET,
                                    "desc": VLM_TARGET_DESC})
        if p == "/led":
            return self._json(200, {"ok": True, "effect": body.get("effect", "fill")})
        if p == "/land":
            if body.get("home"):
                FLIGHT.land_home()      # return to start cell then land
            else:
                FLIGHT.d.land()
            return self._json(200, {"ok": True, "landed": True, "pose": FLIGHT.pose_cell()})
        if p == "/pause":          # battery-swap: land + freeze
            FLIGHT.d.pause()
            return self._json(200, {"ok": True, "paused": True})
        if p == "/set_cell":       # arbitrary start / kill-switch: set current cell
            c = body.get("cell")
            if not (isinstance(c, list) and len(c) == 2):
                return self._json(400, {"error": "cell must be [x,y]"})
            return self._json(200, {"ok": True, "cell": FLIGHT.set_cell(c[0], c[1])})
        if p == "/takeoff":        # resume / lift off from ground
            FLIGHT.d.takeoff(z=ALT)
            return self._json(200, {"ok": True, "landed": False, "pose": FLIGHT.pose_cell()})
        if p == "/move":
            to = body.get("to")
            if not (isinstance(to, list) and len(to) == 2):
                return self._json(400, {"error": "to must be [x,y]"})
            pose = FLIGHT.move_cell(to[0], to[1])
            return self._json(200, {"pose": pose, "ok": True})
        if p == "/photograph":
            return self._photograph(body)
        if p == "/analyze":
            return self._analyze(body)
        if p == "/navigate":
            return self._navigate(body)
        return self._json(404, {"error": "not found"})

    def _valid_cell(self, cell) -> bool:
        gs = MAP.get("grid_size") or [6, 6]
        return (isinstance(cell, list) and len(cell) == 2
                and 0 <= int(cell[0]) < int(gs[0]) and 0 <= int(cell[1]) < int(gs[1]))

    def _photograph(self, body):
        cell = body.get("cell")
        if not self._valid_cell(cell):
            return self._json(400, {"error": "invalid cell"})
        cx, cy = int(cell[0]), int(cell[1])
        dst = ARTIFACTS / f"{AGENT}-cell-{cx}-{cy}.png"
        if PHOTO_SETTLE > 0:                 # level out (nadir) before the shot
            time.sleep(PHOTO_SETTLE)
        got = CAM.snap(dst)
        if not got:                          # frame not ready yet -> one brief retry
            time.sleep(0.6)
            got = CAM.snap(dst)
        if got:                              # small JPEG preview alongside the PNG
            _save_thumb(dst, dst.with_suffix(".jpg"))
        rel = f"http://127.0.0.1:{PORT}/artifact/{dst.name}" if got else ""
        return self._json(200, {"image_path": rel, "ts": now_iso(), "cell": [cx, cy],
                                "captured": got})

    def _analyze(self, body):
        cell = body.get("cell")
        if not self._valid_cell(cell):
            return self._json(400, {"error": "invalid cell"})
        cx, cy = int(cell[0]), int(cell[1])
        close = bool(body.get("close_look"))
        # REAL detection: descend to inspect (narrow the camera FOV to ~1 cell so
        # the fire only fills the frame when the drone is truly over its cell),
        # snap the frame, ask gemma4-vlm, then climb back to survey altitude.
        is_fire, conf, reason, pos = None, 0.0, "", "none"
        if VLM_ON:
            # let the drone settle over its cell so drift doesn't jitter the frame
            time.sleep(ANALYZE_SETTLE)
            tmp = ARTIFACTS / f"{AGENT}-analyze-{cx}-{cy}.png"
            # Multi-look: hover drift means a fire directly below may read as an
            # edge on one frame and centre on the next. Sample up to 3 frames but
            # ONLY keep looking while a fire is in view but not yet centred (empty
            # cells cost a single call). Any 'centre' look => the fire is here.
            dirs = []
            for look in range(3):
                if look:
                    time.sleep(1.2)
                if not CAM.snap(tmp):
                    break
                is_fire, conf, reason, pos = vlm_fire(tmp.read_bytes())
                if is_fire is None or is_fire or pos == "none":
                    break            # done: centred, VLM down, or clearly empty
                dirs.append(pos)     # fire seen but off-centre -> look again
            if not is_fire and dirs:
                pos = max(set(dirs), key=dirs.count)   # dominant edge direction
                reason = f"fire off-centre ({pos}); {reason}"
        if is_fire is None:  # VLM unavailable -> deterministic map fallback
            truth = cell_truth(cell)
            is_fire = (truth == "cargo")
            conf = (0.9 if is_fire else 0.95)
            reason, pos = f"fallback:map({truth})", ("center" if is_fire else "none")
        out = {"cargo": bool(is_fire), "confidence": conf,
               "label": "fire" if is_fire else "clear",
               "vlm": reason, "fire_pos": pos, "cell": [cx, cy], "close_look": close}
        return self._json(200, out)

    def _navigate(self, body):
        """Rover-style cell-by-cell drive: A* over the occupancy grid, fly the
        drone through each waypoint. Streams {pose,progress} then {status}."""
        frm, to, grid = body.get("from"), body.get("to"), body.get("grid")
        if not (isinstance(frm, list) and isinstance(to, list) and isinstance(grid, list)):
            return self._json(400, {"error": "from/to/grid required"})
        from mock import astar  # reuse the A* implementation
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
            FLIGHT.move_cell(c[0], c[1])
            emit({"pose": FLIGHT.pose_cell(), "progress": round((i + 1) / n, 3)})
        emit({"status": "arrived", "pose": FLIGHT.pose_cell()})


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[bridge {AGENT}] REAL on :{PORT} inst={INSTANCE} model={MODEL} "
          f"cam={'ok' if CAM.ok else 'no'} connected={FLIGHT.connected}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
