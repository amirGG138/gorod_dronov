"""Полная попытка по сети: диспетчер, ровер и дрон — разные программы.

Тест медленный (стоянки 3 и 5 секунд идут в реальном времени, их нельзя ускорить,
не соврав про регламент), поэтому по умолчанию пропускается:

    CITY_SLOW_TESTS=1 python3 -m unittest tests.test_http_e2e

Сценарий взят нарочно короткий: маршруты проверяются быстрыми тестами, а здесь
проверяется только то, что команды доходят по сети и факты подтверждаются опросом.
"""

import glob
import json
import os
import tempfile
import unittest

from city.robots.mock_server import serve
from city.run import main

SLOW = os.environ.get("CITY_SLOW_TESTS")


@unittest.skipUnless(SLOW, "медленный тест по сети: включается CITY_SLOW_TESTS=1")
class TestRunOverNetwork(unittest.TestCase):
    def setUp(self):
        self.rover_srv, _ = serve("rover", 0, (3, 3), move_time=0.05, quiet=True)
        self.drone_srv, _ = serve("drone", 0, (1, 1), name="m1", quiet=True)
        self.rover_url = f"http://127.0.0.1:{self.rover_srv.server_address[1]}"
        self.drone_url = f"http://127.0.0.1:{self.drone_srv.server_address[1]}"

    def tearDown(self):
        for srv in (self.rover_srv, self.drone_srv):
            srv.shutdown()
            srv.server_close()

    def test_full_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = main(
                [
                    "--net", "--drones", "--monitors", "m1",
                    "--rover-url", self.rover_url,
                    "--drone-url", self.drone_url,
                    "--fire-level", "1",
                    "--pickup", "2,3", "--dropoff", "3,4",
                    "--quiet", "--logs", tmp,
                ]
            )
            path = sorted(glob.glob(os.path.join(tmp, "run-*.jsonl")))[-1]
            with open(path, encoding="utf-8") as fh:
                events = [json.loads(line) for line in fh]
            shots = glob.glob(os.path.join(tmp, "shots", "*.jpg"))
            heads = []  # читаем до того, как временный каталог будет удалён
            for p in shots:
                with open(p, "rb") as fh:
                    heads.append(fh.read(2))

        self.assertEqual(code, 0)
        types = [e["type"] for e in events]
        self.assertIn("DONE", types)
        self.assertFalse([e for e in events if e["type"] == "ERROR"], "в логе есть ошибки")

        # борта опознаны и записаны в лог вместе с адресами
        robots = {e["name"]: e for e in events if e["type"] == "ROBOT"}
        self.assertEqual(set(robots), {"rover", "m1"})
        self.assertTrue(robots["rover"]["url"].startswith("http://"))

        # кадр реально долетел по сети и лёг на диск
        self.assertEqual(len(shots), 1)
        self.assertEqual(heads[0], b"\xff\xd8", "сохранён не JPEG")

        # стоянки засчитаны по факту опроса, а не по факту вызова sleep
        dwells = [e for e in events if e["type"] == "DWELL"]
        self.assertEqual(len(dwells), 2)
        for d in dwells:
            self.assertTrue(d["counted"], d)
            self.assertGreaterEqual(d["seconds"], 3.0)


if __name__ == "__main__":
    unittest.main()
