#!/usr/bin/env python3
"""Dashboard + Hub server (brief §8 + the §2 distributed swap).

Two modes, one file:

* default (single-host dev / `make demo`): read-only dashboard. Tails
  blackboard/events.jsonl and streams to the browser over SSE; serves the SPA,
  the scenario grid, the agent list, and each agent's full thinking transcript.

* HUB_MODE=1 (distributed / on-drone): ALSO the network rendezvous. Drones on
  their own Docker hosts reach it over HTTP (HttpBoard) to read shared state and
  post messages / progress / streamed thoughts. The coordinator runs co-located
  and shares the same blackboard volume directly (FileBoard). Writes are gated
  by HUB_TOKEN (Bearer) when set (§11).

SSE is used instead of a raw WebSocket so the whole thing is stdlib-only and
gets browser auto-reconnect for free.
"""
from __future__ import annotations

import json
import csv
import os
import re
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from bb import Blackboard, now_iso  # FileBoard: atomic state/message/event/registry I/O
from pointcloud import build_pointcloud, export_pointcloud, csv_bytes

HERE = Path(__file__).resolve().parent


def _resolve_web_dir() -> Path:
    """Built React SPA. Prefers WEB_DIR env, then frontend/dist, then
    frontend-recovered/dist (the copy pulled out of the rover-viz docker image
    after the 2026-07 NTFS corruption ate the frontend/ directory)."""
    cands = ([Path(os.environ["WEB_DIR"])] if os.environ.get("WEB_DIR") else [])
    cands += [HERE.parent / "frontend" / "dist",
              HERE.parent / "frontend-recovered" / "dist"]
    for c in cands:
        try:
            if (c / "index.html").is_file():
                return c
        except OSError:
            continue
    return cands[0]


WEB_DIR = _resolve_web_dir()
SCENARIO = os.environ.get("SCENARIO", "scenario-1")
TASK = os.environ.get("TASK", "")
FIXTURES = Path(os.environ.get("FIXTURES", "./test_fixtures"))


def _default_dashboard() -> str:
    """Which dashboard the bare '/' serves, per scenario.

    Only the painting/studio flow uses the React SPA (frontend/dist) — and its
    source was lost to an fs corruption, so it survives only as a prebuilt
    bundle. Every other scenario has a maintained standalone HTML dashboard:
    the street/city rover run -> index.html (also at /rover), survey -> survey.html.
    Landing street runs on the studio SPA is why '/' looked like painters with no
    field; route them to their real dashboard instead."""
    try:
        mp = FIXTURES / SCENARIO / "map.json"
        if mp.exists() and json.loads(mp.read_text()).get("mode") == "painting":
            return "studio"
    except Exception:  # noqa: BLE001
        pass
    if TASK == "painting" or SCENARIO.startswith("painters"):
        return "studio"
    if TASK == "survey" or SCENARIO.startswith("survey"):
        return "survey"
    if TASK == "scan_debate" or SCENARIO.startswith("test"):
        return "test"
    return "rover"

_CTYPES = {
    ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript",
    ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2",
    ".map": "application/json", ".webmanifest": "application/manifest+json",
}


def _ctype(p: Path) -> str:
    return _CTYPES.get(p.suffix.lower(), "application/octet-stream")
HUB_MODE = os.environ.get("HUB_MODE", "0") not in ("0", "", "false", "no")
HUB_TOKEN = os.environ.get("HUB_TOKEN", "")

# Несколько команд в одной локалке: у каждого хендлера (хаба) — свой
# идентификатор и флот (painter | city). Дрон с чужим handler_id/флотом
# получает отказ при регистрации — команды не путаются, чей это борт.
from binding import accept_registration, fleet_for_task, normalize_fleet  # noqa: E402
HANDLER_ID = os.environ.get("HANDLER_ID", "").strip()
HUB_FLEET = normalize_fleet(os.environ.get("FLEET")) \
    or fleet_for_task(os.environ.get("TASK", ""))

# real-stack drone bridges live at fleet:900N (sverk_sitl joined to the mesh as
# `fleet`); operator controls (set_cell) + the cv2-aruco reality-check are
# proxied through the viz, which is on the same mesh.
import re as _re  # noqa: E402
FLEET_HOST = os.environ.get("FLEET_BRIDGE_HOST", "fleet")
FLEET_N = int(os.environ.get("FLEET_DRONES", "4"))


def _bridge_url(agent: str):
    m = _re.search(r"(\d+)", agent or "")
    return f"http://{FLEET_HOST}:{9000 + int(m.group(1))}" if m else None


def _fleet_drones():
    return [f"drone-{i}" for i in range(1, FLEET_N + 1)]


# ---- demo mode (/demo): drive robots by hand through the SAME bridge HTTP
# contract the LLM agents use (BridgeClient: /move /navigate /pose /dwell /led)
# — an interface smoke-test with zero LLM in the loop. Robot registry comes
# from DEMO_BRIDGES ("id=url,id=url"); default = the mock-compose bridges.
def _demo_robots() -> dict:
    env = os.environ.get("DEMO_BRIDGES", "").strip()
    if env:
        out = {}
        for part in env.split(","):
            if "=" in part:
                rid, url = part.split("=", 1)
                out[rid.strip()] = url.strip().rstrip("/")
        return out
    robots = {f"drone-{i}": f"http://bridge-drone-{i}:9000"
              for i in range(1, int(os.environ.get("DEMO_DRONES", "2")) + 1)}
    robots["rover"] = os.environ.get("DEMO_ROVER_URL", "http://bridge-rover:9000")
    return robots


# actions the demo panel may forward to a bridge — exactly the BridgeClient verbs
_DEMO_ACTIONS = {"move", "navigate", "dwell", "led", "land", "takeoff",
                 "photograph", "analyze", "stop", "config", "initial_pose",
                 "goto", "teleop", "mapping"}
_DEMO_FIELD = {}  # last field pushed from the demo page (fallback: scenario map)


def _demo_call(url: str, action: str, args: dict, timeout: float = 90.0) -> dict:
    import urllib.error as _e
    import urllib.request as _u
    req = _u.Request(url + "/" + action, data=json.dumps(args or {}).encode(),
                     headers={"content-type": "application/json"}, method="POST")
    try:
        if action == "navigate" and args.get("from") is not None:
            frames = []
            with _u.urlopen(req, timeout=timeout) as resp:  # ndjson stream
                for line in resp:
                    line = line.strip()
                    if line:
                        frames.append(json.loads(line.decode()))
            return {"ok": bool(frames) and frames[-1].get("status") == "arrived",
                    "frames": frames}
        with _u.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except _e.HTTPError as exc:
        # surface the bridge's error JSON (e.g. {"error":"nav aborted","at":[x,y]})
        # instead of a bare "HTTP Error NNN"
        try:
            return {"ok": False, "http": exc.code, **json.loads(exc.read().decode())}
        except Exception:  # noqa: BLE001
            return {"ok": False, "http": exc.code, "error": str(exc)}

BB = Blackboard()
if HUB_MODE:
    BB.ensure_layout()  # hub writes; in read-only dashboard mode the volume is ro
EVENTS = BB.events_path

_STATE = {"phase", "decision", "assignments", "world", "pause", "critic", "control"}  # writable state files
_POINTCLOUD_DIR = BB.root / "artifacts" / "pointcloud"

# agent ids arriving over HTTP become file/dir names on the blackboard — an
# unsanitized id like "../../etc/x" escaped the board entirely (path traversal)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _safe_id(s) -> str | None:
    s = str(s or "")
    return s if _ID_RE.match(s) else None


def _scenario_canvas() -> tuple[float, float]:
    mp = FIXTURES / SCENARIO / "map.json"
    if mp.exists():
        try:
            m = json.loads(mp.read_text(encoding="utf-8"))
            cv = m.get("canvas") or {}
            return float(cv.get("w", 120)), float(cv.get("h", 120))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return 120.0, 120.0


def _pointcloud_payload() -> dict:
    meta = _POINTCLOUD_DIR / "pointcloud.json"
    if meta.exists():
        try:
            return json.loads(meta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    cw, ch = _scenario_canvas()
    return build_pointcloud(BB.events_path, canvas_w=cw, canvas_h=ch)


# ---- transcript assembly: reconstruct each agent's full chain-of-thought ----
def assemble_transcript(agent_id: str) -> dict:
    thoughts, cur = [], None
    if EVENTS.exists():
        with open(EVENTS, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("from") != agent_id:
                    continue
                k = e.get("kind")
                if k == "thought":  # mock: single-shot
                    thoughts.append({"ts": e.get("t"), "phase": e.get("phase"),
                                     "text": e.get("text", "")})
                elif k == "thought_start":
                    cur = {"ts": e.get("t"), "phase": e.get("phase"), "text": ""}
                elif k == "thought_delta" and cur is not None:
                    cur["text"] += e.get("text", "")
                elif k == "thought_end":
                    if cur is None:
                        cur = {"ts": e.get("t"), "phase": e.get("phase"), "text": ""}
                    if not cur["text"]:
                        cur["text"] = e.get("text", "")
                    if e.get("thinking"):
                        cur["thinking"] = e.get("thinking")
                    thoughts.append(cur)
                    cur = None
    if cur is not None:  # stream still in flight
        cur["streaming"] = True
        thoughts.append(cur)
    messages = [m for m in BB.list_messages()
                if m.get("from") == agent_id or m.get("to") == agent_id]
    reg = BB.read_registry().get(agent_id, {})
    return {"id": agent_id, "role": reg.get("role"), "meta": reg,
            "thoughts": thoughts, "messages": messages}


def agents_summary() -> list:
    reg = BB.read_registry()
    # last thought + phase per agent (from the event tail)
    last = {}
    if EVENTS.exists():
        with open(EVENTS, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                f = e.get("from")
                if not f:
                    continue
                if e.get("kind") in ("thought", "thought_end", "thought_start", "thought_delta"):
                    d = last.setdefault(f, {})
                    if e.get("phase"):
                        d["phase"] = e["phase"]
    ids = set(reg) | set(last)
    out = []
    for i in sorted(ids):
        r = reg.get(i) or {}
        out.append({"id": i, "role": r.get("role"),
                    "phase": last.get(i, {}).get("phase"),
                    "registered": i in reg,
                    # флот/привязка: страница /fleet и фильтры дашбордов
                    "fleet": r.get("fleet") or "",
                    "bound": bool(r.get("bound")),
                    "handler_id": r.get("handler_id") or "",
                    "name": r.get("name") or i})
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    # ---- helpers ----
    def _send(self, code, ctype, data: bytes):
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(data)))
        self.send_header("cache-control", "no-store")
        self.send_header("access-control-allow-origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, "application/json", json.dumps(obj).encode())

    def _body(self) -> dict:
        n = int(self.headers.get("content-length", 0))
        return json.loads(self.rfile.read(n).decode()) if n else {}

    def _authed(self) -> bool:
        if not HUB_TOKEN:
            return True
        return self.headers.get("authorization", "") == f"Bearer {HUB_TOKEN}"

    # ---- GET ----
    def do_GET(self):
        path = urlparse(self.path).path
        # legacy dashboards, kept as separate tools (safe-passage/rover, debate)
        if path in ("/rover", "/legacy"):
            return self._file(HERE / "index.html", "text/html")
        if path in ("/debate", "/debate.html"):
            return self._file(HERE / "debate.html", "text/html")
        if path in ("/survey", "/survey.html"):
            return self._file(HERE / "survey.html", "text/html")
        if path in ("/city", "/city.html"):
            return self._file(HERE / "city.html", "text/html")
        if path in ("/test", "/test.html", "/testfront"):
            return self._file(HERE / "test.html", "text/html")
        if path in ("/debug", "/debug.html"):
            return self._file(HERE / "debug.html", "text/html")
        if path in ("/demo", "/demo.html"):
            return self._file(HERE / "demo.html", "text/html")
        if path == "/demo/state":
            # poll every robot's bridge: alive? where? (same /healthz + /pose
            # the agents use). Field geometry: last /demo/field push, else the
            # scenario fixture.
            import urllib.request as _u
            robots = {}
            for rid, url in _demo_robots().items():
                try:
                    hz = json.loads(_u.urlopen(url + "/healthz", timeout=3).read().decode())
                    pose = json.loads(_u.urlopen(url + "/pose", timeout=3).read().decode())
                    robots[rid] = {"ok": bool(hz.get("ok")), "url": url,
                                   "real": bool(hz.get("real")), "pose": pose,
                                   "busy": hz.get("busy"),
                                   "busy_s": hz.get("busy_s", 0)}
                except Exception as e:  # noqa: BLE001
                    robots[rid] = {"ok": False, "url": url, "error": str(e)[:120]}
            field = dict(_DEMO_FIELD)
            if not field:
                try:
                    mp = json.loads((FIXTURES / SCENARIO / "map.json").read_text())
                    field = {"grid_size": mp.get("grid_size") or [5, 5],
                             "cell_size": mp.get("cell_size", 0.6)}
                except Exception:  # noqa: BLE001
                    field = {"grid_size": [5, 5], "cell_size": 0.6}
            return self._json({"robots": robots, "field": field})
        if path == "/demo/rover_slam":
            # rover localization/SLAM summary, proxied off its bridge (/slam)
            url = _demo_robots().get("rover")
            if not url:
                return self._json({"ok": False, "error": "no rover bridge"}, 404)
            try:
                import urllib.request as _u
                data = _u.urlopen(url + "/slam", timeout=5).read()
                return self._send(200, "application/json", data)
            except Exception as e:  # noqa: BLE001
                return self._json({"ok": False, "error": str(e)[:160]})
        if path == "/demo/rover_livemap":
            # live /map topic (растущая SLAM-карта) через бридж ровера
            url = _demo_robots().get("rover")
            if not url:
                return self._json({"ok": False, "error": "no rover bridge"}, 404)
            try:
                import urllib.request as _u
                data = _u.urlopen(url + "/livemap", timeout=12).read()
                return self._send(200, "application/json", data)
            except Exception as e:  # noqa: BLE001
                return self._json({"ok": False, "error": str(e)[:160]})
        if path == "/demo/rover_map.png":
            url = _demo_robots().get("rover")
            if not url:
                return self._send(404, "text/plain", b"no rover bridge")
            try:
                import urllib.request as _u
                data = _u.urlopen(url + "/map.png", timeout=8).read()
            except Exception:  # noqa: BLE001
                return self._send(404, "text/plain", b"no map")
            self.send_response(200)
            self.send_header("content-type", "image/png")
            self.send_header("content-length", str(len(data)))
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/chat.js":     # общий чат-слой активных фронтов
            return self._file(HERE / "chat.js", "application/javascript")
        if path == "/reality":
            # per-drone cv2-aruco reality-check (does the camera confirm the pose?)
            import urllib.request as _u
            out = {}
            for a in _fleet_drones():
                try:
                    r = json.loads(_u.urlopen(_bridge_url(a) + "/pose", timeout=3).read().decode())
                    out[a] = {k: r.get(k) for k in
                              ("xy", "reality_ok", "aruco_cell", "on_field", "markers", "alt")}
                except Exception:  # noqa: BLE001
                    out[a] = {"reality_ok": None, "err": "unreachable"}
            return self._json(out)
        if path == "/drone_photo":
            # per-cell drone camera preview: proxy the small JPEG the drone bridge
            # saved for (agent, cell). The bridges live on the mesh at fleet:900N,
            # the same hosts /reality already proxies. 404 => the cell wasn't shot.
            q = parse_qs(urlparse(self.path).query)
            agent = _safe_id((q.get("agent") or [""])[0])
            cx, cy = (q.get("cx") or [""])[0], (q.get("cy") or [""])[0]
            url = _bridge_url(agent) if agent else None
            if not (url and cx.lstrip("-").isdigit() and cy.lstrip("-").isdigit()):
                return self._send(404, "text/plain", b"bad drone_photo request")
            name = f"{agent}-cell-{int(cx)}-{int(cy)}.jpg"
            try:
                import urllib.request as _u
                data = _u.urlopen(url + "/artifact/" + name, timeout=4).read()
            except Exception:  # noqa: BLE001
                return self._send(404, "text/plain", b"no photo")
            self.send_response(200)
            self.send_header("content-type", "image/jpeg")
            self.send_header("content-length", str(len(data)))
            self.send_header("cache-control", "public, max-age=600")
            self.send_header("access-control-allow-origin", "*")
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/cell_tile":
            # aligned per-cell tile: the rover bridge crops the fixed top-down
            # skycam into cell tiles (reliable, unlike the drones' own flaky
            # per-cell flight). Proxy fleet:9005/tile. 404 => skycam not up yet.
            q = parse_qs(urlparse(self.path).query)
            cx, cy = (q.get("cx") or [""])[0], (q.get("cy") or [""])[0]
            if not (cx.lstrip("-").isdigit() and cy.lstrip("-").isdigit()):
                return self._send(404, "text/plain", b"bad cell_tile request")
            try:
                import urllib.request as _u
                data = _u.urlopen(f"http://{FLEET_HOST}:9005/tile?cx={int(cx)}&cy={int(cy)}",
                                  timeout=4).read()
            except Exception:  # noqa: BLE001
                return self._send(404, "text/plain", b"no tile")
            self.send_response(200)
            self.send_header("content-type", "image/jpeg")
            self.send_header("content-length", str(len(data)))
            self.send_header("cache-control", "no-store")
            self.send_header("access-control-allow-origin", "*")
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/survey-commerce":
            return self._file(HERE / "survey.html", "text/html")
        if path == "/commerce-widget.js":
            return self._file(HERE / "commerce-widget.js", "text/javascript")
        if path == "/commerce-widget.css":
            return self._file(HERE / "commerce-widget.css", "text/css")
        if path in ("/critic", "/critic.html", "/jury"):
            return self._file(HERE / "critic.html", "text/html")
        if path in ("/fleet", "/fleet.html", "/pairing"):
            return self._file(HERE / "fleet.html", "text/html")
        if path == "/healthz":
            return self._json({"ok": True, "hub": HUB_MODE, "scenario": SCENARIO,
                               "handler_id": HANDLER_ID, "fleet": HUB_FLEET})
        if path == "/rerun":
            # destructive action → POST only (a GET on 0.0.0.0 with CORS * let any
            # web page wipe a live run via a drive-by fetch)
            return self._json({"ok": False, "error": "use POST /rerun"}, 405)
        if path.startswith("/scenario.json"):
            mp = FIXTURES / SCENARIO / "map.json"
            return self._send(200, "application/json",
                              mp.read_bytes() if mp.exists() else b"{}")
        if path == "/agents":
            return self._json(agents_summary())
        if path.startswith("/agents/") and path.endswith("/transcript"):
            aid = path[len("/agents/"):-len("/transcript")]
            return self._json(assemble_transcript(aid))
        if path == "/events":
            return self._sse()
        # board reads (used by remote drones; harmless to expose read-only)
        if path == "/messages":
            return self._json(BB.list_messages())
        if path == "/progress":
            return self._json(BB.read_all_progress())
        if path == "/pointcloud.json":
            return self._json(_pointcloud_payload())
        if path == "/collaborative.json":
            return self._json(BB.read_json(BB.root / "state" / "collaborative.json", {}))
        if path == "/run.json":
            return self._json(BB.read_json(BB.root / "state" / "current_run.json", {}))
        if path.startswith("/export/pointcloud/"):
            name = path.split("/")[-1]
            if name not in ("all.csv",) and not name.endswith(".csv"):
                return self._send(404, "text/plain", b"not found")
            f = _POINTCLOUD_DIR / name
            if f.exists():
                return self._send(200, "text/csv", f.read_bytes())
            # serve from events without writing (dashboard volume may be read-only)
            cloud = _pointcloud_payload()
            if name == "all.csv":
                import io
                buf = io.StringIO()
                w = csv.writer(buf)
                w.writerow(["agent", "x_m", "y_m"])
                for agent, data in cloud.get("agents", {}).items():
                    for x, y in data.get("points", []):
                        w.writerow([agent, x, y])
                return self._send(200, "text/csv", buf.getvalue().encode("utf-8"))
            agent = name[:-4]
            data = cloud.get("agents", {}).get(agent)
            if not data:
                return self._send(404, "text/plain", b"not found")
            return self._send(200, "text/csv", csv_bytes(agent, data.get("points", [])))
        if path.startswith("/state/"):
            name = path.split("/", 2)[2]
            if name in _STATE:
                return self._json(BB.read_json(BB.state / f"{name}.json", {}))
            return self._json({"error": "unknown state"}, 404)
        # ---- debug: souls ----
        if path == "/debug/souls":
            import souls as _souls
            sdir = FIXTURES / "souls"
            out = {}
            for f in sorted(sdir.glob("*.md")) if sdir.is_dir() else []:
                meta, body = _souls.load_soul(f)
                meta["_file"] = f.name
                meta["_body"] = body
                out[f.stem] = meta
            return self._json(out)
        if path.startswith("/debug/soul/") and not path.endswith("/save"):
            name = path[len("/debug/soul/"):]
            import souls as _souls
            sf = FIXTURES / "souls" / f"{name}.md"
            if not sf.is_file():
                return self._json({"error": "soul not found"}, 404)
            meta, body = _souls.load_soul(sf)
            meta["_file"] = sf.name
            meta["_body"] = body
            return self._json(meta)
        # The bare "/" serves the dashboard that matches the running scenario
        # (street/city -> rover HTML, survey -> survey HTML, painting -> React
        # studio). Explicit "/studio" always forces the React SPA.
        if path in ("/", "", "/index.html"):
            dash = _default_dashboard()
            if dash == "rover":
                return self._file(HERE / "index.html", "text/html")
            if dash == "survey":
                return self._file(HERE / "survey.html", "text/html")
            if dash == "test":
                return self._file(HERE / "test.html", "text/html")
            # dash == "studio" -> fall through to the React SPA
        # React SPA (frontend/dist) — the studio dashboard at "/studio", plus its
        # static assets; unknown paths fall back to index.html (client routing).
        return self._web(path)

    def _web(self, path: str):
        idx = WEB_DIR / "index.html"
        if not idx.exists():
            return self._send(
                200, "text/html",
                "<!doctype html><meta charset=utf-8>"
                "<body style='font:16px sans-serif;background:#0b0f16;color:#eee;padding:40px'>"
                "<h2>OpenClaw Studio — frontend not built</h2>"
                "<p>Run <code>make web</code> (or <code>cd frontend &amp;&amp; npm install &amp;&amp; "
                "npm run build</code>), then reload.</p></body>".encode("utf-8"))
        rel = path.lstrip("/")
        if rel and not path.endswith("/"):
            f = (WEB_DIR / rel).resolve()
            try:
                if str(f).startswith(str(WEB_DIR.resolve())) and f.is_file():
                    return self._file(f, _ctype(f))
            except OSError:
                pass
        return self._file(idx, "text/html")

    # ---- POST (rerun in any mode; board writes in hub mode only) ----
    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/rerun":
            # local dev convenience: wipe the runtime so the (keep-alive) coordinator
            # re-runs the whole flow from scratch on its next poll. The custom header
            # forces a CORS preflight, so a cross-origin page cannot trigger it.
            if self.headers.get("x-rerun") != "1":
                return self._json({"ok": False, "error": "x-rerun header required"}, 403)
            try:
                if hasattr(BB, "reset_runtime"):
                    BB.reset_runtime()
                    BB.append_event({"kind": "canvas_clear"})
                    BB.append_event({"kind": "phase", "phase": "INIT", "round": 0})
                    BB.append_event({"kind": "souls_reload", "ts": now_iso()})
                    return self._json({"ok": True})
                return self._json({"ok": False, "error": "not a FileBoard"}, 400)
            except Exception as exc:  # noqa: BLE001
                return self._json({"ok": False, "error": str(exc)}, 500)
        if path == "/demo/cmd":
            # manual robot command through the SAME bridge endpoint the LLM
            # uses. Custom header => CORS preflight (no drive-by robot moves).
            if self.headers.get("x-demo") != "1":
                return self._json({"ok": False, "error": "x-demo header required"}, 403)
            try:
                body = self._body()
            except Exception as exc:  # noqa: BLE001
                return self._json({"error": f"bad json: {exc}"}, 400)
            rid = str(body.get("robot") or "")
            action = str(body.get("action") or "")
            args = body.get("args") or {}
            url = _demo_robots().get(rid)
            if not url:
                return self._json({"ok": False, "error": f"unknown robot {rid!r}"}, 404)
            if action not in _DEMO_ACTIONS or not isinstance(args, dict):
                return self._json({"ok": False, "error": f"bad action {action!r}"}, 400)
            try:
                out = _demo_call(url, action, args)
                return self._json({"ok": out.get("ok", True), "robot": rid,
                                   "action": action, "result": out})
            except Exception as exc:  # noqa: BLE001
                return self._json({"ok": False, "robot": rid, "action": action,
                                   "error": str(exc)[:200]}, 502)
        if path == "/demo/field":
            # retune the field (cells count / cell size) and push it to every
            # bridge so the robots and the page agree on the grid
            if self.headers.get("x-demo") != "1":
                return self._json({"ok": False, "error": "x-demo header required"}, 403)
            try:
                body = self._body()
            except Exception as exc:  # noqa: BLE001
                return self._json({"error": f"bad json: {exc}"}, 400)
            gs = body.get("grid_size")
            if not (isinstance(gs, list) and len(gs) == 2
                    and all(isinstance(v, int) and 1 <= v <= 32 for v in gs)):
                return self._json({"ok": False, "error": "grid_size must be [1..32,1..32]"}, 400)
            try:
                cs = float(body.get("cell_size", 0.6))
            except (TypeError, ValueError):
                return self._json({"ok": False, "error": "cell_size must be a number"}, 400)
            if not 0.05 <= cs <= 10.0:
                return self._json({"ok": False, "error": "cell_size out of range"}, 400)
            _DEMO_FIELD.clear()
            _DEMO_FIELD.update({"grid_size": gs, "cell_size": cs})
            pushed = {}
            for rid, url in _demo_robots().items():
                try:  # mock: grid_size+cell_size; real rover bridge: cell/grid keys
                    pushed[rid] = _demo_call(url, "config", {
                        "grid_size": gs, "cell_size": cs,
                        "grid_nx": gs[0], "grid_ny": gs[1]}, timeout=5).get("ok", True)
                except Exception as exc:  # noqa: BLE001
                    pushed[rid] = f"err: {str(exc)[:80]}"
            return self._json({"ok": True, **_DEMO_FIELD, "pushed": pushed})
        if path == "/pause":
            # Операторская пауза всех сценариев (замена аккумуляторов): дроны
            # садятся, фазовая машина замирает; resume — тот же эндпоинт с
            # paused:false (дроны взлетают, поза ресинкается из бриджа).
            # Работает и локально (не только HUB_MODE); custom header => CORS
            # preflight, чужая страница не дёрнет; токен — если задан.
            if self.headers.get("x-pause") != "1":
                return self._json({"ok": False, "error": "x-pause header required"}, 403)
            if not self._authed():
                return self._json({"error": "unauthorized"}, 401)
            try:
                body = self._body()
            except Exception as exc:
                return self._json({"error": f"bad json: {exc}"}, 400)
            paused = bool(body.get("paused", True))
            obj = {"paused": paused,
                   "reason": str(body.get("reason") or
                                 ("battery swap" if paused else ""))[:200],
                   "by": "operator", "ts": now_iso()}
            try:
                BB.write_pause(obj)
                BB.append_event({"kind": "pause", **obj})
                return self._json({"ok": True, **obj})
            except Exception as exc:  # read-only volume (docker demo) и т.п.
                return self._json({"ok": False, "error": str(exc)}, 500)

        if path == "/step":
            # single-step / tick: briefly resume the frozen machine for `secs`,
            # then auto-pause again — lets an operator walk the run forward a cell
            # or two to watch/debug. Not atomic (the loop is async multi-agent), so
            # it advances by time, not by exactly one action.
            if self.headers.get("x-pause") != "1":
                return self._json({"ok": False, "error": "x-pause header required"}, 403)
            if not self._authed():
                return self._json({"error": "unauthorized"}, 401)
            try:
                secs = max(0.3, min(10.0, float(self._body().get("secs", 2.0))))
            except Exception as exc:
                return self._json({"error": f"bad json: {exc}"}, 400)
            try:
                BB.write_pause({"paused": False, "reason": "step", "by": "operator",
                                "ts": now_iso()})
                BB.append_event({"kind": "pause", "paused": False, "reason": "step"})
            except Exception as exc:  # noqa: BLE001
                return self._json({"ok": False, "error": str(exc)}, 500)

            def _repause():
                time.sleep(secs)
                try:
                    BB.write_pause({"paused": True, "reason": "step-hold",
                                    "by": "operator", "ts": now_iso()})
                    BB.append_event({"kind": "pause", "paused": True,
                                     "reason": "step-hold"})
                except Exception:  # noqa: BLE001
                    pass
            threading.Thread(target=_repause, daemon=True).start()
            return self._json({"ok": True, "stepped_secs": secs})

        if path == "/control":
            # test-3x3: switch which pilot is "at the helm" — the single flyer then
            # scans that pilot's route. Meant to be flipped during a pause (the
            # flyer picks up the new active route on its next SCAN cycle). Custom
            # header => CORS preflight, so a cross-origin page cannot flip it.
            if self.headers.get("x-control") != "1":
                return self._json({"ok": False, "error": "x-control header required"}, 403)
            if not self._authed():
                return self._json({"error": "unauthorized"}, 401)
            try:
                body = self._body()
            except Exception as exc:
                return self._json({"error": f"bad json: {exc}"}, 400)
            active = _safe_id(body.get("active"))
            if not active:
                return self._json({"error": "active (pilot id) required"}, 400)
            obj = {"active": active, "by": "operator", "ts": now_iso()}
            try:
                BB.write_json(BB.state / "control.json", obj)
                BB.append_event({"kind": "control", **obj})
                return self._json({"ok": True, **obj})
            except Exception as exc:  # read-only volume (docker demo) и т.п.
                return self._json({"ok": False, "error": str(exc)}, 500)

        if path == "/set_cell":
            # operator sets which cell a drone is really on (arbitrary start /
            # kill-switch recovery) — proxied to that drone's bridge.
            if self.headers.get("x-fleet") != "1":
                return self._json({"ok": False, "error": "x-fleet header required"}, 403)
            if not self._authed():
                return self._json({"error": "unauthorized"}, 401)
            try:
                body = self._body()
            except Exception as exc:
                return self._json({"error": f"bad json: {exc}"}, 400)
            agent, cell = str(body.get("agent") or ""), body.get("cell")
            url = _bridge_url(agent)
            if not url or not (isinstance(cell, list) and len(cell) == 2):
                return self._json({"error": "agent + cell[x,y] required"}, 400)
            try:
                import urllib.request as _u
                req = _u.Request(url + "/set_cell",
                                 data=json.dumps({"cell": cell}).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
                out = json.loads(_u.urlopen(req, timeout=5).read().decode())
                try:                       # best-effort (viz board may be read-only)
                    BB.append_event({"kind": "set_cell", "from": agent, "cell": cell})
                except Exception:  # noqa: BLE001
                    pass
                return self._json({"ok": True, "agent": agent, **out})
            except Exception as exc:  # noqa: BLE001
                return self._json({"ok": False, "error": str(exc)}, 502)

        # ---- debug: save soul ----
        if path.startswith("/debug/soul/") and path.endswith("/save"):
            name = path[len("/debug/soul/"):-len("/save")]
            import souls as _souls
            sf = FIXTURES / "souls" / f"{name}.md"
            if not sf.is_file():
                return self._json({"error": "soul not found"}, 404)
            body = self._body()
            meta = {k: v for k, v in body.items() if not k.startswith("_")}
            new_body = body.get("_body") or body.get("body") or ""
            _souls.save_soul(sf, meta, new_body)
            return self._json({"ok": True, "name": name})

        if path in ("/identify", "/bind", "/unbind"):
            # LED-регистрация дронов (страница /fleet): identify — «мигни
            # цветом, покажись»; bind — подтверждение (дрон пишет привязку в
            # постоянную память); unbind — отвязать. Команды едут обычным
            # COMMAND-сообщением через доску — агент исполняет на своём бридже.
            if self.headers.get("x-fleet") != "1":
                return self._json({"ok": False, "error": "x-fleet header required"}, 403)
            if not self._authed():
                return self._json({"error": "unauthorized"}, 401)
            try:
                body = self._body()
            except Exception as exc:
                return self._json({"error": f"bad json: {exc}"}, 400)
            aid = _safe_id(body.get("id"))
            if not aid:
                return self._json({"error": "id required"}, 400)
            try:
                if path == "/identify":
                    color = str(body.get("color") or "#00ffcc")[:9]
                    effect = str(body.get("effect") or "blink")[:24]
                    msg = BB.write_message({
                        "from": "handler", "to": aid, "phase": "ANY",
                        "type": "COMMAND",
                        "body": f"Мигни лентой ({effect} {color}) — регистрация.",
                        "payload": {"led": {"effect": effect, "color": color}}})
                    BB.append_event({"kind": "identify", "id": aid,
                                     "color": color, "effect": effect})
                    return self._json({"ok": True, "id": aid, "msg": msg.get("id")})
                if path == "/bind":
                    reg = BB.read_registry().get(aid) or {}
                    reg.update({"bound": True, "handler_id": HANDLER_ID,
                                "fleet": reg.get("fleet") or HUB_FLEET})
                    BB.write_registry(aid, reg)
                    BB.write_message({
                        "from": "handler", "to": aid, "phase": "ANY",
                        "type": "COMMAND",
                        "body": f"Привязка подтверждена: хендлер {HANDLER_ID}.",
                        "payload": {"bind": {"handler_id": HANDLER_ID,
                                             "fleet": reg.get("fleet") or HUB_FLEET,
                                             "hub_url": body.get("hub_url") or ""}}})
                    BB.append_event({"kind": "bind", "id": aid,
                                     "handler_id": HANDLER_ID})
                    return self._json({"ok": True, "id": aid,
                                       "handler_id": HANDLER_ID})
                # /unbind
                reg = BB.read_registry().get(aid) or {}
                reg["bound"] = False
                BB.write_registry(aid, reg)
                BB.write_message({
                    "from": "handler", "to": aid, "phase": "ANY",
                    "type": "COMMAND", "body": "Привязка снята.",
                    "payload": {"unbind": True}})
                BB.append_event({"kind": "unbind", "id": aid})
                return self._json({"ok": True, "id": aid})
            except Exception as exc:  # read-only volume и т.п.
                return self._json({"ok": False, "error": str(exc)}, 500)

        if not HUB_MODE:
            return self._json({"error": "hub disabled"}, 403)
        if not self._authed():
            return self._json({"error": "unauthorized"}, 401)
        try:
            body = self._body()
        except Exception as exc:  # strict boundary (§11)
            return self._json({"error": f"bad json: {exc}"}, 400)

        if path == "/messages":
            if not _safe_id(body.get("from")) or not _safe_id(body.get("type")):
                return self._json({"error": "bad from/type"}, 400)
            return self._json(BB.write_message(body))
        if path == "/events":
            BB.append_event(body)
            return self._json({"ok": True})
        if path == "/register":
            aid = _safe_id(body.get("id"))
            if not aid:
                return self._json({"error": "id required (letters/digits/_-. only)"}, 400)
            # чужая команда / чужой флот — отказ с внятной причиной
            reason = accept_registration(HANDLER_ID, HUB_FLEET, body)
            if reason:
                BB.append_event({"kind": "register_rejected", "id": aid,
                                 "reason": reason})
                return self._json({"error": reason, "handler_id": HANDLER_ID,
                                   "fleet": HUB_FLEET}, 409)
            body["id"] = aid
            body["handler_id"] = body.get("handler_id") or ""
            body["fleet"] = normalize_fleet(body.get("fleet"))
            BB.write_registry(aid, body)
            return self._json({"ok": True, "id": aid,
                               "handler_id": HANDLER_ID, "fleet": HUB_FLEET})
        if path.startswith("/progress/"):
            aid = _safe_id(path.split("/", 2)[2])
            if not aid:
                return self._json({"error": "bad agent id"}, 400)
            BB.write_progress(aid, body)
            return self._json({"ok": True})
        if path.startswith("/state/"):
            name = path.split("/", 2)[2]
            if name not in _STATE:
                return self._json({"error": "unknown state"}, 404)
            BB.write_json(BB.state / f"{name}.json", body)
            return self._json({"ok": True})
        return self._json({"error": "not found"}, 404)

    # ---- static / SSE ----
    def _file(self, p: Path, ctype: str):
        try:
            self._send(200, ctype, p.read_bytes())
        except FileNotFoundError:
            self._send(404, "text/plain", b"missing")

    def _sse(self):
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.send_header("connection", "keep-alive")
        self.send_header("access-control-allow-origin", "*")
        self.end_headers()

        def send(line: str):
            self.wfile.write(f"data: {line}\n\n".encode())
            self.wfile.flush()

        pos = 0
        try:
            send(json.dumps({"kind": "hello"}))
            while True:
                if EVENTS.exists():
                    try:
                        size = EVENTS.stat().st_size
                    except OSError:
                        size = 0
                    if size < pos:
                        # /rerun (or a coordinator restart) truncated the feed while
                        # we were tailing — seeking past EOF would go silent forever.
                        # Rewind and tell the client to reset its reducer state.
                        pos = 0
                        send(json.dumps({"kind": "hello"}))
                    with open(EVENTS, "r", encoding="utf-8") as fh:
                        fh.seek(pos)
                        for line in fh:
                            line = line.strip()
                            if line:
                                send(line)
                        pos = fh.tell()
                time.sleep(0.25)  # snappy enough to show tokens streaming in
        except (BrokenPipeError, ConnectionResetError):
            return


def main():
    port = int(os.environ.get("PORT", "8080"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    mode = "HUB+dashboard" if HUB_MODE else "dashboard (read-only)"
    print(f"[viz] {mode} on :{port}  events={EVENTS}  auth={'on' if HUB_TOKEN else 'off'}",
          flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
