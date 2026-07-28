"""«Понарошечный» аппарат как отдельная программа.

Тот же контракт, что у настоящего борта, — значит, на нём отлаживается вся сетевая
часть: адреса, таймауты, отказы, порядок команд. Когда приедет железо, изменится
только адрес в config.yaml.

    python3 -m city.robots.mock_server --role rover  --port 8010
    python3 -m city.robots.mock_server --role drone  --port 8020 --cell 1,1 --name m1
"""

from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..clock import RealClock
from .base import RobotError
from .fake import FakeDrone, FakeRover, FakeVup

ROLES = {"rover": FakeRover, "drone": FakeDrone, "vup": FakeVup}

DEDUP_KEEP = 64  # сколько последних command_id помнить (столько же, сколько борт)


class Busy(Exception):
    """Аппарат занят предыдущей командой."""


class _Handler(BaseHTTPRequestHandler):
    robot = None  # подставляется в serve()
    lock = threading.Lock()
    dedup: dict = {}
    dedup_lock = threading.Lock()
    quiet = False

    # --- ответы -------------------------------------------------------------

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, code: int, payload: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            raise RobotError(f"тело запроса не разобрать: {exc}") from exc

    def log_message(self, fmt: str, *args) -> None:
        if not self.quiet:
            print(f"{self.robot.name}: {fmt % args}", flush=True)

    # --- маршруты -----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 — имя задано http.server
        try:
            with self.lock:
                if self.path == "/status":
                    return self._json(200, self.robot.status())
                if self.path == "/shot":
                    return self._bytes(200, self.robot.shot(), "image/jpeg")
        except RobotError as exc:
            return self._json(400, {"error": str(exc)})
        except AttributeError:
            return self._json(400, {"error": f"{self.robot.role} этого не умеет"})
        self._json(404, {"error": f"нет такого пути: {self.path}"})

    def _method(self, name: str):
        """Взять метод аппарата или отказать сразу.

        Проверка синхронная: «ровер не умеет взлетать» — это ответ на команду, а не
        событие, о котором диспетчер узнает когда-нибудь потом из статуса.
        """
        fn = getattr(self.robot, name, None)
        if fn is None:
            raise RobotError(f"{self.robot.role} не умеет «{name}»")
        return fn

    def _accept(self, name: str, fn) -> dict:
        """Принять команду и исполнять в фоне.

        Настоящий борт отвечает мгновенно, а летит потом: диспетчер узнаёт об
        исполнении опросом /status. Если бы мок отвечал только после посадки,
        диспетчер отладился бы на поведении, которого на железе не бывает.
        """
        with self.lock:
            if self.robot.busy:
                raise Busy(f"{self.robot.name} занят: идёт «{self.robot.current}»")
            self.robot.busy = True
            self.robot.current = name

        def worker():
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 — мок не должен падать целиком
                print(f"{self.robot.name}: ошибка в «{name}»: {exc}", flush=True)
            finally:
                self.robot.busy = False

        threading.Thread(target=worker, daemon=True).start()
        return {"accepted": True, "command": name}

    def _once(self, command_id: str, run) -> dict:
        """Повтор команды с тем же command_id получает прежний ответ, а не второй заезд.

        Клиент переотправляет POST, когда потерялся ответ, а не команда. Настоящий
        борт это различает (onboard/drone_agent.py), значит обязан и мок: иначе
        сетевая часть отлаживается на поведении, которого на железе нет.
        """
        if not command_id:
            return run()
        with self.dedup_lock:
            if command_id in self.dedup:
                return {**self.dedup[command_id], "deduplicated": True}
            result = run()
            if result is None:  # неизвестный путь: запоминать нечего
                return None
            self.dedup[command_id] = result
            while len(self.dedup) > DEDUP_KEEP:
                del self.dedup[next(iter(self.dedup))]
            return result

    def _route(self, body: dict) -> dict | None:
        """Разобрать команду. None — такого пути нет."""
        # Команды движения проверяются сразу, а исполняются в фоне.
        if self.path == "/takeoff":
            takeoff, alt = self._method("takeoff"), float(body.get("alt", 1.5))
            return self._accept("takeoff", lambda: takeoff(alt))
        if self.path == "/land":
            return self._accept("land", self._method("land"))
        if self.path == "/goto":
            goto = self._method("goto")
            cell, alt = self._method("check_goto")(body["cell"]), float(body.get("alt", 1.5))
            return self._accept("goto", lambda: goto(cell, alt))
        if self.path == "/look":
            look = self._method("look")
            xy, alt = self._method("check_look")(body["xy"]), float(body.get("alt", 1.5))
            return self._accept("look", lambda: look(xy, alt))
        if self.path == "/drive":
            drive = self._method("drive")
            cell = self._method("check_drive")(body["cell"])
            return self._accept("drive", lambda: drive(cell))
        with self.lock:
            if self.path == "/led":
                return self.robot.led(body.get("mode", "off"), body.get("color"))
            if self.path == "/stop":
                return self.robot.stop()
        return None

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = self._body()
            # Дедупликация идёт ДО проверок команды, а не после: к моменту повтора
            # аппарат уже поехал по первой, и check_drive ответил бы «уже едет» —
            # то есть отказом на команду, которая на самом деле принята.
            cid = str(body.get("command_id") or "")
            payload = self._once(cid, lambda: self._route(body))
            if payload is not None:
                return self._json(200, payload)
        except Busy as exc:
            return self._json(409, {"error": str(exc)})
        except RobotError as exc:
            return self._json(400, {"error": str(exc)})
        except KeyError as exc:
            return self._json(400, {"error": f"в теле запроса нет поля {exc}"})
        except AttributeError:
            return self._json(400, {"error": f"{self.robot.role} этого не умеет"})
        self._json(404, {"error": f"нет такого пути: {self.path}"})


def serve(
    role: str,
    port: int,
    cell=(3, 3),
    name: str = "",
    move_time: float = 1.2,
    quiet: bool = False,
    scene=None,
):
    """Поднять мок в отдельном потоке. Возвращает (сервер, робот).

    port=0 — занять любой свободный порт; какой достался, видно в
    `server.server_address[1]` (так делают тесты, чтобы не драться за номера).

    scene — нарисованный мир для кадров (city/robots/scene.py). Без него мок отдаёт
    заглушку, и проверить по сети можно только связь, но не зрение.
    """
    clock = RealClock()
    if role == "rover":
        robot = FakeRover(clock, cell, move_time=move_time)
    else:
        robot = ROLES[role](clock, cell, name=name or role, scene=scene)

    handler = type(
        "_Bound",
        (_Handler,),
        {
            "robot": robot,
            "lock": threading.Lock(),
            "dedup": {},  # свой на каждый мок: иначе моки делят память команд
            "dedup_lock": threading.Lock(),
            "quiet": quiet,
        },
    )
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, robot


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="city.robots.mock_server", description="Мок аппарата по HTTP")
    p.add_argument("--role", choices=sorted(ROLES), required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--cell", default="3,3", help="стартовая клетка, например 1,1")
    p.add_argument("--name", default="")
    p.add_argument("--move-time", type=float, default=1.2, help="секунд на переезд в соседнюю клетку")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--blank", action="store_true", help="отдавать пустой кадр вместо нарисованного поля")
    args = p.parse_args(argv)

    cell = tuple(int(v) for v in args.cell.split(","))
    scene = None
    if args.role != "rover" and not args.blank:
        # Кадры рисуются по тому же config.yaml, что читает диспетчер: иначе проверка
        # по сети показывала бы связь, но не зрение.
        from .. import config as config_mod
        from .scene import SceneSpec

        scene = SceneSpec.from_config(config_mod.load())
    server, robot = serve(args.role, args.port, cell, args.name, args.move_time, args.quiet, scene)
    print(
        f"мок «{robot.name}» ({args.role}) слушает порт {args.port}, стоит в клетке {list(robot.cell)}\n"
        f"проверка: curl http://127.0.0.1:{args.port}/status\n"
        f"остановить: Ctrl+C",
        flush=True,
    )
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\nостановлен", flush=True)
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
