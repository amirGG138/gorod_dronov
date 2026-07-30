#!/usr/bin/env python3
"""Дашборд попытки: поле, аппараты и живая лента обмена между агентами.

    python3 -m city.viz                      # взять самый свежий лог из logs/
    python3 -m city.viz --log logs/run-*.jsonl --open

ОТДЕЛЬНЫЙ ПРОЦЕСС, И ТОЛЬКО ОТДЕЛЬНЫЙ. Флага --viz у city.run нет намеренно: поток
внутри процесса диспетчера означал бы общую судьбу — занятый порт, исключение в
разборе события, зависший на записи SSE-клиент, оставленная на день страница. В
отдельном процессе всё это не значит ничего, а внутри зачётной попытки может стоить
зачёта. Цена — второе окно терминала на площадке.

ТОЛЬКО ЧТЕНИЕ. Ни одного POST, ни одной команды аппаратам: дашборд смотрит, а не
управляет. Пульт оператора есть и живёт отдельно — city/pult.py.

Источник данных — файл журнала (logs/run-*.jsonl), а не push из диспетчера. Так
получается три вещи сразу: дашборд физически не может уронить попытку; он показывает
ровно то, что уйдёт судьям (тот же файл, а не второй пересказ); и он умеет
проигрывать вчерашний прогон. Журнал флашится построчно (city/log.py), поэтому
хвост читается без всякой договорённости с писателем.

Раскладку поля страница берёт из события RUN_START (диспетчер кладёт её туда полем
layout) и только при её отсутствии — из текущего config.yaml через /api/field. Это
важнее удобства: раскладку на площадке правят каждый день, а вчерашний прогон надо
показывать таким, каким он был.

Стриминг — SSE, а не WebSocket: одна стандартная библиотека и бесплатный
авто-реконнект в браузере. Идея тайла файла событий взята из чужого решения
(docs/openclaw/snapshot/viz/server.py), код свой: их сервер сросся с их доской, а
чужих данных мы не читаем и чужую архитектуру не переносим.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import config as config_mod
from .field import Field

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "viz.html")

CHUNK = 1 << 20  # сколько байт хвоста читать за раз
TICK = 0.25  # период опроса файла, с — достаточно живо для глаза
PING = 15.0  # период комментария-пульса, с: иначе прокси рвут тихое соединение
MAX_CLIENTS = 8  # больше и не нужно, а поток на клиента стоит памяти


def newest(folder: str) -> str:
    """Самый свежий лог попытки в каталоге. Пусто — значит прогонов ещё нет."""
    runs = glob.glob(os.path.join(folder, "run-*.jsonl"))
    return max(runs, key=os.path.getmtime) if runs else ""


def read_lines(path: str, start: int) -> tuple[list[str], int]:
    """Строки с байтового смещения. Незавершённую последнюю строку не отдаёт.

    Резать надо именно по «\\n», а не читать построчно с fh.tell(): файл, в который
    прямо сейчас пишут, умеет отдать половину строки. У нас флаш построчный, так что
    это редкость — но «редко» на площадке хуже, чем «никогда».
    """
    try:
        with open(path, "rb") as fh:
            fh.seek(start)
            chunk = fh.read(CHUNK)
    except OSError:
        return [], start
    cut = chunk.rfind(b"\n")
    if cut < 0:
        return [], start
    body = chunk[: cut + 1]
    text = body.decode("utf-8", "replace")
    return [line for line in text.splitlines() if line.strip()], start + len(body)


class Viz:
    """Что показывать: конкретный файл или «самый свежий в каталоге»."""

    def __init__(self, folder: str, fixed: str = "") -> None:
        self.folder = os.path.abspath(folder)
        self.fixed = os.path.abspath(fixed) if fixed else ""
        self.clients = 0
        self._lock = threading.Lock()

    def path_for(self, run: str = "") -> str:
        """Путь к журналу по имени файла. Пусто — текущий (свежий или заданный)."""
        if run:
            # Имя приходит из браузера: наружу из каталога логов пускать нельзя.
            candidate = os.path.abspath(os.path.join(self.folder, os.path.basename(run)))
            return candidate if os.path.isfile(candidate) else ""
        if self.fixed:
            return self.fixed if os.path.isfile(self.fixed) else ""
        return newest(self.folder)

    def runs(self) -> list[dict]:
        found = []
        for path in sorted(glob.glob(os.path.join(self.folder, "run-*.jsonl")), reverse=True):
            try:
                stat = os.stat(path)
            except OSError:
                continue
            found.append({
                "run": os.path.basename(path),
                "size": stat.st_size,
                "mtime": round(stat.st_mtime),
            })
        if self.fixed and os.path.isfile(self.fixed):
            name = os.path.basename(self.fixed)
            if not any(r["run"] == name for r in found):
                stat = os.stat(self.fixed)
                found.insert(0, {"run": name, "size": stat.st_size,
                                 "mtime": round(stat.st_mtime)})
        return found

    def field(self) -> dict:
        """Раскладка из текущего config.yaml — запас на случай лога без layout."""
        try:
            cfg = config_mod.load()
            field = Field.from_config(cfg)
        except Exception as exc:  # noqa: BLE001 — конфиг правят руками, ошибки бывают
            return {"error": f"config.yaml не прочитан: {exc}"}
        pads = cfg.get("aruco.pads", {})
        monitors = cfg.get("robots.monitors", {})
        return {
            "size": [field.cols, field.rows],
            "cell": field.cell,
            "buildings": [list(c) for c in sorted(field.buildings)],
            "tower": list(cfg.get("cells.tower", [1, 3])),
            "charge": list(cfg.get("cells.charge", [3, 3])),
            "rover_start": list(cfg.get("cells.rover_start", [3, 3])),
            "pads": {str(k): list(v) for k, v in (pads.items() if hasattr(pads, "items") else [])},
            "districts": {
                str(k): list(v)
                for k, v in (
                    cfg.get("districts", {}).items()
                    if hasattr(cfg.get("districts", {}), "items")
                    else []
                )
            },
            "monitors": {
                name: list(mon.get("pad", [0, 0]))
                for name, mon in (monitors.items() if hasattr(monitors, "items") else [])
            },
            "source": "config.yaml",
        }

    def shot(self, wanted: str) -> bytes:
        """Кадр-доказательство. Пусто — читать нечего или путь ведёт наружу.

        Путь приходит из поля shot событий SCAN, а оно относительно рабочего каталога
        ДИСПЕТЧЕРА (logs/shots/...), не нашего. Поэтому от него берётся только имя
        файла, а искать мы идём в подкаталог shots рядом с журналом: заодно это
        полностью снимает вопрос обхода каталогов — из имени файла его не построить.
        Размеченная копия (*-mark.jpg) предпочитается исходнику: она и есть материал
        техзащиты (на ней видно, что именно зрение приняло за очаг).
        """
        name = os.path.basename(wanted)
        if not name or name.startswith("."):
            return b""
        target = os.path.realpath(os.path.join(self.folder, "shots", name))
        root = os.path.realpath(self.folder)
        if os.path.commonpath([target, root]) != root:
            return b""  # страховка на случай странной раскладки символических ссылок
        marked = target[:-4] + "-mark.jpg" if target.lower().endswith(".jpg") else ""
        for candidate in (marked, target):
            if candidate and os.path.isfile(candidate):
                try:
                    with open(candidate, "rb") as fh:
                        return fh.read()
                except OSError:
                    return b""
        return b""

    def take_slot(self) -> bool:
        with self._lock:
            if self.clients >= MAX_CLIENTS:
                return False
            self.clients += 1
            return True

    def free_slot(self) -> None:
        with self._lock:
            self.clients = max(0, self.clients - 1)


class Handler(BaseHTTPRequestHandler):
    viz: Viz = None  # подставляется в main()
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        pass  # свой вывод понятнее

    # --- ответы -------------------------------------------------------------

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, code: int = 200) -> None:
        self._send(code, "application/json; charset=utf-8",
                   json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _query(self) -> dict:
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    # --- маршруты -----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                return self._page()
            if path == "/api/field":
                return self._json(self.viz.field())
            if path == "/api/runs":
                return self._json({"runs": self.viz.runs(), "folder": self.viz.folder})
            if path == "/api/events":
                return self._events()
            if path == "/api/stream":
                return self._stream()
            if path == "/api/shot":
                return self._shot()
            self._json({"error": f"нет такого пути: {path}"}, 404)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return  # страницу закрыли посреди ответа — это норма, а не сбой

    def _page(self) -> None:
        try:
            with open(PAGE, "rb") as fh:
                body = fh.read()
        except OSError as exc:
            return self._send(500, "text/plain; charset=utf-8",
                              f"не читается {PAGE}: {exc}".encode("utf-8"))
        self._send(200, "text/html; charset=utf-8", body)

    def _events(self) -> None:
        query = self._query()
        path = self.viz.path_for(query.get("run", ""))
        if not path:
            # Прогонов ещё нет — это ожидание, а не ошибка: дашборд поднимают до
            # попытки и он подхватывает файл, когда тот появится.
            return self._json({"run": "", "from": 0, "next": 0, "lines": [], "waiting": True})
        start = max(0, int(query.get("from", 0) or 0))
        size = os.path.getsize(path)
        if size < start:
            start = 0  # файл сменился или обрезан
        lines, nxt = read_lines(path, start)
        self._json({
            "run": os.path.basename(path),
            "from": start,
            "next": nxt,
            "lines": lines,
            "size": size,
        })

    def _shot(self) -> None:
        wanted = self._query().get("path", "")
        body = self.viz.shot(wanted) if wanted else b""
        if not body:
            return self._send(403, "text/plain; charset=utf-8",
                              "кадр недоступен или лежит вне каталога журнала".encode("utf-8"))
        self._send(200, "image/jpeg", body)

    def _stream(self) -> None:
        if not self.viz.take_slot():
            return self._json({"error": f"больше {MAX_CLIENTS} страниц сразу не обслуживаем"}, 503)
        wanted = self._query().get("run", "")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def send(payload: str) -> None:
            self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
            self.wfile.flush()

        current, pos, beat = "", 0, time.monotonic()
        try:
            while True:
                path = self.viz.path_for(wanted)
                if path != current:
                    # Сменился файл (или появился первый): страница обнуляет своё
                    # состояние и начинает считать заново.
                    current, pos = path, 0
                    send(json.dumps(
                        {"kind": "run", "run": os.path.basename(path) if path else ""},
                        ensure_ascii=False,
                    ))
                if path:
                    size = os.path.getsize(path)
                    if size < pos:
                        pos = 0
                        send(json.dumps({"kind": "run", "run": os.path.basename(path),
                                         "truncated": True}, ensure_ascii=False))
                    lines, pos = read_lines(path, pos)
                    for line in lines:
                        send(line)
                    if lines:
                        beat = time.monotonic()
                if time.monotonic() - beat > PING:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    beat = time.monotonic()
                time.sleep(TICK)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return
        finally:
            self.viz.free_slot()


def _address() -> tuple[str, int]:
    """Адрес из config.yaml — тот же файл, что и у диспетчера, копии настроек нет.

    Конфиг правят руками, и сломать им дашборд нельзя: не прочитался — берутся
    встроенные значения, а не падение с трассировкой.
    """
    try:
        cfg = config_mod.load()
        return str(cfg.get("viz.host", "127.0.0.1")), int(cfg.get("viz.port", 8090))
    except Exception:  # noqa: BLE001 — показ не вправе зависеть от чужой опечатки
        return "127.0.0.1", 8090


def build_parser() -> argparse.ArgumentParser:
    host, port = _address()
    p = argparse.ArgumentParser(prog="city.viz", description="Дашборд попытки «Города дронов»")
    p.add_argument("--logs", default="logs", help="каталог с логами попыток")
    p.add_argument("--log", default="", help="конкретный лог; без него берётся самый свежий")
    p.add_argument("--port", type=int, default=port)
    p.add_argument("--host", default=host,
                   help="0.0.0.0 — показать со второго ноутбука в той же сети")
    p.add_argument("--open", action="store_true", help="открыть страницу в браузере")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    folder = os.path.dirname(os.path.abspath(args.log)) if args.log else args.logs
    viz = Viz(folder, args.log)
    handler = type("Bound", (Handler,), {"viz": viz})
    try:
        server = ThreadingHTTPServer((args.host, args.port), handler)
    except OSError as exc:
        print(f"порт {args.port} занят ({exc}) — попробуйте --port {args.port + 1}", flush=True)
        return 1
    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}"
    show = viz.path_for()
    print(f"дашборд слушает {url}\n"
          + (f"читает {show}" if show else
             f"в {viz.folder} прогонов ещё нет — подхвачу, как только появится")
          + "\nостановить: Ctrl+C", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nостановлен", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
