#!/usr/bin/env python3
"""Ровер: борт отвечает диспетчеру тем же контрактом, что и дрон.

Один файл. В отличие от drone_agent.py его НЕ нужно копировать на борт: у ровера уже
есть свой сетевой API, и этот агент — переводчик между нашим контрактом (клетки поля,
режимы ленты) и родным API ровера (метры карты, лиз управления, эффекты ленты).
Поэтому запускается там, откуда видно ровер — с ноутбука рядом с диспетчером:

    python3 rover_agent.py --port 8010 --rover-ip 192.168.1.125

Дальше диспетчер зовёт http://127.0.0.1:8010, ровно как мок из этапа 1. Переезд с
мока на железо — это подмена rover.url в config.yaml, и больше ничего.

Контракт (city/robots/base.py):

    GET  /status  -> {"ok":true,"role":"rover","state":..,"cell":[x,y],
                      "since_move":..,"busy":..,"led":..}
    POST /drive   -> {"cell":[col,row]}  доехать до СОСЕДНЕЙ клетки
    POST /led     -> {"mode":"blink"|"on"|"off","color":"#RRGGBB"}
    POST /stop    -> немедленная остановка

Проверка с ноутбука:

    curl http://127.0.0.1:8010/status
    curl -X POST http://127.0.0.1:8010/led   -d '{"mode":"blink","color":"#FF0000"}'
    curl -X POST http://127.0.0.1:8010/drive -d '{"cell":[2,3]}'
    curl -X POST http://127.0.0.1:8010/stop

Что проверено на живом ровере 192.168.1.125 (он же rover-01, ROS 2 Jazzy) 2026-07-29
(адрес по DHCP, на площадке будет другой — задаётся ключом --rover-ip):

* Движение — через rover_control_api v1 на <ip>:8767 (ветка 1 из PLAN этапа 4; он
  реально живой, а в docs/rover/ и апстриме его нет — см. docs/openclaw/03). Лиз
  X-Control-Lease живёт ~5 с, поэтому на время переезда держим поток продления раз
  в 2 с. Цель Nav2 — POST /v1/navigation/goal в МЕТРАХ карты ровера, не в клетках.
* Метры карты ровера — это его СОБСТВЕННАЯ SLAM-карта (сейчас label "ofice2"), а не
  ArUco-поле дронов. Значит привязку сетки к карте (--map-x0/--map-y0/--map-yaw)
  калибруют на площадке отдельно от дронов: заехать в известную клетку, снять позу.
* Прибытие подтверждаем ПО ФАКТ-ПОЗЕ (расстояние до цели ≤ --arrive-tol), а не по
  ответу «accepted»: Nav2 умеет отдать goal и не доехать, а на aborted у цели уже
  может стоять (грабли из docs/openclaw/03) — тогда это успех, а не провал.
* Nav2 не всегда поднят: /v1/state отдаёт nav2_ready и frame_id позы. Пока
  nav2_ready=false или поза во frame odom (а не map), /drive честно отказывает —
  ехать вслепую по одометрии этот агент не умеет (это была бы ветка 3 из PLAN).
* Лента — через rover_web на <ip>:8765, POST /api/led_strip/command. Наши режимы:
  on -> эффект fill, blink -> эффект blink, off -> enabled:false. Проверено:
  {"response":{"success":true}}. Эффекты борта: fill blink blink_fast fade wipe
  flash rainbow rainbow_fill.
* Заряд в процентах ровер не публикует, только /battery_voltage (docs/rover/). Сейчас
  на нём publishers:0 — напряжение вообще не течёт; читаем его best-effort через
  rover_web /api/ros/topic и в статус кладём как есть, без выдумки процента.

Требуется только стандартная библиотека: urllib к LAN по http работает (SSL-беда из
CLAUDE.md — только про https ai.sverk.tech). Режим --dry запускает файл где угодно
без ровера: агент отвечает как ровер и «ездит» мгновенно.
"""

from __future__ import annotations

import argparse
import json
import math
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "1.0"

DEDUP_KEEP = 64  # сколько последних command_id помнить (столько же, сколько борт дрона)

# Состояния навигации ровера, при которых он ещё едет. Всё, чего здесь нет, —
# терминальное: доехал, отменён или сорвался. Имя успеха у разных сборок разное,
# поэтому успех определяем не по строке, а по фактическому расстоянию до цели.
NAV_ACTIVE = ("sending", "accepted", "navigating", "executing", "canceling", "active")

# Наши режимы ленты -> эффект родного драйвера ровера. off гасит ленту (enabled=false).
LED_EFFECT = {"on": "fill", "blink": "blink", "off": "fill"}


def say(text: str) -> None:
    """Строка в терминал ноутбука рядом с диспетчером."""
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
#  ПРИВЯЗКА СЕТКИ К КАРТЕ РОВЕРА
# ═══════════════════════════════════════════════════════════════════════════
#
# Карта ровера — его собственная SLAM-карта в метрах, к полю дронов отношения не
# имеет. Клетка [col,row] переводится в метры карты через калибруемый якорь: где на
# карте лежит клетка [0,0] (map_x0, map_y0) и как повёрнута сетка (map_yaw). Формула
# из docs/openclaw/03. Значения по умолчанию — тождество (клетка [0,0] в начале
# карты, без поворота); на площадке они правятся под реальную карту.


class Anchor:
    def __init__(self, cell: float, x0: float, y0: float, yaw: float) -> None:
        self.cell = float(cell)
        self.x0 = float(x0)
        self.y0 = float(y0)
        self.yaw = float(yaw)

    def cell_to_m(self, cell) -> tuple[float, float]:
        lx, ly = cell[0] * self.cell, cell[1] * self.cell
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        return (self.x0 + lx * c - ly * s, self.y0 + lx * s + ly * c)

    def m_to_cell(self, x: float, y: float) -> tuple[int, int]:
        dx, dy = x - self.x0, y - self.y0
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        lx = dx * c + dy * s
        ly = -dx * s + dy * c
        return (round(lx / self.cell), round(ly / self.cell))


# ═══════════════════════════════════════════════════════════════════════════
#  БЭКЕНД: РОДНОЙ API РОВЕРА
# ═══════════════════════════════════════════════════════════════════════════


class RoverLinkError(Exception):
    """Ровер не ответил или ответил ошибкой — это про связь, а не про команду."""


class RoverRefused(Exception):
    """Ровер отказался ехать по существу (Nav2 не готов, поза не в карте)."""


def _http(url: str, body: dict | None = None, headers: dict | None = None,
          timeout: float = 4.0, method: str | None = None) -> dict:
    """Один запрос к роверу. Тело есть -> POST. Возвращает разобранный JSON."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdr = {"Content-Type": "application/json"} if data is not None else {}
    if headers:
        hdr.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdr, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = (json.loads(exc.read() or b"{}") or {}).get("message", "")
        except Exception:  # noqa: BLE001 — тело ошибки не важнее самого кода
            pass
        raise RoverLinkError(f"{method or 'GET'} {url} -> {exc.code} {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RoverLinkError(f"нет связи с {url} ({exc})") from exc


class ControlApiBackend:
    """Родной API ровера: движение — rover_control_api :8767, лента — rover_web :8765.

    Лиз управления живёт ~5 с, поэтому на время переезда держим поток продления. Лиз
    берётся под один переезд и отпускается сразу после — тогда между клетками в
    ровер может вклиниться оператор пультом (правило из docs/openclaw/03).
    """

    def __init__(self, ip: str, ctrl_port: int, web_port: int,
                 map_label: str, client_id: str) -> None:
        self.ctrl = f"http://{ip}:{ctrl_port}"
        self.web = f"http://{ip}:{web_port}"
        self.map_label = map_label
        self.client_id = client_id
        self._lease: str | None = None
        self._renew_stop: threading.Event | None = None
        self._renew_thread: threading.Thread | None = None

    # --- чтение состояния ---------------------------------------------------

    def read(self, with_battery: bool = True) -> dict:
        """Снимок: связь, готовность Nav2, поза, заряд. Любой отказ -> link=False.

        with_battery=False — во время заезда: там позу опрашивают часто, а лишний
        GET к rover_web на каждый такт и спамит, и рискует затормозить цикл, если
        веб-порт вдруг медленный.
        """
        snap = {"link": False, "nav_ready": False, "pose": None, "frame_id": "",
                "battery": None}
        try:
            st = _http(f"{self.ctrl}/v1/state", timeout=3.0)
        except RoverLinkError:
            return snap
        snap["link"] = True
        snap["nav_ready"] = bool(st.get("nav2_ready"))
        pose = st.get("pose") or {}
        if pose.get("x") is not None:
            snap["pose"] = (float(pose["x"]), float(pose["y"]),
                            float(pose.get("yaw_deg", 0.0)))
            snap["frame_id"] = pose.get("frame_id", "")
        if with_battery:
            snap["battery"] = self._battery()
        return snap

    def _battery(self) -> float | None:
        """Напряжение АКБ, В. best-effort: процента ровер не даёт, только вольты."""
        try:
            msg = _http(
                f"{self.web}/api/ros/topic?name=/battery_voltage"
                "&type=std_msgs/msg/Float32", timeout=3.0
            )
        except RoverLinkError:
            return None
        latest = msg.get("latest_message")
        if isinstance(latest, dict) and latest.get("data") is not None:
            return float(latest["data"])
        return None

    # --- лиз ----------------------------------------------------------------

    def _acquire(self) -> None:
        resp = _http(f"{self.ctrl}/v1/lease/acquire", {"client_id": self.client_id})
        self._lease = resp.get("lease_id")
        if not self._lease:
            raise RoverLinkError(f"лиз не выдан: {resp}")
        stop = threading.Event()
        self._renew_stop = stop

        def renew():
            # Продлевать раньше, чем истечёт: TTL ~5 с, шаг 2 с оставляет запас.
            while not stop.wait(2.0):
                try:
                    _http(f"{self.ctrl}/v1/lease/renew", {},
                          headers={"X-Control-Lease": self._lease or ""}, timeout=3.0)
                except RoverLinkError as exc:
                    say(f"лиз: продление не прошло ({exc})")

        self._renew_thread = threading.Thread(target=renew, daemon=True)
        self._renew_thread.start()

    def _release(self) -> None:
        if self._renew_stop is not None:
            self._renew_stop.set()
        lease, self._lease = self._lease, None
        self._renew_stop = self._renew_thread = None
        if lease:
            try:
                _http(f"{self.ctrl}/v1/lease/release", {},
                      headers={"X-Control-Lease": lease}, timeout=3.0)
            except RoverLinkError:
                pass  # лиз всё равно протухнет за 5 с сам

    def _lease_headers(self) -> dict:
        return {"X-Control-Lease": self._lease or ""}

    # --- движение -----------------------------------------------------------

    def goal(self, x: float, y: float, yaw_deg: float, request_id: str) -> None:
        """Взять лиз и отдать Nav2 цель в метрах карты. Отказ Nav2 -> RoverRefused."""
        snap = self.read()
        if not snap["nav_ready"]:
            raise RoverRefused(
                "Nav2 ровера не готов (nav2_ready=false): подними навигацию на борту, "
                "иначе ехать вслепую по одометрии этот агент не будет"
            )
        if snap["frame_id"] and snap["frame_id"] != "map":
            raise RoverRefused(
                f"поза ровера во frame «{snap['frame_id']}», а не «map»: локализация "
                "по карте ещё не сошлась — цель в метрах карты слать рано"
            )
        self._acquire()
        try:
            _http(f"{self.ctrl}/v1/navigation/goal",
                  {"request_id": request_id, "x": x, "y": y, "yaw_deg": yaw_deg,
                   "map_label": self.map_label},
                  headers=self._lease_headers(), timeout=5.0)
        except Exception:
            self._release()
            raise

    def nav_status(self) -> dict:
        try:
            return _http(f"{self.ctrl}/v1/navigation/status", timeout=3.0)
        except RoverLinkError:
            return {"state": "unknown"}

    def cancel(self, request_id: str) -> None:
        try:
            _http(f"{self.ctrl}/v1/navigation/cancel", {"request_id": request_id},
                  headers=self._lease_headers(), timeout=3.0)
        except RoverLinkError as exc:
            say(f"отмена цели не прошла ({exc})")
        finally:
            self._release()

    def hard_stop(self) -> None:
        """Аварийная остановка: и Nav2, и веб-джойстик, и мотор-старт — всё разом."""
        for url, body in (
            (f"{self.web}/api/drive/stop", {}),
            (f"{self.web}/api/motion/stop", {}),
            (f"{self.web}/api/stop", {"source": "rover_agent"}),
        ):
            try:
                _http(url, body, timeout=3.0)
            except RoverLinkError:
                pass
        self._release()

    # --- лента --------------------------------------------------------------

    def led(self, enabled: bool, effect: str, brightness: float, speed: float,
            primary: str, secondary: str) -> None:
        resp = _http(f"{self.web}/api/led_strip/command",
                     {"enabled": enabled, "effect": effect, "brightness": brightness,
                      "effect_speed_hz": speed, "primary_color": primary,
                      "secondary_color": secondary}, timeout=4.0)
        ok = (resp.get("response") or {}).get("success", resp.get("ok"))
        if not ok:
            raise RoverLinkError(f"лента не приняла команду: {resp}")


class DryBackend:
    """Ровер понарошку: ни сети, ни железа. Nav2 «готов», «доезжает» мгновенно.

    Нужен для --dry и для тестов: логика агента (соседство клеток, лиз-как-факт,
    подтверждение по позе) проверяется без ровера.
    """

    def __init__(self, anchor: Anchor, start_cell) -> None:
        self.anchor = anchor
        self._pose = anchor.cell_to_m(start_cell) + (0.0,)
        self.leased = False

    def read(self, with_battery: bool = True) -> dict:
        return {"link": True, "nav_ready": True, "pose": self._pose,
                "frame_id": "map", "battery": 12.4 if with_battery else None}

    def goal(self, x: float, y: float, yaw_deg: float, request_id: str) -> None:
        self.leased = True
        self._pose = (x, y, yaw_deg)  # долетел мгновенно: подтверждение по позе пройдёт

    def nav_status(self) -> dict:
        return {"state": "succeeded"}

    def cancel(self, request_id: str) -> None:
        self.leased = False

    def hard_stop(self) -> None:
        self.leased = False

    def led(self, *a, **k) -> None:
        pass


# ═══════════════════════════════════════════════════════════════════════════
#  АГЕНТ
# ═══════════════════════════════════════════════════════════════════════════


class Busy(Exception):
    pass


class Refused(Exception):
    pass


class Job:
    """Одна исполняемая команда: её номер и флаг «тебя сменили» (см. drone_agent)."""

    def __init__(self, seq: int, name: str) -> None:
        self.seq = seq
        self.name = name
        self.cancel = threading.Event()


class Agent:
    role = "rover"

    def __init__(self, args, backend, anchor: Anchor) -> None:
        self.args = args
        self.backend = backend
        self.anchor = anchor
        self.name = args.name
        self.cell = tuple(int(v) for v in args.cell.split(","))
        # idle | moving | stopped | error
        self.state = "idle"
        self.led_mode = "off"
        self.last_error = ""
        self._lock = threading.Lock()
        self._busy = False
        self.current = ""
        self._job: Job | None = None
        self._seq = 0
        self._done: dict[str, dict] = {}
        self._done_lock = threading.Lock()
        self._last_move = time.monotonic()
        self._last_request = time.monotonic()
        # Снимок состояния ровера обновляет фоновый опрос: /status обязан отвечать
        # мгновенно из кэша, а не висеть на 3-секундном запросе к роверу.
        self._snap = {"link": False, "nav_ready": False, "pose": None,
                      "frame_id": "", "battery": None}

    # --- статус -------------------------------------------------------------

    def status(self) -> dict:
        snap = self._snap
        st = {
            "ok": True,
            "role": self.role,
            "name": self.name,
            "state": self.state,
            "cell": list(self.cell),
            "since_move": round(time.monotonic() - self._last_move, 2),
            "busy": self._busy,
            "led": self.led_mode,
            "link": snap["link"],
            "nav_ready": snap["nav_ready"],
            "version": VERSION,
        }
        if snap["pose"] is not None:
            x, y, yaw = snap["pose"]
            st["pose"] = [round(x, 2), round(y, 2), round(yaw, 1)]
            st["frame_id"] = snap["frame_id"]
            # Клетка по живой позе — для сверки с confirmed cell и для глаз оператора.
            st["pose_cell"] = list(self.anchor.m_to_cell(x, y))
        if snap["battery"] is not None:
            st["battery_v"] = round(snap["battery"], 2)
        if self.args.dry:
            st["dry"] = True
        if self.last_error:
            st["last_error"] = self.last_error
        return st

    def poller(self) -> None:
        """Фоновый опрос ровера: держит снимок свежим, не блокируя /status."""
        while True:
            try:
                self._snap = self.backend.read()
            except Exception as exc:  # noqa: BLE001 — опрос падать не должен
                self._snap = {**self._snap, "link": False}
                self.last_error = f"опрос: {exc}"
            time.sleep(self.args.poll_period)

    # --- дедуп/запуск (та же механика, что у drone_agent) -------------------

    def once(self, command_id: str, run):
        if not command_id:
            return run()
        with self._done_lock:
            if command_id in self._done:
                say(f"повтор команды {command_id[:8]} — второй раз не исполняю")
                return {**self._done[command_id], "deduplicated": True}
            result = run()
            self._done[command_id] = result
            while len(self._done) > DEDUP_KEEP:
                del self._done[next(iter(self._done))]
            return result

    def start(self, name: str, fn, *, preempt: bool = False) -> dict:
        with self._lock:
            if self._busy and not preempt:
                raise Busy(f"{self.name} занят: идёт «{self.current}»")
            if self._job is not None:
                self._job.cancel.set()
            self._seq += 1
            job = self._job = Job(self._seq, name)
            self._busy = True
            self.current = name
            was = self.state

        def worker():
            try:
                fn(job)
            except Refused as exc:
                # Отказ ехать (Nav2 не готов, поза не в карте) — ровер не тронулся:
                # возвращаем прежнее состояние, а не оставляем «едет».
                if self._job is job:
                    self.state = was
                    self.last_error = f"{name}: {exc}"
                say(f"ОТКАЗ в «{name}»: {exc}")
            except Exception as exc:  # noqa: BLE001 — падать целиком агенту нельзя
                if self._job is job:
                    self.state = "error"
                    self.last_error = f"{name}: {exc}"
                say(f"ОШИБКА в «{name}»: {exc}")
            finally:
                with self._lock:
                    if self._job is job:
                        self._busy = False
                        self._job = None

        threading.Thread(target=worker, daemon=True).start()
        return {"accepted": True, "command": name}

    @staticmethod
    def _wait(job: Job, seconds: float) -> bool:
        return not job.cancel.wait(seconds)

    # --- движение -----------------------------------------------------------

    def check_drive(self, cell):
        """Проверка команды без исполнения: отказ приходит сразу, а не в конце.

        Диспетчер обязан ехать по одной клетке (так же считается игровой заряд), а
        мок и борт одинаково придирчивы — иначе диспетчер, отлаженный на всепрощающем
        роверe, на поле развалится.
        """
        target = (int(cell[0]), int(cell[1]))
        dist = abs(target[0] - self.cell[0]) + abs(target[1] - self.cell[1])
        if dist > 1:
            raise Refused(
                f"rover: {list(self.cell)} -> {list(target)} не соседняя клетка "
                "(диспетчер обязан ехать по одной клетке)"
            )
        if self.state == "moving":
            raise Refused("rover: уже едет, вторая команда движения отклонена")
        return target

    def drive(self, cell) -> dict:
        target = self.check_drive(cell)
        return self.start("drive", lambda job: self._drive(target, job))

    def _drive(self, target, job: Job) -> None:
        if target == self.cell:  # уже здесь — засчитываем как доехал, лиз не берём
            self._set(job, state="idle", cell=target, moved=True)
            return
        x, y = self.anchor.cell_to_m(target)
        yaw = self._snap["pose"][2] if self._snap.get("pose") else self.args.goal_yaw
        request_id = f"{self.name}-{self._seq}"
        say(f"ЕДУ в клетку {list(target)} = ({x:.2f}, {y:.2f}) м карты")
        self._set(job, state="moving")
        self.last_error = ""

        arrived = self._go_once(target, x, y, yaw, request_id, job)
        if arrived is None:  # команду сменили посреди заезда
            return
        for attempt in range(self.args.retries):
            if arrived:
                break
            # Nav2 умеет отдать aborted, стоя уже почти у цели; ретрай — грабли из
            # docs/openclaw/03. Дальше — честный провал, а не бесконечные попытки.
            say(f"ровер не доехал — повтор {attempt + 1}")
            arrived = self._go_once(target, x, y, yaw, f"{request_id}-r{attempt}", job)
            if arrived is None:
                return
        if arrived:
            self._set(job, state="idle", cell=target, moved=True)
            say(f"доехал в {list(target)}")
        else:
            # Ровер ехал, но до цели не дошёл: это провал, а не отказ до старта —
            # оставляем error, чтобы диспетчер увидел это в статусе, а не «еду вечно».
            if self._set(job, state="error"):
                self.last_error = f"не доехал в {list(target)} за {self.args.drive_timeout:g} с"
            say(f"НЕ ДОЕХАЛ в {list(target)}")

    def _go_once(self, target, x, y, yaw, request_id, job: Job) -> bool | None:
        """Один заезд Nav2 до цели. True — доехал, False — нет, None — команду сменили.

        Прибытие — по фактической позе (расстояние до цели ≤ arrive_tol), а не по
        строке состояния: имя успеха у сборок разное, а Nav2 умеет отдать goal и не
        доехать. Поэтому опрашиваем и статус, и позу, и верим позе.
        """
        def near() -> bool:
            # Позу берём СВЕЖУЮ, а не из фонового снимка: тот обновляется раз в
            # ~0,5 с и для «доехал ли» слишком редкий. Заодно освежаем self._snap —
            # оператор видит в /status живую позу ровера прямо во время заезда.
            self._snap = self.backend.read(with_battery=False)
            pose = self._snap.get("pose")
            return pose is not None and math.hypot(
                pose[0] - x, pose[1] - y) <= self.args.arrive_tol

        try:
            self.backend.goal(x, y, yaw, request_id)
        except RoverRefused as exc:
            raise Refused(str(exc)) from exc
        deadline = time.monotonic() + self.args.drive_timeout
        try:
            while time.monotonic() < deadline:
                if job.cancel.is_set():
                    return None
                nav = str(self.backend.nav_status().get("state", "")).lower()
                if near():
                    return True
                if nav not in NAV_ACTIVE:
                    # Терминальное состояние, а у цели не стоим — дадим позе один
                    # такт устояться и решаем окончательно.
                    if not self._wait(job, self.args.poll):
                        return None
                    return near()
                if not self._wait(job, self.args.poll):
                    return None
            return False
        finally:
            self.backend.cancel(request_id)

    def _set(self, job: Job, state=None, cell=None, moved=False) -> bool:
        if self._job is not job:
            return False
        if state is not None:
            self.state = state
        if cell is not None:
            self.cell = (int(cell[0]), int(cell[1]))
        if moved:
            self._last_move = time.monotonic()
        return True

    # --- лента --------------------------------------------------------------

    def led(self, mode: str, color: str | None = None) -> dict:
        if mode not in LED_EFFECT:
            raise Refused(f"rover: неизвестный режим ленты {mode!r}")
        primary = color or self.args.led_color
        try:
            self.backend.led(
                enabled=(mode != "off"), effect=LED_EFFECT[mode],
                brightness=self.args.led_brightness, speed=self.args.led_speed,
                primary=primary, secondary="#000000",
            )
        except RoverLinkError as exc:
            # Лента — доказательство миссии (мигалка у башни, светодиод доставки);
            # молча проглотить отказ нельзя, но и валить агент из-за ленты незачем.
            self.last_error = f"led: {exc}"
            return {"accepted": False, "led": mode, "error": str(exc)}
        self.led_mode = mode
        return {"accepted": True, "led": mode}

    # --- остановка ----------------------------------------------------------

    def stop(self) -> dict:
        say("СТОП")
        return self.start("stop", self._stop, preempt=True)

    def _stop(self, job: Job) -> None:
        try:
            self.backend.hard_stop()
        finally:
            self._set(job, state="stopped", moved=True)

    # --- сторож (Failsafe: потеряли ноутбук — стоп) -------------------------

    def touch(self) -> None:
        self._last_request = time.monotonic()

    def watchdog(self) -> None:
        limit = self.args.watchdog
        if limit <= 0:
            return
        while True:
            time.sleep(0.5)
            quiet = time.monotonic() - self._last_request
            if quiet > limit and self.state == "moving":
                say(f"СТОРОЖ: {quiet:.0f} с без команд — торможу ровер сам")
                self._last_request = time.monotonic()
                self.start("watchdog-stop", self._stop, preempt=True)


# ═══════════════════════════════════════════════════════════════════════════
#  СЕТЬ
# ═══════════════════════════════════════════════════════════════════════════


class Handler(BaseHTTPRequestHandler):
    agent: Agent = None  # подставляется в main()

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    def log_message(self, fmt: str, *args) -> None:
        pass  # свой вывод понятнее

    def do_GET(self) -> None:  # noqa: N802
        self.agent.touch()
        if self.path in ("/status", "/"):
            return self._json(200, self.agent.status())
        self._json(404, {"error": f"нет такого пути: {self.path}"})

    def do_POST(self) -> None:  # noqa: N802
        self.agent.touch()
        body = self._body()
        cid = str(body.get("command_id") or "")
        try:
            if self.path == "/drive":
                return self._json(200, self.agent.once(
                    cid, lambda: self.agent.drive(body["cell"])))
            if self.path == "/led":
                # Лента синхронна: это короткая команда без фонового исполнения,
                # и дедуп ей не нужен (повтор просто повторит тот же режим).
                return self._json(200, self.agent.led(
                    body.get("mode", "off"), body.get("color")))
            if self.path == "/stop":
                return self._json(200, self.agent.once(cid, self.agent.stop))
        except Busy as exc:
            return self._json(409, {"error": str(exc)})
        except Refused as exc:
            return self._json(403, {"error": str(exc)})
        except KeyError as exc:
            return self._json(400, {"error": f"в теле запроса нет поля {exc}"})
        except Exception as exc:  # noqa: BLE001
            return self._json(500, {"error": str(exc)})
        self._json(404, {"error": f"нет такого пути: {self.path}"})


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Агент ровера «Города дронов»")
    p.add_argument("--port", type=int, default=8010, help="порт нашего контракта")
    p.add_argument("--name", default="rover", help="имя в логе диспетчера")
    p.add_argument("--cell", default="3,3", help="стартовая клетка, col,row")
    p.add_argument("--rover-ip", default="192.168.1.125",
                   help="адрес ровера в сети (DHCP: на площадке будет другой)")
    p.add_argument("--ctrl-port", type=int, default=8767, help="порт rover_control_api")
    p.add_argument("--web-port", type=int, default=8765, help="порт rover_web (лента, стоп)")
    p.add_argument("--map-label", default="ofice2", help="метка SLAM-карты ровера")
    # Привязка сетки к карте ровера — калибруется на площадке (см. RUN.md).
    p.add_argument("--cell-size", type=float, default=0.8, help="сторона клетки, м")
    p.add_argument("--map-x0", type=float, default=0.0, help="метры карты у клетки [0,0]")
    p.add_argument("--map-y0", type=float, default=0.0)
    p.add_argument("--map-yaw", type=float, default=0.0, help="поворот сетки к карте, рад")
    p.add_argument("--goal-yaw", type=float, default=0.0,
                   help="курс цели, град, когда своя поза неизвестна")
    p.add_argument("--arrive-tol", type=float, default=0.22,
                   help="доехал, если ближе этого к цели, м (грабли Nav2)")
    p.add_argument("--drive-timeout", type=float, default=30.0, help="ждать переезд, с")
    p.add_argument("--retries", type=int, default=1, help="повторов заезда при недоезде")
    p.add_argument("--poll", type=float, default=0.3, help="период опроса Nav2 при заезде, с")
    p.add_argument("--poll-period", type=float, default=0.5,
                   help="период фонового опроса состояния ровера, с")
    p.add_argument("--watchdog", type=float, default=3.0,
                   help="стоп, если нет команд N с (0 — выкл)")
    p.add_argument("--led-color", default="#FF0000", help="цвет ленты по умолчанию")
    p.add_argument("--led-brightness", type=float, default=0.35)
    p.add_argument("--led-speed", type=float, default=2.0, help="частота мигания, Гц")
    p.add_argument("--dry", action="store_true",
                   help="без ровера: отвечать и «ездить» мгновенно")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    anchor = Anchor(args.cell_size, args.map_x0, args.map_y0, args.map_yaw)
    start_cell = tuple(int(v) for v in args.cell.split(","))
    if args.dry:
        backend = DryBackend(anchor, start_cell)
    else:
        backend = ControlApiBackend(
            args.rover_ip, args.ctrl_port, args.web_port, args.map_label,
            client_id=f"city-{args.name}",
        )
    agent = Agent(args, backend, anchor)

    handler = type("Bound", (Handler,), {"agent": agent})
    try:
        server = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    except OSError as exc:
        say(f"ПОРТ {args.port} УЖЕ ЗАНЯТ — похоже, агент уже запущен ({exc})")
        say(f"  или запустить этот на другом порту:  --port {args.port + 1}")
        return 1
    threading.Thread(target=agent.poller, daemon=True).start()
    threading.Thread(target=agent.watchdog, daemon=True).start()

    where = "ЗАГЛУШКА (--dry)" if args.dry else f"{args.rover_ip} (упр {args.ctrl_port}, веб {args.web_port})"
    say(f"агент ровера «{args.name}» слушает порт {args.port}, ровер: {where}")
    say(f"проверка: curl http://127.0.0.1:{args.port}/status")
    if not args.dry:
        time.sleep(args.poll_period + 0.2)  # дать фоновому опросу снять первый снимок
        snap = agent.status()
        say(f"ровер {'на связи' if snap.get('link') else 'НЕ ОТВЕЧАЕТ'}, "
            f"Nav2 {'готов' if snap.get('nav_ready') else 'не готов'}")
        if (args.map_x0, args.map_y0, args.map_yaw) == (0.0, 0.0, 0.0):
            say("ВНИМАНИЕ: привязка сетки к карте не калибрована "
                "(--map-x0/--map-y0/--map-yaw = 0) — переезды поедут не туда")
    say("остановить: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        say("остановка по Ctrl+C")
        if agent.state == "moving":
            say("ровер едет — торможу перед выходом")
            agent.stop()
            time.sleep(1.0)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
