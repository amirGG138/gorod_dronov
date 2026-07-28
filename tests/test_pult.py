"""Облёт с пульта: куда именно летит дрон по команде «обзор 0.5».

Проверяем не сеть и не борт, а порядок точек и обязательный возврат на метку после
каждой стороны: ошибка здесь — это дрон, брошенный над чужой площадкой, и заметить
её на площадке будет уже нечем.
"""

import argparse
import math
import unittest

from city import pult
from city.robots.base import RobotError


class FakeDrone:
    """Борт, который всё принимает и всегда докладывает «долетел»."""

    def __init__(self, refuse_at=None):
        self.points = []
        self.shots = 0
        self.refuse_at = refuse_at  # номер вызова look, на котором отказать
        self.last_error = ""

    def status(self):
        return {"state": "hover", "busy": False, "alt": 1.5, "last_error": self.last_error}

    def look(self, xy, alt):
        self.points.append((round(xy[0], 3), round(xy[1], 3)))
        if self.refuse_at is not None and len(self.points) == self.refuse_at:
            self.last_error = "точка слишком далеко"
        return {}

    def shot(self):
        self.shots += 1
        return b"jpeg"


def make_args(**over):
    args = argparse.Namespace(alt=1.5, scan_radius=1.0, cell="1,1")
    for key, value in over.items():
        setattr(args, key, value)
    return args


class SweepTest(unittest.TestCase):
    def setUp(self):
        self.home = pult.pad_xy(make_args())
        # Кадр в этих проверках не нужен: он лезет в файловую систему и в зрение.
        self._take_shot = pult.take_shot
        pult.take_shot = lambda drone, counter, open_it=True: drone.shot()

    def tearDown(self):
        pult.take_shot = self._take_shot

    def test_vosem_storon_s_vozvratom(self):
        """Восемь сторон, между ними — метка; кадр снимается на каждой точке обзора."""
        drone = FakeDrone()
        pult.do_sweep(drone, 0.5, [0], make_args())
        self.assertEqual(len(drone.points), 16)
        self.assertEqual(drone.shots, 8)
        away = drone.points[0::2]
        back = drone.points[1::2]
        home = (round(self.home[0], 3), round(self.home[1], 3))
        self.assertEqual(back, [home] * 8)
        for point in away:
            distance = math.hypot(point[0] - self.home[0], point[1] - self.home[1])
            self.assertAlmostEqual(distance, 0.5, places=2)
        # Стороны разные, а не восемь раз одна и та же.
        self.assertEqual(len(set(away)), 8)

    def test_dalshe_predela_ne_letim(self):
        """За --scan-radius пульт не пускает сам, не дожидаясь восьми отказов борта."""
        drone = FakeDrone()
        pult.do_sweep(drone, 1.5, [0], make_args(scan_radius=1.0))
        self.assertEqual(drone.points, [])

    def test_otkaz_na_vozvrate_ostanavlivaet_oblyot(self):
        """Не вернулись на метку — облёт прекращается: дрон в неизвестном месте."""
        drone = FakeDrone(refuse_at=2)  # отказ на первом возврате
        pult.do_sweep(drone, 0.5, [0], make_args())
        self.assertEqual(len(drone.points), 2)

    def test_odna_tochka_po_dvum_chislam(self):
        """Старая форма «обзор 0.5 0.5» — одна точка и возврат."""
        drone = FakeDrone()
        pult.do_look(drone, "0.5 0.5", [0], make_args())
        home = (round(self.home[0], 3), round(self.home[1], 3))
        self.assertEqual(drone.points, [(home[0] + 0.5, home[1] + 0.5), home])
        self.assertEqual(drone.shots, 1)

    def test_ne_chislo(self):
        drone = FakeDrone()
        pult.do_look(drone, "далеко", [0], make_args())
        self.assertEqual(drone.points, [])


class HopTest(unittest.TestCase):
    def test_novaya_oshibka_borta_znachit_ne_poletel(self):
        drone = FakeDrone(refuse_at=1)
        self.assertFalse(pult.hop(drone, (0.0, 0.0), make_args(), "отлёт"))

    def test_staraya_oshibka_ne_meshaet(self):
        """Ошибка, которая была на борту ДО команды, не должна читаться как отказ."""
        drone = FakeDrone()
        drone.last_error = "давняя беда"
        self.assertTrue(pult.hop(drone, (0.0, 0.0), make_args(), "отлёт"))


if __name__ == "__main__":
    unittest.main()
