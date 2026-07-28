"""Полная попытка по сети: диспетчер, ровер и дрон — разные программы.

Тест медленный (стоянка у башни в 3 секунды идёт в реальном времени, её нельзя
ускорить, не соврав про регламент), поэтому по умолчанию пропускается:

    CITY_SLOW_TESTS=1 python3 -m unittest tests.test_http_e2e

Сценарий взят нарочно короткий: маршруты проверяются быстрыми тестами, а здесь
проверяется только то, что команды доходят по сети и факты подтверждаются опросом.
"""

import glob
import json
import os
import tempfile
import unittest

from city import config as config_mod
from city.robots.mock_server import serve
from city.run import main

SLOW = os.environ.get("CITY_SLOW_TESTS")
# Очаг стоит в углу того монитора, который участвует в прогоне: так по сети
# проверяется вся цепочка «отлетел -> снял -> вернулся -> узнал клетку».
SIM_FIRE = [0, 0]


def build_scene():
    """Нарисованный мир для мока дрона, или None если OpenCV на машине нет."""
    try:
        from city.robots.scene import SceneSpec

        cfg = config_mod.load()
        cfg.override("sim.fire_cell", SIM_FIRE)
        return SceneSpec.from_config(cfg)
    except Exception:  # noqa: BLE001
        return None


@unittest.skipUnless(SLOW, "медленный тест по сети: включается CITY_SLOW_TESTS=1")
class TestRunOverNetwork(unittest.TestCase):
    def setUp(self):
        self.scene = build_scene()
        self.rover_srv, _ = serve("rover", 0, (3, 3), move_time=0.05, quiet=True)
        self.drone_srv, _ = serve("drone", 0, (1, 1), name="m1", quiet=True, scene=self.scene)
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
                    "--quiet", "--logs", tmp,
                ]
            )
            path = sorted(glob.glob(os.path.join(tmp, "run-*.jsonl")))[-1]
            with open(path, encoding="utf-8") as fh:
                events = [json.loads(line) for line in fh]
            shots = sorted(glob.glob(os.path.join(tmp, "shots", "*.jpg")))
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

        # кадры реально долетели по сети и легли на диск
        self.assertGreaterEqual(len(shots), 1)
        for head in heads:
            self.assertEqual(head, b"\xff\xd8", "сохранён не JPEG")

        # разведка состоялась: каждый кадр разобран и записан отдельным событием
        scans = [e for e in events if e["type"] == "SCAN"]
        self.assertTrue(scans)
        if self.scene is not None:
            # облёт по сети: дрон отлетал от метки и возвращался, очаг найден
            self.assertGreater(len(scans), 1, "второй проход по сети не состоялся")
            spotted = next(e for e in events if e["type"] == "FIRE_SPOTTED")
            self.assertEqual(spotted["cell"], SIM_FIRE)

        # стоянки засчитаны по факту опроса, а не по факту вызова sleep
        dwells = [e for e in events if e["type"] == "DWELL"]
        self.assertEqual(len(dwells), 1)  # уровень пожара 1 = один забор воды
        for d in dwells:
            self.assertTrue(d["counted"], d)
            self.assertGreaterEqual(d["seconds"], 3.0)


if __name__ == "__main__":
    unittest.main()
