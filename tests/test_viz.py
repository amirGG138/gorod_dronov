"""Дашборд: эндпоинты, тайл журнала и то, что он не имеет права сделать.

Своей логики попытки у дашборда нет — он только читает. Поэтому проверяется ровно
это: отдаёт ли он то, что есть; не падает ли, когда прогонов ещё нет; и не пускает ли
наружу файлы, которых показывать нельзя.
"""

import json
import os
import socket
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from city import viz


class _Served(unittest.TestCase):
    """Дашборд на случайном порту над временным каталогом логов."""

    fixed = ""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.folder = self.dir.name
        self.viz = viz.Viz(self.folder, self.fixed)
        handler = type("Bound", (viz.Handler,), {"viz": self.viz})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.dir.cleanup()

    def get(self, path, timeout=5):
        with urllib.request.urlopen(f"{self.url}{path}", timeout=timeout) as resp:
            return resp.status, resp.read(), resp.headers

    def json(self, path):
        code, body, _ = self.get(path)
        return code, json.loads(body)

    def write_log(self, name="run-20260730-000000.jsonl", events=()):
        path = os.path.join(self.folder, name)
        with open(path, "w", encoding="utf-8") as fh:
            for e in events:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        return path

    def write_shot(self, name="m1-00003.3.jpg", body=b"\xff\xd8jpeg"):
        shots = os.path.join(self.folder, "shots")
        os.makedirs(shots, exist_ok=True)
        path = os.path.join(shots, name)
        with open(path, "wb") as fh:
            fh.write(body)
        return path


class TestPageAndField(_Served):
    def test_page_is_served_as_utf8_html(self):
        code, body, headers = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn("charset=utf-8", headers["Content-Type"])
        self.assertIn("ГОРОД ДРОНОВ", body.decode("utf-8"))

    def test_field_comes_from_the_config(self):
        code, field = self.json("/api/field")
        self.assertEqual(code, 200)
        self.assertEqual(field["size"], [6, 6])
        self.assertEqual(field["cell"], 0.8)
        self.assertIn(list(field["tower"]), [field["tower"]])
        self.assertTrue(field["buildings"])
        self.assertTrue(field["pads"])
        self.assertEqual(field["source"], "config.yaml")

    def test_unknown_path_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/nope")
        self.assertEqual(ctx.exception.code, 404)


class TestEvents(_Served):
    def test_no_runs_yet_is_waiting_not_an_error(self):
        """Дашборд поднимают ДО попытки — пустой каталог это ожидание, а не сбой."""
        code, data = self.json("/api/events?from=0")
        self.assertEqual(code, 200)
        self.assertTrue(data["waiting"])
        self.assertEqual(data["lines"], [])
        self.assertEqual(self.json("/api/runs")[1]["runs"], [])

    def test_lines_are_read_from_an_offset(self):
        self.write_log(events=[{"t": 0.0, "type": "RUN_START"}, {"t": 1.0, "type": "MOVE"}])
        code, first = self.json("/api/events?from=0")
        self.assertEqual(len(first["lines"]), 2)
        self.assertEqual(json.loads(first["lines"][0])["type"], "RUN_START")
        # Со смещения конца — ничего нового, и смещение не съехало.
        code, again = self.json(f"/api/events?from={first['next']}")
        self.assertEqual(again["lines"], [])
        self.assertEqual(again["next"], first["next"])

    def test_an_unfinished_line_is_not_served(self):
        """Файл, в который пишут, умеет отдать половину строки — её нельзя разбирать."""
        # Пишем байтами: в текстовом режиме Windows подставил бы \r\n, и тест мерил бы
        # перевод строки платформы, а не смещение, которое считает read_lines.
        whole = b'{"t":0.0,"type":"RUN_START"}\n'
        path = os.path.join(self.folder, "run-20260730-000000.jsonl")
        with open(path, "wb") as fh:
            fh.write(whole + b'{"t":1.0,"ty')
        code, data = self.json("/api/events?from=0")
        self.assertEqual(len(data["lines"]), 1)
        # Смещение встало ровно за переводом строки: недописанный хвост остался
        # непрочитанным и придёт целиком следующим запросом.
        self.assertEqual(data["next"], len(whole))

    def test_truncation_rewinds_instead_of_going_silent(self):
        path = self.write_log(events=[{"t": 0.0, "type": "RUN_START"}] * 5)
        _, before = self.json("/api/events?from=0")
        with open(path, "w", encoding="utf-8") as fh:  # усечение: новый прогон
            fh.write(json.dumps({"t": 0.0, "type": "RUN_START"}) + "\n")
        code, after = self.json(f"/api/events?from={before['next']}")
        self.assertEqual(after["from"], 0)
        self.assertEqual(len(after["lines"]), 1)

    def test_a_named_run_outside_the_folder_is_ignored(self):
        self.write_log()
        code, data = self.json("/api/events?run=" + urllib.parse.quote("../../secret.jsonl"))
        self.assertTrue(data.get("waiting"))

    def test_runs_are_listed_newest_first(self):
        self.write_log("run-20260101-000000.jsonl", [{"t": 0.0, "type": "DONE"}])
        self.write_log("run-20260730-000000.jsonl", [{"t": 0.0, "type": "DONE"}])
        _, data = self.json("/api/runs")
        self.assertEqual([r["run"] for r in data["runs"]],
                         ["run-20260730-000000.jsonl", "run-20260101-000000.jsonl"])


class TestShots(_Served):
    def test_a_frame_is_served_as_jpeg(self):
        self.write_shot()
        code, body, headers = self.get("/api/shot?path=logs/shots/m1-00003.3.jpg")
        self.assertEqual(code, 200)
        self.assertEqual(headers["Content-Type"], "image/jpeg")
        self.assertEqual(body, b"\xff\xd8jpeg")

    def test_the_marked_copy_wins(self):
        """Размеченный кадр и есть материал техзащиты: на нём видно, что нашло зрение."""
        self.write_shot("m1-00003.3.jpg", b"\xff\xd8plain")
        self.write_shot("m1-00003.3-mark.jpg", b"\xff\xd8marked")
        _, body, _ = self.get("/api/shot?path=m1-00003.3.jpg")
        self.assertEqual(body, b"\xff\xd8marked")

    def test_a_path_leading_outside_is_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/shot?path=" + urllib.parse.quote("../../../../Windows/win.ini"))
        self.assertEqual(ctx.exception.code, 403)

    def test_a_missing_frame_is_refused_not_a_crash(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/shot?path=" + urllib.parse.quote("нет-такого.jpg"))
        self.assertEqual(ctx.exception.code, 403)


class TestStream(_Served):
    def test_sse_sends_the_run_then_the_lines(self):
        self.write_log(events=[{"t": 0.0, "type": "RUN_START", "reason": "начало"}])
        # Сокет с таймаутом: поток бесконечный, и тест не должен на нём зависнуть.
        got = []
        resp = urllib.request.urlopen(f"{self.url}/api/stream", timeout=6)
        try:
            resp.fp.raw._sock.settimeout(6)
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if line.startswith("data: "):
                    got.append(json.loads(line[6:]))
                if len(got) >= 2:
                    break
        finally:
            resp.close()
        self.assertEqual(got[0]["kind"], "run")
        self.assertTrue(got[0]["run"].startswith("run-"))
        self.assertEqual(got[1]["type"], "RUN_START")

    def test_too_many_clients_get_a_refusal_not_a_hang(self):
        # Предел нужен потому, что на каждого клиента живёт свой поток: оставленная
        # на день страница плюс реконнекты иначе копили бы их без счёта.
        self.viz.clients = viz.MAX_CLIENTS
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/stream")
        self.assertEqual(ctx.exception.code, 503)


class TestReadLines(unittest.TestCase):
    """Чтение хвоста отдельно от сети: тут вся тонкая часть."""

    def test_a_missing_file_is_not_an_error(self):
        self.assertEqual(viz.read_lines(os.path.join(tempfile.gettempdir(), "нет"), 0), ([], 0))

    def test_blank_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "run-x.jsonl")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"a":1}\n\n{"b":2}\n')
            lines, nxt = viz.read_lines(path, 0)
            self.assertEqual(lines, ['{"a":1}', '{"b":2}'])
            self.assertEqual(nxt, os.path.getsize(path))

    def test_cyrillic_survives_the_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "run-x.jsonl")
            body = {"reason": "очаг найден по кадрам"}
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(body, ensure_ascii=False) + "\n")
            lines, _ = viz.read_lines(path, 0)
            self.assertEqual(json.loads(lines[0]), body)


class TestNewest(unittest.TestCase):
    def test_empty_folder_gives_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(viz.newest(d), "")

    def test_the_freshest_run_wins(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.path.join(d, "run-20260101-000000.jsonl")
            new = os.path.join(d, "run-20260730-000000.jsonl")
            for path in (old, new):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("{}\n")
            os.utime(old, (1, 1))
            self.assertEqual(viz.newest(d), new)


if __name__ == "__main__":
    unittest.main()
