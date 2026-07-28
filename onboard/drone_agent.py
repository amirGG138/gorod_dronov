#!/usr/bin/env python3
"""Дрон-монитор: борт отвечает на команды диспетчера по сети.

Один файл. Копируется на дрон и запускается ВНУТРИ контейнера sverk_ros2:

    python3 drone_agent.py --port 8020 --name m1

Проверка с ноутбука (адрес дрона подставить свой):

    curl http://192.168.1.50:8020/status
    curl -X POST http://192.168.1.50:8020/takeoff -d '{"alt":1.5}'
    curl http://192.168.1.50:8020/shot -o kadr.jpg
    curl -X POST http://192.168.1.50:8020/land

Что важно знать про этот файл (всё добыто на живом железе, не выдумано):

* Камера отдаёт yuv422_yuy2, штатный перевод в картинку на нём падает. Без патча
  patch_yuv не будет НИ ОДНОГО кадра. Взято из нашего же кода «Змейки»
  (sverh_snake/Archipelago2026/fly_head.py:173).
* navigate издаётся РОВНО ОДИН РАЗ на команду. Повторный вызов переинициализирует
  траекторию в контроллере, и дрон бесконечно начинает заход заново, никуда не летя.
* auto_arm=True всегда: без него просевший и дизармившийся дрон уже не поднимется.
* get_telemetry на наших сборках виснет без полётного контроллера, а /status обязан
  отвечать всегда. Поэтому статус собирается из последней команды, а телеметрия —
  только по флагу --telemetry.
* land() может вернуть успех и ничего не сделать, а на части сборок принимает
  timeout и без него бросает TypeError. Обе сигнатуры обёрнуты, посадка повторяется.
* Монитор по полю НЕ ЛЕТАЕТ: взлетел со своей площадки, завис, снял кадр вниз, сел.
  Команда /goto есть, но без --allow-goto отвечает отказом.

Требуется только стандартная библиотека + sverk_interfaces + cv2/numpy, которые на
борту уже стоят. Режим --dry позволяет запустить файл где угодно без железа.
"""

from __future__ import annotations

import argparse
import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "1.0"

# Заглушка-кадр для режима --dry: настоящий, хоть и крохотный, JPEG.
DRY_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABsSFBcUERsXFhceHBsgKEIrKCUlKFE6PTBCYFVlZF9VXVtqeJmB"
    "anGQc1tdhbWGkJ6jq62rZ4C8ybqmx5moq6T/2wBDARweHigjKE4rK06kbl1upKSkpKSkpKSkpKSkpKSkpKSk"
    "pKSkpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKT/wAARCAAQABADASIAAhEBAxEB/8QAFQABAQAAAAAA"
    "AAAAAAAAAAAAAAP/xAAaEAACAgMAAAAAAAAAAAAAAAAEEgAREyJB/8QAFAEBAAAAAAAAAAAAAAAAAAAAAP/E"
    "ABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AJDD522Va5cEj4F2Zr5UDEYG1Zq7UEkZ11Vb7cD/"
    "2Q=="
)


def say(text: str) -> None:
    """Строка в терминал дрона. Её читает человек, стоящий рядом с аппаратом."""
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
#  КАМЕРА
# ═══════════════════════════════════════════════════════════════════════════


def patch_yuv(drone, color: str = "bgr") -> bool:
    """Научить камеру отдавать картинку: бортовая может публиковать yuv422_yuy2, а to_cv2 его не знает.

    Порядок каналов на выходе делаем таким же, как у штатного take_picture (см. --color),
    иначе один и тот же кадр будет разного цвета в зависимости от сборки камеры.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        say("ВНИМАНИЕ: нет cv2/numpy — кадры отдавать нечем")
        return False

    image = getattr(drone, "image", None)
    original = getattr(image, "to_cv2", None)
    if original is None:
        return False

    target = cv2.COLOR_YUV2RGB_YUY2 if color == "rgb" else cv2.COLOR_YUV2BGR_YUY2

    def to_cv2(msg):
        if (getattr(msg, "encoding", "") or "").lower() in ("yuv422_yuy2", "yuyv", "yuv422"):
            yuv = np.frombuffer(msg.data, np.uint8).reshape((msg.height, msg.width, 2))
            return cv2.cvtColor(yuv, target)
        return original(msg)

    image.to_cv2 = to_cv2
    return True


def encode_jpeg(frame, color: str = "bgr") -> bytes | None:
    """Сжать кадр в JPEG.

    Порядок каналов у камеры борта — BGR, как и объявлено в топике (bgr8): проверено
    глазами на полу известного цвета 2026-07-28. cv2.imencode ждёт ровно его, поэтому
    по умолчанию кадр не трогаем. Флаг --color rgb оставлен на случай другой сборки
    камеры: если на кадре красное выглядит синим, каналы надо переставить.
    """
    import cv2

    if color == "rgb":
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes() if ok else None


# ═══════════════════════════════════════════════════════════════════════════
#  БОРТ
# ═══════════════════════════════════════════════════════════════════════════


class Agent:
    """Состояние борта и все обращения к железу. Команды исполняются по одной."""

    role = "drone"

    def __init__(self, args) -> None:
        self.args = args
        self.name = args.name
        self.cell = [int(v) for v in args.cell.split(",")]
        self.alt = 0.0
        self.state = "idle"  # idle | taking_off | hover | landing | landed | error
        self.last_error = ""
        self.frames = 0
        self.dry = args.dry
        self.camera_ok = False
        self.drone = None
        self._lock = threading.Lock()
        self._busy = False
        self.current = ""
        self._last_move = time.monotonic()
        self._last_request = time.monotonic()

    # --- железо -------------------------------------------------------------

    def open(self) -> None:
        if self.dry:
            say("режим --dry: железо не трогаем, отвечаем как дрон и ничего не делаем")
            return
        import sverk_interfaces

        say("подключаюсь к дрону…")
        self.drone = sverk_interfaces.init(Nodename=f"agent_{self.name}")
        self.camera_ok = patch_yuv(self.drone, self.args.color)
        say(
            f"дрон на связи, камера {'готова' if self.camera_ok else 'НЕ ГОТОВА'}"
            f" (цвет: {self.args.color})"
        )

    def close(self) -> None:
        if self.drone is not None:
            try:
                self.drone.close()
            except Exception as exc:  # noqa: BLE001 — на выходе глушим всё
                say(f"закрытие: {exc}")

    # --- отчёт о состоянии --------------------------------------------------

    def status(self) -> dict:
        st = {
            "ok": True,
            "role": self.role,
            "name": self.name,
            "state": self.state,
            "cell": self.cell,
            "alt": round(self.alt, 2),
            "since_move": round(time.monotonic() - self._last_move, 2),
            "busy": self._busy,
            "camera": self.camera_ok,
            "version": VERSION,
        }
        if self.dry:
            st["dry"] = True  # честно: на том конце заглушка, а не аппарат
        if self.last_error:
            st["last_error"] = self.last_error
        if self.args.telemetry and self.drone is not None:
            # По умолчанию выключено: на наших сборках вызов виснет без полётного
            # контроллера, а /status обязан отвечать всегда.
            try:
                tel = self.drone.control.get_telemetry(frame_id="body")
                st["telemetry"] = {k: getattr(tel, k, None) for k in ("x", "y", "z", "armed", "mode")}
            except Exception as exc:  # noqa: BLE001
                st["telemetry_error"] = str(exc)
        return st

    # --- команды ------------------------------------------------------------

    def start(self, name: str, fn) -> dict:
        """Принять команду и исполнять её в фоне: ответ по сети должен быть мгновенным."""
        with self._lock:
            if self._busy:
                raise Busy(f"{self.name} занят: идёт «{self.current}»")
            self._busy = True
            self.current = name

        def worker():
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 — падать целиком борту нельзя
                self.state = "error"
                self.last_error = f"{name}: {exc}"
                say(f"ОШИБКА в «{name}»: {exc}")
            finally:
                self._busy = False

        threading.Thread(target=worker, daemon=True).start()
        return {"accepted": True, "command": name}

    def takeoff(self, alt: float) -> dict:
        if self.state in ("taking_off", "hover"):
            # Повторная команда взлёта намеренно не доходит до navigate: второй вызов
            # переинициализирует траекторию, и дрон зависает, начиная заход заново.
            return {"accepted": True, "note": "взлёт уже идёт или дрон в воздухе"}
        return self.start("takeoff", lambda: self._takeoff(alt))

    def _takeoff(self, alt: float) -> None:
        alt = min(float(alt), self.args.max_alt)
        self.state = "taking_off"
        self.last_error = ""
        say(f"ВЗЛЁТ на {alt:g} м")
        if self.dry:
            time.sleep(2.0)
        else:
            # Ровно один navigate: повторный вызов переинициализирует траекторию.
            resp = self.drone.control.navigate(
                x=0.0, y=0.0, z=alt, yaw=0.0,
                speed=self.args.climb_speed, frame_id="body", auto_arm=True,
            )
            ok = getattr(resp, "success", True)
            say(f"взлёт принят: {ok} {getattr(resp, 'message', '')}")
            if resp is not None and not ok:
                raise RuntimeError(f"взлёт не принят: {getattr(resp, 'message', '')}")
            # Ждём набор высоты плюс время на успокоение: командовать раскачанным
            # дроном нельзя, и кадр с качающегося борта смазан.
            time.sleep(alt / max(self.args.climb_speed, 0.05) + self.args.settle)
        self.alt = alt
        self._last_move = time.monotonic()
        self.state = "hover"
        say(f"вишу на {alt:g} м")

    def land(self) -> dict:
        return self.start("land", self._land)

    def _land(self) -> None:
        self.state = "landing"
        say("ПОСАДКА")
        if self.dry:
            time.sleep(2.0)
            self.alt = 0.0
            self._last_move = time.monotonic()
            self.state = "landed"
            return
        for attempt in range(1, 4):
            try:
                try:
                    resp = self.drone.control.land()
                except TypeError:  # сборка со старой сигнатурой
                    resp = self.drone.control.land(timeout=10.0)
            except Exception as exc:  # noqa: BLE001
                say(f"посадка: попытка {attempt} сорвалась — {exc}")
                time.sleep(1.0)
                continue
            ok = getattr(resp, "success", True)
            say(f"посадка: попытка {attempt} — {ok} {getattr(resp, 'message', '')}")
            if ok:
                time.sleep(self.args.land_wait)
                self.alt = 0.0
                self._last_move = time.monotonic()
                # Подтвердить посадку нечем (телеметрии не доверяем, камера смотрит
                # вниз в пол), поэтому состояние честное: команда принята и отработана.
                self.state = "landed"
                say("сел (по факту принятой команды; глазами подтвердить обязательно)")
                return
            time.sleep(1.0)
        self.state = "land_unconfirmed"
        self.last_error = "посадка не подтверждена: сажайте пультом"
        say("ПОСАДКА НЕ ПОДТВЕРЖДЕНА — сажайте пультом")

    def goto(self, cell, alt: float) -> dict:
        if not self.args.allow_goto:
            raise Refused(
                "перелёт по полю запрещён: монитор снимает со своей площадки. "
                "Если это осознанно — запустите агент с ключом --allow-goto"
            )
        if self.state != "hover":
            raise Refused("перелёт до взлёта")
        return self.start("goto", lambda: self._goto(cell, alt))

    def cell_to_m(self, cell) -> tuple[float, float]:
        """Клетка поля -> метры кадра aruco_map.

        Начало кадра aruco_map — центр квадрата из четырёх маркеров, а он же центр
        поля (docs/field-map/README.md). Поэтому центр клетки [col,row] на поле
        6x6 по 0,8 м это ((col-2.5)*0.8, (row-2.5)*0.8).
        """
        cols, rows = (int(v) for v in self.args.grid.split(","))
        size = self.args.cell_size
        return ((cell[0] - (cols - 1) / 2.0) * size, (cell[1] - (rows - 1) / 2.0) * size)

    def _goto(self, cell, alt: float) -> None:
        x, y = self.cell_to_m(cell)
        alt = min(float(alt), self.args.max_alt)
        say(f"перелёт в клетку {list(cell)} = ({x:.2f}, {y:.2f}) м на {alt:g} м")
        if self.dry:
            time.sleep(2.0)
        else:
            resp = self.drone.control.navigate(
                x=x, y=y, z=alt, yaw=0.0, speed=self.args.speed,
                frame_id=self.args.frame, auto_arm=True,
            )
            if resp is not None and not getattr(resp, "success", True):
                raise RuntimeError(f"перелёт не принят: {getattr(resp, 'message', '')}")
            time.sleep(self.args.hop_wait)
        self.cell = [int(cell[0]), int(cell[1])]
        self.alt = alt
        self._last_move = time.monotonic()
        self.state = "hover"

    def shot(self) -> bytes:
        if self.dry:
            self.frames += 1
            return DRY_JPEG
        if not self.camera_ok:
            raise NoFrame("камера не готова (нет cv2/numpy или патча yuv)")
        try:
            frame = self.drone.image.take_picture(timeout=2.0)
        except Exception as exc:  # noqa: BLE001
            raise NoFrame(f"камера не отдала кадр: {exc}") from exc
        if frame is None or getattr(frame, "ndim", 0) != 3 or frame.size == 0:
            raise NoFrame("камера отдала пустой кадр")
        data = encode_jpeg(frame, self.args.color)
        if not data:
            raise NoFrame("кадр не удалось сжать в JPEG")
        self.frames += 1
        return data

    def stop(self) -> dict:
        """Аварийная остановка: для дрона это немедленная посадка."""
        say("СТОП — сажусь")
        self._busy = False  # аварийная команда важнее текущей
        return self.start("stop-land", self._land)

    # --- сторож -------------------------------------------------------------

    def touch(self) -> None:
        self._last_request = time.monotonic()

    def watchdog(self) -> None:
        """Потеряли ноутбук — садимся сами (регламент 2.6: Failsafe при потере сигнала)."""
        limit = self.args.watchdog
        if limit <= 0:
            return
        while True:
            time.sleep(0.5)
            quiet = time.monotonic() - self._last_request
            if quiet > limit and self.state in ("taking_off", "hover"):
                say(f"СТОРОЖ: {quiet:.0f} с без команд с ноутбука — сажусь сам")
                self._last_request = time.monotonic()
                try:
                    self.start("watchdog-land", self._land)
                except Busy:
                    pass


class Busy(Exception):
    pass


class Refused(Exception):
    pass


class NoFrame(Exception):
    pass


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
        pass  # свой вывод понятнее: сыпать в терминал дрона строками HTTP незачем

    def do_GET(self) -> None:  # noqa: N802
        self.agent.touch()
        try:
            if self.path in ("/status", "/"):
                return self._json(200, self.agent.status())
            if self.path == "/shot":
                data = self.agent.shot()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                return self.wfile.write(data)
        except NoFrame as exc:
            return self._json(503, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return self._json(500, {"error": str(exc)})
        self._json(404, {"error": f"нет такого пути: {self.path}"})

    def do_POST(self) -> None:  # noqa: N802
        self.agent.touch()
        body = self._body()
        try:
            if self.path == "/takeoff":
                return self._json(200, self.agent.takeoff(body.get("alt", self.agent.args.alt)))
            if self.path == "/land":
                return self._json(200, self.agent.land())
            if self.path == "/goto":
                return self._json(
                    200, self.agent.goto(body["cell"], body.get("alt", self.agent.args.alt))
                )
            if self.path == "/stop":
                return self._json(200, self.agent.stop())
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
    p = argparse.ArgumentParser(description="Агент дрона-монитора «Города дронов»")
    p.add_argument("--port", type=int, default=8020)
    p.add_argument("--name", default="m1", help="имя борта в логе диспетчера")
    p.add_argument("--cell", default="1,1", help="на какой площадке стоит, col,row")
    p.add_argument("--alt", type=float, default=1.5, help="рабочая высота, м")
    p.add_argument("--max-alt", type=float, default=3.5, help="потолок, м (регламент 2.6: 4 м)")
    p.add_argument("--climb-speed", type=float, default=0.3, help="скорость набора высоты, м/с")
    p.add_argument("--speed", type=float, default=0.6, help="скорость перелёта, м/с")
    p.add_argument("--settle", type=float, default=2.5, help="пауза на успокоение после взлёта, с")
    p.add_argument("--land-wait", type=float, default=4.0, help="пауза на снижение, с")
    p.add_argument("--hop-wait", type=float, default=6.0, help="пауза на перелёт, с")
    p.add_argument("--watchdog", type=float, default=8.0, help="сесть, если нет команд N с (0 — выкл)")
    p.add_argument("--frame", default="aruco_map", help="кадр координат для перелётов")
    p.add_argument("--grid", default="6,6", help="размер поля в клетках")
    p.add_argument("--cell-size", type=float, default=0.8, help="сторона клетки, м")
    p.add_argument("--allow-goto", action="store_true", help="разрешить перелёты по полю")
    p.add_argument("--telemetry", action="store_true", help="добавлять телеметрию в статус (может виснуть)")
    p.add_argument(
        "--color", choices=("bgr", "rgb"), default="bgr",
        help="порядок каналов у камеры борта: bgr — как на наших дронах (проверено), "
             "rgb — если на кадре красное выглядит синим",
    )
    p.add_argument("--dry", action="store_true", help="без железа: отвечать, но ничего не делать")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    agent = Agent(args)
    agent.open()

    handler = type("Bound", (Handler,), {"agent": agent})
    try:
        server = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    except OSError as exc:
        # Самая частая ошибка запуска: агент уже работает с прошлого раза. Голый
        # traceback про «Address already in use» этого не объясняет.
        say(f"ПОРТ {args.port} УЖЕ ЗАНЯТ — похоже, агент уже запущен ({exc})")
        # Скобки в шаблоне не опечатка: без них pkill/pgrep находят и убивают
        # собственную же команду (ssh-сессия падает с кодом 255).
        say('  посмотреть:  pgrep -af "[d]rone_agent"')
        say('  остановить:  pkill -9 -f "[d]rone_agent"')
        say(f"  или запустить этот на другом порту:  --port {args.port + 1}")
        agent.close()
        return 1
    threading.Thread(target=agent.watchdog, daemon=True).start()

    say(f"агент «{args.name}» слушает порт {args.port}" + (" (ЗАГЛУШКА)" if args.dry else ""))
    say(f"проверка: curl http://<адрес-дрона>:{args.port}/status")
    say("остановить: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        say("остановка по Ctrl+C")
        if agent.state in ("taking_off", "hover"):
            say("дрон в воздухе — сажаю перед выходом")
            agent._land()
    finally:
        server.server_close()
        agent.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
