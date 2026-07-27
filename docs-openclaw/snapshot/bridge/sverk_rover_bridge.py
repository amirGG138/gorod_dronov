#!/usr/bin/env python3
"""REAL rover bridge — same HTTP contract as bridge/mock.py / rover_bridge.py,
but drives the physical sverk_rover (Raspberry Pi + Nav2) through its
rover_control_api v1 (github.com/wodocanal/sverk_rover, :8767).

The LLM agents keep using BridgeClient (/move /navigate /pose /dwell /led ...)
— only BRIDGE_URL points here. Cells are mapped onto the rover's SLAM map with
a calibratable grid anchor (map coords of cell [0,0] + grid yaw + cell size).

  POST /move      {to:[cx,cy], grid?}   -> A* over grid -> Nav2 goal per cell
  POST /navigate  {from,to,grid}        -> ndjson stream {pose,progress}...{status}
  GET  /pose                            -> {xy:[cx,cy], heading, map:{x,y,yaw_deg}}
  POST /dwell     {seconds, led}        -> real wall-clock hold + evidence
  POST /led /land /takeoff              -> acknowledged no-ops (no LED over v1 API)
  POST /initial_pose {cell,[yaw_deg]}   -> AMCL re-localization at a grid cell
  POST /stop                            -> cancel the active Nav2 goal
  GET|POST /config                      -> view / retune grid mapping at runtime

Control leases (the rover API requires an exclusive lease for motion) are taken
per command and released right after, so a human operator or another agent can
grab the rover between our moves.

Env: PORT(9006) ROVER_API(http://192.168.4.9:8767) CELL_SIZE(0.6)
     MAP_X0 MAP_Y0 (map metres of cell [0,0] centre) MAP_YAW_DEG(0)
     GRID_NX GRID_NY (field bounds, demo/validation) GOAL_TIMEOUT(45)
     CLIENT_ID(openclaw-bridge) MAP_LABEL('' = whatever map is loaded)
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mock import astar  # noqa: E402  (same A* the mock/gazebo bridges use)

PORT = int(os.environ.get("PORT", "9006"))
API = os.environ.get("ROVER_API", "http://192.168.4.9:8767").rstrip("/")
# rover web gateway (rover_web :8765): the SLAM map list + rendered map image
WEB = os.environ.get("ROVER_WEB",
                     API.rsplit(":", 1)[0] + ":8765").rstrip("/")
CLIENT_ID = os.environ.get("CLIENT_ID", "openclaw-bridge")
GOAL_TIMEOUT = float(os.environ.get("GOAL_TIMEOUT", "45"))
# Nav2 часто ДОЕЗЖАЕТ, но в конце не добивает точный допуск позы и репортит
# aborted («nav aborted at:[2,1] target:[2,1]»). Если факт-поза ближе допуска —
# считаем прибытием.
GOAL_TOL = float(os.environ.get("GOAL_TOL", "0.22"))

# grid <-> map calibration (runtime-tunable via /config)
CFG = {
    "cell_size": float(os.environ.get("CELL_SIZE", "0.6")),
    "map_x0": float(os.environ.get("MAP_X0", "0.0")),
    "map_y0": float(os.environ.get("MAP_Y0", "0.0")),
    "map_yaw_deg": float(os.environ.get("MAP_YAW_DEG", "0.0")),
    "grid_nx": int(os.environ.get("GRID_NX", "6")),
    "grid_ny": int(os.environ.get("GRID_NY", "6")),
    "map_label": os.environ.get("MAP_LABEL", ""),
}
_led = {"effect": "off"}


def cell_to_map(cx: float, cy: float) -> tuple[float, float]:
    th = math.radians(CFG["map_yaw_deg"])
    c, s = math.cos(th), math.sin(th)
    gx, gy = cx * CFG["cell_size"], cy * CFG["cell_size"]
    return CFG["map_x0"] + gx * c - gy * s, CFG["map_y0"] + gx * s + gy * c


def map_to_cell(mx: float, my: float) -> list[int]:
    th = math.radians(CFG["map_yaw_deg"])
    c, s = math.cos(th), math.sin(th)
    dx, dy = mx - CFG["map_x0"], my - CFG["map_y0"]
    gx = (dx * c + dy * s) / CFG["cell_size"]
    gy = (-dx * s + dy * c) / CFG["cell_size"]
    return [int(round(gx)), int(round(gy))]


# ---- rover control API v1 client ----------------------------------------
class RoverApiError(RuntimeError):
    pass


def _api(path: str, body: dict | None = None, lease: str = "") -> dict:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"content-type": "application/json",
                 **({"X-Control-Lease": lease} if lease else {})},
        method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode())
        except Exception:  # noqa: BLE001
            err = {}
        raise RoverApiError(err.get("message") or f"HTTP {e.code}") from e
    except Exception as e:  # noqa: BLE001
        raise RoverApiError(str(e)) from e


class Lease:
    """Exclusive control lease, held only for the duration of one command.
    The rover API expires leases after ~5s, so a renew thread runs while held."""

    def __init__(self) -> None:
        self.id = ""
        self._stop = threading.Event()

    def __enter__(self) -> "Lease":
        self.id = _api("/v1/lease/acquire", {"client_id": CLIENT_ID})["lease_id"]
        self._stop.clear()
        threading.Thread(target=self._renew, daemon=True).start()
        return self

    def _renew(self) -> None:
        while not self._stop.wait(2.0):
            try:
                _api("/v1/lease/renew", {}, lease=self.id)
            except RoverApiError:
                return

    def __exit__(self, *exc) -> None:
        self._stop.set()
        try:
            _api("/v1/lease/release", {}, lease=self.id)
        except RoverApiError:
            pass


def rover_state() -> dict:
    return _api("/v1/state")


# ---- one motion at a time: пока едет goto/move, вторая команда получает
# ЧЕСТНЫЙ 409 («едет к цели, N сек — жми stop»), а не мутный lease-отказ
# rover api; /stop рвёт активную цель через ЕЁ же lease.
class BusyError(RuntimeError):
    pass


_busy = {"lease": None, "since": 0.0, "what": "", "abort": False}
_busy_lock = threading.Lock()


class _Motion:
    def __init__(self, what: str):
        self.what = what
        self.lease = None

    def __enter__(self) -> Lease:
        with _busy_lock:
            if _busy["lease"] is not None:
                raise BusyError(
                    f"занят: {_busy['what']} уже {int(time.time() - _busy['since'])}с "
                    "— дождись или жми stop")
            self.lease = Lease().__enter__()
            _busy.update(lease=self.lease, since=time.time(),
                         what=self.what, abort=False)
        return self.lease

    def __exit__(self, *exc) -> None:
        with _busy_lock:
            _busy.update(lease=None, what="", abort=False)
        self.lease.__exit__(*exc)


def _wait_nav_ready(timeout: float = 25.0) -> str | None:
    """После рестарта профиля Nav2 поднимается ~40с, AMCL пуст. Подождать
    готовности вместо мгновенного отказа; вернуть текст ошибки или None."""
    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout:
        try:
            st = rover_state()
            pose_ok = (st.get("pose") or {}).get("frame_id") == "map"
            if st.get("nav2_ready") and pose_ok:
                return None
            last = ("нет amcl-позы — задай initial pose (📍)"
                    if st.get("nav2_ready") else "nav2 ещё поднимается")
        except RoverApiError as e:
            last = f"control api: {e}"
        time.sleep(1.5)
    return f"не готов к навигации: {last}"


def _goal_body(mx: float, my: float, yaw_deg: float) -> dict:
    body = {"request_id": str(uuid.uuid4()), "x": mx, "y": my, "yaw_deg": yaw_deg}
    label = CFG["map_label"] or rover_state().get("map", {}).get("label")
    if label:
        body["map_label"] = label
    return body


def drive_to_point(lease: Lease, mx: float, my: float, yaw_deg: float = 0.0) -> dict:
    """Nav2 goal to map metres (mx,my) + ОДИН авто-ретрай на aborted/failed:
    на нагруженном Pi сервисные вызовы Nav2 флакучие — цель может отвалиться
    без причины и пройти со второго раза (наблюдалось живьём)."""
    def close_enough() -> bool:
        try:
            _, pose = current_cell()
            return (pose.get("frame_id") == "map"
                    and math.hypot(pose["x"] - mx, pose["y"] - my) <= GOAL_TOL)
        except RoverApiError:
            return False

    ns = _drive_once(lease, mx, my, yaw_deg)
    if ns.get("state") in ("aborted", "failed") and not _busy.get("abort"):
        if close_enough():
            return {"state": "succeeded", "note": "arrived_within_tolerance"}
        time.sleep(1.0)
        ns = _drive_once(lease, mx, my, yaw_deg)
        ns["retried"] = True
        if ns.get("state") in ("aborted", "failed") and close_enough():
            return {"state": "succeeded", "note": "arrived_within_tolerance",
                    "retried": True}
    return ns


_NAV_ACTIVE = ("sending", "accepted", "navigating", "canceling")


def _clear_active_goal(lease: Lease, tries: int = 10) -> bool:
    """Осиротевшая цель (рестарт бриджа посреди поездки / чужая команда)
    блокирует новые: «a navigation goal is already active». Отменить и
    ДОЖДАТЬСЯ, пока статус реально перестанет быть активным."""
    for i in range(tries):
        ns = _api("/v1/navigation/status")
        st = ns.get("state")
        if st not in _NAV_ACTIVE:
            return True
        if st != "canceling":   # canceling: отмена уже идёт, повторная не поможет
            try:
                _api("/v1/navigation/cancel",
                     {"request_id": str(uuid.uuid4())}, lease=lease.id)
            except RoverApiError:
                pass
        time.sleep(0.8)
    # застряли в canceling — bt_navigator подвис в halt; жёсткий лечебный путь:
    # передёрнуть его lifecycle (deactivate/activate), это сбрасывает handle
    try:
        _ssh(_ros_cmd("timeout 15 ros2 lifecycle set /bt_navigator deactivate; "
                      "sleep 1; timeout 15 ros2 lifecycle set /bt_navigator activate"),
             timeout=60)
        time.sleep(2.0)
        return _api("/v1/navigation/status").get("state") not in _NAV_ACTIVE
    except Exception:  # noqa: BLE001
        return False


def _drive_once(lease: Lease, mx: float, my: float, yaw_deg: float = 0.0) -> dict:
    """One Nav2 goal; poll until OUR goal settles. The status endpoint keeps
    reporting the PREVIOUS goal's terminal state for a moment after a new goal
    is sent — match by request_id or the poll races."""
    if not _clear_active_goal(lease):
        return {"state": "failed",
                "message": "цель зависла в canceling (баг control API) — "
                           "жми «⚡ Оживить Nav2», он перезапустит борт и всё поднимет"}
    body = _goal_body(mx, my, yaw_deg)
    _api("/v1/navigation/goal", body, lease=lease.id)
    t0 = time.time()
    while time.time() - t0 < GOAL_TIMEOUT:
        time.sleep(0.5)
        if _busy.get("abort"):
            _api("/v1/navigation/cancel", {"request_id": str(uuid.uuid4())},
                 lease=lease.id)
            return {"state": "stopped", "message": "остановлен оператором (stop)"}
        ns = _api("/v1/navigation/status")
        if (ns.get("request_id") == body["request_id"]
                and ns.get("state") in ("succeeded", "failed", "canceled", "aborted")):
            return ns
    _api("/v1/navigation/cancel", {"request_id": str(uuid.uuid4())}, lease=lease.id)
    return {"state": "timeout"}


def drive_to_cell(lease: Lease, cx: int, cy: int, yaw_deg: float = 0.0) -> dict:
    mx, my = cell_to_map(cx, cy)
    return drive_to_point(lease, mx, my, yaw_deg)


# ---- teleop (mapping drives / nudges): stream velocity commands ----------
_teleop_seq = {"n": 0}
TELEOP_MAX_SEC = 5.0


def teleop_burst(lease: Lease, vx: float, vy: float, wz: float, dur: float) -> int:
    """Stream /v1/teleop at ~5 Hz for `dur` seconds (ttl 600ms keeps the base
    moving between packets; seq must strictly increase per lease)."""
    sent = 0
    t_end = time.time() + max(0.1, min(dur, TELEOP_MAX_SEC))
    while time.time() < t_end:
        _teleop_seq["n"] += 1
        _api("/v1/teleop", {"request_id": str(uuid.uuid4()), "seq": _teleop_seq["n"],
                            "linear_x": vx, "linear_y": vy, "angular_z": wz,
                            "ttl_ms": 400}, lease=lease.id)  # API cap: ttl <= 500ms
        sent += 1
        time.sleep(0.15)
    return sent


def _web_drive_push(x: float, y: float, z: float) -> None:
    """One velocity packet to the rover web gateway (/api/drive/command ->
    /cmd_vel; its deadman is 0.25s, so somebody must keep repeating)."""
    req = urllib.request.Request(
        WEB + "/api/drive/command",
        data=json.dumps({"linear_x": x, "linear_y": y, "angular_z": z}).encode(),
        headers={"content-type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=4).read()


def _web_drive_burst(vx: float, vy: float, wz: float, dur: float) -> int:
    sent = 0
    t_end = time.time() + max(0.1, min(dur, TELEOP_MAX_SEC))
    while time.time() < t_end:
        _web_drive_push(vx, vy, wz)
        sent += 1
        time.sleep(0.15)
    _web_drive_push(0.0, 0.0, 0.0)
    return sent


# ---- teleop STREAM: плавная езда с клавиатуры. Браузер только продлевает
# дедлайн (лёгкий HTTP каждые ~250мс), а фоновый воркер бриджа гонит текущую
# скорость в шлюз с 8 Гц без пауз и без стопов между бурстами — рывков нет.
# Дедлайн прошёл (клавишу отпустили / вкладка умерла) -> один стоп, воркер спит.
_stream = {"v": (0.0, 0.0, 0.0), "until": 0.0}
_stream_lock = threading.Lock()
_stream_thread: dict = {"t": None}


def _stream_worker() -> None:
    while True:
        with _stream_lock:
            v, until = _stream["v"], _stream["until"]
        if time.time() >= until:
            try:
                _web_drive_push(0.0, 0.0, 0.0)
            except Exception:  # noqa: BLE001
                pass
            with _stream_lock:
                if time.time() >= _stream["until"]:
                    _stream_thread["t"] = None
                    return
            continue
        try:
            _web_drive_push(*v)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.12)


def stream_set(vx: float, vy: float, wz: float, dur: float) -> None:
    with _stream_lock:
        _stream["v"] = (vx, vy, wz)
        _stream["until"] = time.time() + max(0.1, min(dur, 2.0))
        t = _stream_thread["t"]
        if t is None or not t.is_alive():
            t = threading.Thread(target=_stream_worker, daemon=True)
            _stream_thread["t"] = t
            t.start()


# ---- SLAM mapping control over ssh (the control API has no mapping verbs):
# switch the bringup profile mapping<->full and save the map with the repo's
# own tool (ros2 run rover_navigation rover_map save <name>).
SSH_HOST = os.environ.get("ROVER_SSH_HOST", API.split("//", 1)[-1].split(":")[0])
SSH_USER = os.environ.get("ROVER_SSH_USER", "pi")
SSH_PASS = os.environ.get("ROVER_SSH_PASS", "raspberry")
_NAME_RE = __import__("re").compile(r"^[A-Za-z0-9_-]{1,32}$")


def _ssh(cmd: str, timeout: float = 40.0) -> tuple[int, str]:
    import paramiko
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(SSH_HOST, 22, SSH_USER, SSH_PASS, timeout=8,
              banner_timeout=8, auth_timeout=8)
    try:
        _, o, e = c.exec_command(cmd, timeout=timeout)
        out = o.read().decode(errors="replace") + e.read().decode(errors="replace")
        return o.channel.recv_exit_status(), out.strip()
    finally:
        c.close()


def _sudo(cmd: str) -> str:
    return f"echo {SSH_PASS} | sudo -S -p '' {cmd}"


def _ros_cmd(cmd: str) -> str:
    """Wrap a command with the rover's ROS env: setup.bash + the bringup env
    file (ROS_DOMAIN_ID=77 there — a bare ssh shell sits in domain 0 and sees
    NO topics)."""
    return ("bash -lc 'set -a; . /etc/default/rover-bringup 2>/dev/null; set +a; "
            "source /opt/ros/jazzy/setup.bash; "
            "source /home/pi/sverk_rover/install/setup.bash; "
            + cmd + "'")


def _set_profile(profile: str, launch_args: str = "") -> tuple[int, str]:
    return _ssh(
        _sudo(f"sed -i 's/^ROVER_PROFILE=.*/ROVER_PROFILE={profile}/' /etc/default/rover-bringup")
        + " && "
        + _sudo(f"sed -i 's|^ROVER_LAUNCH_ARGS=.*|ROVER_LAUNCH_ARGS={launch_args}|' /etc/default/rover-bringup")
        + " && " + _sudo("systemctl restart rover-bringup")
        + " && echo restarted-to-" + profile, timeout=60)


# Nav2 на нагруженном Pi стабильно НЕДОактивируется после рестарта bringup
# (bond timeout у lifecycle-менеджера): bt_navigator/planner повисают в
# inactive, и control API отвечает nav2_ready=true, а цели молча reject
# («Action server is inactive»). Дожимаем активацию per-node с ретраями.
_NAV2_NODES = ("map_server amcl planner_server controller_server "
               "smoother_server behavior_server bt_navigator waypoint_follower")


def _nav2_recover(retries: int = 3) -> dict:
    # ШАГ -1: control API мог НАВЕЧНО зависнуть в navigation=canceling
    # (cancel_goal_async по мёртвому handle не резолвится) — все новые цели
    # получают «a navigation goal is already active». Лечится только
    # рестартом bringup; дальше recover сам вернёт позу и активирует Nav2.
    restarted = False
    try:
        nav_st = (rover_state().get("navigation") or {}).get("state")
        if nav_st in _NAV_ACTIVE:
            with Lease() as lease:
                if not _clear_active_goal(lease, tries=6):
                    _ssh(_sudo("systemctl restart rover-bringup"), timeout=40)
                    restarted = True
                    time.sleep(45)
    except (RoverApiError, Exception):  # noqa: BLE001
        pass
    # ШАГ 0: без amcl-позы нет TF map->odom, а без него planner НЕ активируется
    # (курица-яйцо после каждого рестарта bringup). Если поза потеряна —
    # восстановить последнюю известную initial pose перед активацией.
    relocalized = False
    try:
        st = rover_state()
        if (st.get("pose") or {}).get("frame_id") != "map" and _last_pose:
            with Lease() as lease:
                _api("/v1/localization/initial-pose",
                     _goal_body(_last_pose["x"], _last_pose["y"],
                                _last_pose.get("yaw_deg", 0.0)), lease=lease.id)
            relocalized = True
            time.sleep(3.0)
    except RoverApiError:
        pass
    script = (
        f"for n in {_NAV2_NODES}; do "
        'st=$(timeout 8 ros2 lifecycle get /$n 2>/dev/null | tail -1); '
        'if [ "${st%% *}" != active ]; then echo "$n:activate"; '
        "timeout 20 ros2 lifecycle set /$n activate 2>&1 | tail -1; fi; done")
    log = []
    for i in range(retries):
        rc, out = _ssh(_ros_cmd(script), timeout=200)
        log.append(out.strip() or "all-active")
        if ":activate" not in out:
            return {"ok": True, "attempts": i + 1, "log": log,
                    "relocalized": relocalized, "bringup_restarted": restarted,
                    "note": "все ноды Nav2 активны"}
        time.sleep(4)
    rc, out = _ssh(_ros_cmd(
        f"for n in {_NAV2_NODES}; do echo -n \"$n: \"; "
        "timeout 8 ros2 lifecycle get /$n 2>&1 | tail -1; done"), timeout=150)
    return {"ok": ":activate" not in log[-1], "attempts": retries,
            "states": out.splitlines(), "log": log}


def _recover_later(delay: float = 50.0) -> None:
    """После смены профиля bringup стартует ~40с — потом добить активацию."""
    def work():
        time.sleep(delay)
        try:
            r = _nav2_recover()
            print(f"[sverk_rover_bridge] auto nav2 recover: {r.get('ok')} "
                  f"({r.get('attempts')} попыток)", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[sverk_rover_bridge] auto recover failed: {e}", flush=True)
    threading.Thread(target=work, daemon=True).start()


def mapping_action(body: dict) -> dict:
    act = str(body.get("action") or "status")
    if act == "status":
        rc, out = _ssh(
            "grep '^ROVER_PROFILE' /etc/default/rover-bringup; "
            "systemctl is-active rover-bringup; "
            "pgrep -c -f 'slam_toolbo[x]' || true; "  # [x] = не матчить сам pgrep
            "ls -la /var/lib/sverk-rover/maps/current/ 2>/dev/null | tail -n +2 | awk '{print $NF, $5}'")
        lines = out.splitlines()
        return {"ok": rc == 0, "profile": (lines[0].split("=", 1)[-1] if lines else "?"),
                "service": lines[1] if len(lines) > 1 else "?",
                "slam_running": bool(len(lines) > 2 and lines[2].strip().isdigit()
                                     and int(lines[2]) > 0),
                "map_files": lines[3:], "raw": out}
    if act == "start":
        rc, out = _set_profile("mapping")
        return {"ok": rc == 0, "detail": out,
                "note": "bringup перезапускается в профиль mapping (~40с); "
                        "nav2/control API временно недоступны, карта строится SLAM Toolbox "
                        "С НУЛЯ (достройка существующей — action:update)"}
    if act == "update":
        # ДОСТРОЙКА существующей карты: SLAM Toolbox продолжает с сохранённого
        # posegraph (maps/current/map) от ТЕКУЩЕЙ amcl-позы. Требует локализации.
        try:
            st = rover_state()
            p = st.get("pose") or {}
        except RoverApiError as e:
            return {"ok": False, "error": f"control api: {e} — "
                    "update стартует из режима навигации (нужна amcl-поза)"}
        if p.get("frame_id") != "map":
            return {"ok": False,
                    "error": "ровер не локализован (поза odom) — сначала initial pose"}
        x, y = float(p["x"]), float(p["y"])
        th = math.radians(float(p.get("yaw_deg", 0.0)))
        prm = "/home/pi/openclaw_slam_update.yaml"
        src = ("/home/pi/sverk_rover/install/rover_bringup/share/rover_bringup/"
               "config/navigation/slam_toolbox_params.yaml")
        rc, out = _ssh(
            f"cp {src} {prm} && "
            f"printf '    map_file_name: /var/lib/sverk-rover/maps/current/map\\n"
            f"    map_start_pose: [{x:.3f}, {y:.3f}, {th:.4f}]\\n' >> {prm}",
            timeout=20)
        if rc != 0:
            return {"ok": False, "error": f"params prep: {out[-400:]}"}
        rc, out = _set_profile("mapping", f"slam_params_file:={prm}")
        return {"ok": rc == 0, "detail": out,
                "note": f"достройка карты от позы ({x:.2f}, {y:.2f}); катай ровера "
                        "телеопом, прогресс — кнопкой «Сохранить карту»"}
    if act == "stop":
        rc, out = _set_profile("full")
        _recover_later()   # через ~50с добить lifecycle-активацию Nav2
        return {"ok": rc == 0, "detail": out,
                "note": "bringup возвращается в профиль full (~40с, Nav2 доактивируется "
                        "автоматически ещё ~30с); потом локализация (📍); если goto "
                        "всё же отвергается — кнопка «⚡ Оживить Nav2»"}
    if act == "recover":
        return _nav2_recover()
    if act == "save":
        name = str(body.get("name") or "")
        if not _NAME_RE.match(name):
            return {"ok": False, "error": "name: [A-Za-z0-9_-]{1,32} required"}
        rc, out = _ssh(_ros_cmd(f"ros2 run rover_navigation rover_map save {name}"),
                       timeout=90)
        return {"ok": rc == 0, "detail": out[-1500:]}
    return {"ok": False, "error": f"unknown action {act!r} (status|start|save|stop)"}


_last_pose: dict = {}   # последняя известная map-поза (переживает рестарты bringup)


def current_cell() -> tuple[list[int], dict]:
    st = rover_state()
    pose = st.get("pose") or {}
    if pose.get("frame_id") == "map":
        _last_pose.update(x=pose["x"], y=pose["y"],
                          yaw_deg=pose.get("yaw_deg", 0.0))
        return map_to_cell(pose["x"], pose["y"]), pose
    return [0, 0], pose  # not localized yet (odom-only)


def _grid_png(w: int, h: int, data: bytes) -> bytes:
    """OccupancyGrid bytes -> greyscale PNG (row 0 of the grid = min y = image
    BOTTOM, so rows are flipped). -1/255 unknown -> map-grey, 0 free -> white,
    100 occupied -> black — same palette as the saved map render."""
    import struct
    import zlib
    raw = bytearray()
    for yy in range(h - 1, -1, -1):
        raw.append(0)
        for v in data[yy * w:(yy + 1) * w]:
            c = 205 if v > 100 else max(0, 255 - int(v * 2.55))  # 255 = int8 -1
            raw += bytes((c, c, c))

    def ch(t, d):
        return (struct.pack(">I", len(d)) + t + d
                + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n"
            + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + ch(b"IDAT", zlib.compress(bytes(raw), 6)) + ch(b"IEND", b""))


# live /map: the web gateway truncates arrays to 64 items (sanitize_payload),
# so the full grid comes over ssh — a one-shot rclpy dump of the latched topic.
_MAPDUMP_PATH = "/home/pi/openclaw_mapdump.py"
_MAPDUMP = r'''#!/usr/bin/env python3
import base64, json, sys, time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from nav_msgs.msg import OccupancyGrid

rclpy.init()
n = Node("openclaw_mapdump")
box = {}
qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                 reliability=ReliabilityPolicy.RELIABLE)
n.create_subscription(OccupancyGrid, "/map", lambda m: box.setdefault("m", m), qos)
# поза ровера в кадре карты из TF (map->base_link): при картировании её даёт
# сам SLAM (amcl спит), при навигации — amcl; одна механика на оба режима
from tf2_ros.buffer import Buffer
from tf2_ros.transform_listener import TransformListener
import math
buf = Buffer()
TransformListener(buf, n)
t0 = time.time()
pose = None
while time.time() - t0 < 6.0:
    rclpy.spin_once(n, timeout_sec=0.2)
    if "m" in box:
        try:
            t = buf.lookup_transform("map", "base_link", rclpy.time.Time())
            q = t.transform.rotation
            yaw = math.atan2(2*(q.w*q.z + q.x*q.y), 1 - 2*(q.y*q.y + q.z*q.z))
            pose = {"x": round(t.transform.translation.x, 4),
                    "y": round(t.transform.translation.y, 4),
                    "yaw_deg": round(math.degrees(yaw), 2)}
            break
        except Exception:
            if time.time() - t0 > 4.0:
                break               # карта есть, TF нет — отдаём без позы
m = box.get("m")
if not m:
    print(json.dumps({"ok": False, "error": "no /map in 6s"}))
else:
    i = m.info
    print(json.dumps({"ok": True, "w": int(i.width), "h": int(i.height),
                      "res": round(float(i.resolution), 6),
                      "ox": round(float(i.origin.position.x), 4),
                      "oy": round(float(i.origin.position.y), 4),
                      "pose": pose,
                      "data": base64.b64encode(bytes(v & 0xFF for v in m.data)).decode()}))
n.destroy_node(); rclpy.shutdown()
'''
_livemap_cache = {"ts": 0.0, "body": None}
_livemap_lock = threading.Lock()


def _mapdump_install() -> None:
    """Stage the dump script on the rover once per bridge run (sftp)."""
    if _livemap_cache.get("staged"):
        return
    import io
    import paramiko
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(SSH_HOST, 22, SSH_USER, SSH_PASS, timeout=8)
    try:
        c.open_sftp().putfo(io.BytesIO(_MAPDUMP.encode()), _MAPDUMP_PATH)
    finally:
        c.close()
    _livemap_cache["staged"] = True


# Nav2 раздувает препятствия (~15-20см inflation): клетка со «свободным»
# центром, но стеной рядом — недостижима, цель молча abort'ится. Считаем
# проходимость каждой клетки сетки прямо по карте, чтобы фронт красил её,
# а move давал честную ошибку ДО поездки.
WALK_R = float(os.environ.get("WALK_RADIUS", "0.18"))


def _cell_walkability(grid: bytes, w: int, h: int,
                      res: float, ox: float, oy: float) -> list:
    def occ_at(x: float, y: float) -> int:
        px, py = int((x - ox) / res), int((y - oy) / res)
        if not (0 <= px < w and 0 <= py < h):
            return 255
        return grid[py * w + px]

    out = []
    for cy in range(CFG["grid_ny"]):
        row = []
        for cx in range(CFG["grid_nx"]):
            mx, my = cell_to_map(cx, cy)
            c = occ_at(mx, my)
            if c == 255:
                row.append("unknown")
                continue
            if c >= 65:
                row.append("blocked")
                continue
            tight = False
            steps = int(WALK_R / res)
            for dx in range(-steps, steps + 1, 2):
                for dy in range(-steps, steps + 1, 2):
                    v = occ_at(mx + dx * res, my + dy * res)
                    if v >= 65 or v == 255:
                        tight = True
                        break
                if tight:
                    break
            row.append("tight" if tight else "free")
        out.append(row)
    return out


def livemap_payload() -> dict:
    """Fresh /map frame (cached ~2s): ssh -> rclpy one-shot -> PNG + geometry."""
    with _livemap_lock:
        if _livemap_cache["body"] and time.time() - _livemap_cache["ts"] < 2.0:
            return _livemap_cache["body"]
        _mapdump_install()
        rc, out = _ssh(_ros_cmd(f"python3 {_MAPDUMP_PATH}"), timeout=25)
        line = out.strip().splitlines()[-1] if out.strip() else "{}"
        j = json.loads(line)
        if not j.get("ok"):
            return {"ok": False, "error": j.get("error") or f"dump rc={rc}"}
        import base64
        grid = base64.b64decode(j["data"])
        body = {"ok": True, "width_px": j["w"], "height_px": j["h"],
                "resolution": j["res"], "origin": [j["ox"], j["oy"]],
                "pose": j.get("pose"),
                "cells": _cell_walkability(grid, j["w"], j["h"], j["res"],
                                           j["ox"], j["oy"]),
                "png": base64.b64encode(_grid_png(j["w"], j["h"], grid)).decode()}
        _livemap_cache.update(ts=time.time(), body=body)
        return body


# ---- HTTP handler (our bridge contract) ----------------------------------
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
            busy = {"busy": _busy["what"] or None,
                    "busy_s": int(time.time() - _busy["since"]) if _busy["what"] else 0}
            try:
                st = rover_state()
                return self._json(200, {
                    "ok": bool(st.get("ok")), "agent": "rover", "real": True,
                    "robot_id": st.get("robot_id"), "nav2_ready": st.get("nav2_ready"),
                    "map": (st.get("map") or {}).get("label"),
                    "localized": (st.get("pose") or {}).get("frame_id") == "map",
                    **busy})
            except RoverApiError as e:
                return self._json(200, {"ok": False, "agent": "rover", "real": True,
                                        "error": str(e)})
        if self.path == "/pose":
            try:
                cell, pose = current_cell()
                return self._json(200, {
                    "xy": cell, "heading": pose.get("yaw_deg", 0.0),
                    "map": {k: pose.get(k) for k in ("x", "y", "yaw_deg", "frame_id")},
                    "reality_ok": pose.get("frame_id") == "map"})
            except RoverApiError as e:
                return self._json(200, {"xy": [0, 0], "heading": 0.0, "error": str(e)})
        if self.path == "/config":
            return self._json(200, {"ok": True, **CFG, "rover_api": API})
        if self.path == "/slam":
            # localization/SLAM summary for the demo panel: which map is loaded,
            # is AMCL localized (pose in the map frame), is Nav2 up, who holds
            # the lease. Map geometry comes from the rover web gateway.
            try:
                st = rover_state()
            except RoverApiError as e:
                # mapping profile: control API is down but the web gateway (and
                # the growing SLAM map) stay up — keep the panel alive
                st = {"map": {}, "pose": {}, "nav2_ready": False, "lease": None,
                      "navigation": {}, "_control_api_error": str(e)}
            out = {"ok": True,
                   "control_api": "_control_api_error" not in st,
                   "map": st.get("map") or {},
                   "pose": st.get("pose") or {},
                   "localized": (st.get("pose") or {}).get("frame_id") == "map",
                   "nav2_ready": st.get("nav2_ready"),
                   "lease": st.get("lease"),
                   "navigation": {k: (st.get("navigation") or {}).get(k)
                                  for k in ("state", "message", "distance_remaining")},
                   "grid": dict(CFG)}
            try:
                maps = json.loads(urllib.request.urlopen(
                    WEB + "/api/maps", timeout=5).read().decode()).get("maps") or []
                if maps:
                    out["map"].update({k: maps[0].get(k) for k in
                                       ("resolution", "origin", "width_m", "height_m",
                                        "width_px", "height_px")})
                    out["map"]["image_url"] = maps[0].get("image_url")
            except Exception:  # noqa: BLE001  (gateway down -> no geometry, still ok)
                pass
            return self._json(200, out)
        if self.path == "/livemap":
            # LIVE map straight from the /map topic (SLAM Toolbox while mapping,
            # map_server latch in navigation): JSON with base64 PNG + geometry
            # so the panel keeps its grid/pose overlay aligned while building.
            try:
                body = livemap_payload()
                return self._json(200 if body.get("ok") else 404, body)
            except Exception as e:  # noqa: BLE001
                return self._json(502, {"error": f"livemap: {e}"})
        if self.path == "/map.png":
            # rendered SLAM map image, proxied from the rover web gateway
            try:
                maps = json.loads(urllib.request.urlopen(
                    WEB + "/api/maps", timeout=5).read().decode()).get("maps") or []
                if not maps:
                    return self._json(404, {"error": "no map"})
                data = urllib.request.urlopen(
                    WEB + maps[0]["image_url"], timeout=8).read()
            except Exception as e:  # noqa: BLE001
                return self._json(502, {"error": f"map image: {e}"})
            self.send_response(200)
            self.send_header("content-type", "image/png")
            self.send_header("content-length", str(len(data)))
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        try:
            body = self._body()
        except Exception as e:  # noqa: BLE001
            return self._json(400, {"error": f"bad json: {e}"})
        try:
            if self.path in ("/land", "/takeoff"):
                return self._json(200, {"ok": True})
            if self.path == "/led":
                _led["effect"] = str(body.get("effect")
                                     or ("on" if body.get("on") else "off"))[:24]
                return self._json(200, {"ok": True, "led": _led["effect"], "hw": False})
            if self.path == "/config":
                return self._config(body)
            if self.path == "/initial_pose":
                return self._initial_pose(body)
            if self.path == "/stop":
                with _busy_lock:
                    active = _busy["lease"]
                    if active is not None:
                        _busy["abort"] = True   # цикл goto сам отменит цель
                        return self._json(200, {"ok": True, "stopped": True,
                                                "aborted": _busy["what"]})
                stream_set(0.0, 0.0, 0.0, 0.1)   # заодно глушим телеоп-поток
                with Lease() as lease:
                    cleared = _clear_active_goal(lease)
                return self._json(200, {"ok": True, "stopped": True,
                                        "goal_cleared": cleared})
            if self.path == "/goto":
                return self._goto(body)
            if self.path == "/teleop":
                return self._teleop(body)
            if self.path == "/mapping":
                return self._json(200, mapping_action(body))
            if self.path == "/dwell":
                return self._dwell(body)
            if self.path == "/move":
                return self._move(body)
            if self.path == "/navigate":
                if body.get("from") is None and isinstance(body.get("to"), list):
                    return self._move(body)
                return self._navigate(body)
        except BusyError as e:
            return self._json(409, {"error": str(e)})
        except RoverApiError as e:
            return self._json(502, {"error": f"rover api: {e}"})
        return self._json(404, {"error": "not found"})

    def _config(self, body):
        for k in ("cell_size", "map_x0", "map_y0", "map_yaw_deg"):
            if k in body:
                CFG[k] = float(body[k])
        for k in ("grid_nx", "grid_ny"):
            if k in body:
                CFG[k] = max(1, int(body[k]))
        if "map_label" in body:
            CFG["map_label"] = str(body["map_label"])[:64]
        return self._json(200, {"ok": True, **CFG})

    def _initial_pose(self, body):
        """AMCL re-localization: either at a grid cell ({cell:[cx,cy]}) or at
        raw map metres ({map:{x,y}}) — the demo panel offers both."""
        yaw = float(body.get("yaw_deg", 0.0))
        cell = body.get("cell")
        raw = body.get("map")
        if isinstance(raw, dict) and "x" in raw and "y" in raw:
            mx, my = float(raw["x"]), float(raw["y"])
            yaw = float(raw.get("yaw_deg", yaw))
            cell = map_to_cell(mx, my)
        elif isinstance(cell, list) and len(cell) == 2:
            mx, my = cell_to_map(float(cell[0]), float(cell[1]))
        else:
            return self._json(400, {"error": "cell:[cx,cy] or map:{x,y} required"})
        with Lease() as lease:
            r = _api("/v1/localization/initial-pose",
                     _goal_body(mx, my, yaw), lease=lease.id)
        if r.get("ok"):
            _last_pose.update(x=mx, y=my, yaw_deg=yaw)  # для авто-recover
        return self._json(200, {"ok": bool(r.get("ok")), "cell": cell,
                                "map": {"x": mx, "y": my, "yaw_deg": yaw}})

    def _path_for(self, to, grid):
        frm, _ = current_cell()
        to = [int(to[0]), int(to[1])]
        if isinstance(grid, list):
            return frm, astar(grid, frm, to)
        # no obstacle grid -> free-plan straight through cells (Nav2 avoids
        # real obstacles itself); still step cell-by-cell for progress frames
        return frm, astar([[0] * max(CFG["grid_nx"], to[0] + 1, frm[0] + 1)
                           for _ in range(max(CFG["grid_ny"], to[1] + 1, frm[1] + 1))],
                          frm, to) or [frm, to]

    def _move(self, body):
        to = body.get("to")
        if not (isinstance(to, list) and len(to) == 2):
            return self._json(400, {"error": "to:[x,y] required"})
        err = _wait_nav_ready()
        if err:
            return self._json(503, {"error": err})
        target_st = ""
        try:  # честная ошибка ДО поездки, если клетка упирается в стену карты
            cells = livemap_payload().get("cells") or []
            target_st = cells[int(to[1])][int(to[0])]
            if target_st in ("blocked", "unknown"):
                return self._json(409, {"error":
                    f"клетка {to} на карте {'в стене' if target_st == 'blocked' else 'в неизвестной зоне'}"
                    " — сдвинь якорь сетки или выбери другую клетку",
                    "cell_status": target_st})
        except Exception:  # noqa: BLE001  (карта недоступна — едем как есть)
            pass
        frm, path = self._path_for(to, body.get("grid"))
        if not path:
            return self._json(409, {"error": "no path", "from": frm, "to": to})
        with _Motion(f"move -> {to}") as lease:
            for c in path[1:] or path:
                ns = drive_to_cell(lease, c[0], c[1])
                if ns.get("state") != "succeeded":
                    cell, _ = current_cell()
                    if cell == [int(c[0]), int(c[1])]:
                        continue    # фактически в клетке — abort от допуска позы
                    hint = (" (клетка впритык к стене ~18см — inflation Nav2 не "
                            "пускает; сдвинь якорь сетки)" if target_st == "tight"
                            and c == [int(to[0]), int(to[1])] else "")
                    msg = f": {ns['message']}" if ns.get("message") else ""
                    return self._json(502, {"error": f"nav {ns.get('state')}{msg}{hint}",
                                            "at": cell, "target": c})
        cell, _ = current_cell()
        return self._json(200, {"ok": True, "pose": cell, "cells": len(path)})

    def _navigate(self, body):
        frm, to, grid = body.get("from"), body.get("to"), body.get("grid")
        if not (isinstance(frm, list) and isinstance(to, list) and isinstance(grid, list)):
            return self._json(400, {"error": "from/to/grid required"})
        err = _wait_nav_ready()
        if err:
            return self._json(503, {"error": err})
        real_frm, _ = current_cell()
        path = astar(grid, real_frm, [int(to[0]), int(to[1])])
        try:
            motion = _Motion(f"navigate -> {to}")
            lease = motion.__enter__()   # BusyError ДО отправки заголовков
        except BusyError as e:
            return self._json(409, {"error": str(e)})
        self.send_response(200)
        self.send_header("content-type", "application/x-ndjson")
        self.end_headers()

        def emit(o):
            self.wfile.write((json.dumps(o) + "\n").encode())
            self.wfile.flush()

        try:
            if not path:
                return emit({"status": "blocked", "reason": "no path"})
            n = len(path)
            for i, c in enumerate(path):
                if i:  # first cell = where we already are
                    ns = drive_to_cell(lease, c[0], c[1])
                    if ns.get("state") != "succeeded":
                        return emit({"status": "blocked",
                                     "reason": f"nav {ns.get('state')} at {c}"})
                emit({"pose": [int(c[0]), int(c[1])],
                      "progress": round((i + 1) / n, 3)})
            emit({"status": "arrived", "pose": [int(to[0]), int(to[1])]})
        finally:
            motion.__exit__(None, None, None)

    def _goto(self, body):
        """Direct Nav2 goal at raw map metres: {x,y,yaw_deg} or {map:{...}} —
        «отправить ровера просто в точку», мимо сетки."""
        src = body.get("map") if isinstance(body.get("map"), dict) else body
        try:
            mx, my = float(src["x"]), float(src["y"])
        except (KeyError, TypeError, ValueError):
            return self._json(400, {"error": "x,y (map metres) required"})
        yaw = float(src.get("yaw_deg", 0.0))
        err = _wait_nav_ready()
        if err:
            return self._json(503, {"error": err})
        with _Motion(f"goto ({mx:.2f},{my:.2f})") as lease:
            ns = drive_to_point(lease, mx, my, yaw)
        cell, pose = current_cell()
        out = {"ok": ns.get("state") == "succeeded", "state": ns.get("state"),
               "pose": cell, "map": {k: pose.get(k) for k in ("x", "y", "yaw_deg")}}
        return self._json(200 if out["ok"] else 502, out)

    def _teleop(self, body):
        """Manual velocity burst (mapping drives): {vx, vy, wz, duration_s}.
        Clamped by the rover API itself; max 5s per call."""
        try:
            vx = float(body.get("vx", 0.0))
            vy = float(body.get("vy", 0.0))
            wz = float(body.get("wz", 0.0))
            dur = float(body.get("duration_s", 0.6))
        except (TypeError, ValueError):
            return self._json(400, {"error": "vx/vy/wz/duration_s must be numbers"})
        if body.get("stream"):
            # плавный режим (WASD): задать вектор + продлить дедлайн, воркер
            # уже гонит его 8 Гц; ответ мгновенный, позу не дёргаем
            stream_set(vx, vy, wz, dur)
            return self._json(200, {"ok": True, "via": "stream"})
        # Ловушка режима картирования: control API ЖИВ и молча принимает teleop,
        # но публикует в /cmd_vel_teleop -> twist_mux, а twist_mux в профиле
        # mapping ВЫКЛЮЧЕН — команды уходят в никуда (WASD «не работает»).
        # Веб-гейтвей публикует прямо в /cmd_vel, который слушает база.
        use_web = True
        try:
            use_web = not rover_state().get("nav2_ready")
        except RoverApiError:
            pass
        if use_web:
            sent = _web_drive_burst(vx, vy, wz, dur)
            via = "web_gateway"
        else:
            try:
                with Lease() as lease:
                    sent = teleop_burst(lease, vx, vy, wz, dur)
                via = "control_api"
            except RoverApiError:
                sent = _web_drive_burst(vx, vy, wz, dur)
                via = "web_gateway"
        try:
            cell, pose = current_cell()
        except RoverApiError:
            cell, pose = [0, 0], {}
        return self._json(200, {"ok": True, "packets": sent, "via": via,
                                "cell": cell,
                                "map": {k: pose.get(k) for k in ("x", "y", "yaw_deg")}})

    def _dwell(self, body):
        secs = float(body.get("seconds", 0))
        led = str(body.get("led") or _led["effect"] or "off").lower()
        _led["effect"] = led
        cell0, _ = current_cell()
        t0 = time.time()
        time.sleep(max(0.0, min(secs, 120.0)))
        cell1, _ = current_cell()
        return self._json(200, {"ok": True, "cell": cell1,
                                "stationary_seconds": round(time.time() - t0, 2),
                                "moved": cell0 != cell1,
                                "led": led in ("on", "blink")})


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[sverk_rover_bridge] REAL rover on :{PORT} -> {API} "
          f"cell={CFG['cell_size']}m anchor=({CFG['map_x0']},{CFG['map_y0']})"
          f"@{CFG['map_yaw_deg']}deg", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
