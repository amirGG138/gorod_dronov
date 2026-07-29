"""Своя карта ровера: разворот лидара, сканматчинг, планировщик, файлы карт.

Ровера здесь нет — вместо HTTP подставляется заглушка, а сканы считаются от
синтетической комнаты. Проверяется то, что нельзя проверить глазами на площадке:
что точки лидара кладутся в карту в правильную сторону (лидар развёрнут на 180°,
ошибка знака даёт зеркальную карту), что сканматчинг вытягивает уехавшую
одометрию обратно, и что планировщик обходит стену, а не режет её насквозь.
"""

import importlib.util
import json
import math
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "rovMapControl", os.path.join(ROOT, "rovMapControl.py")
)
rmc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rmc)

rmc.say = lambda text: None  # строки инструмента в тесте — шум

ROOM = (-2.0, -1.5, 2.0, 1.5)  # комната, по стенам которой считаются лучи


def cast(pose, room=ROOM, beams=360, max_range=8.0):
    """Скан из позы внутри прямоугольной комнаты — точки в осях корпуса."""
    x, y, th = pose
    x0, y0, x1, y1 = room
    out = []
    for i in range(beams):
        a = -math.pi + 2 * math.pi * i / beams
        gx, gy = math.cos(th + a), math.sin(th + a)
        best = max_range
        for wall, g, p in ((x0, gx, x), (x1, gx, x), (y0, gy, y), (y1, gy, y)):
            if abs(g) < 1e-9:
                continue
            t = (wall - p) / g
            if 0 < t < best:
                hx, hy = x + gx * t, y + gy * t
                inside = (x0 - 1e-6 <= hx <= x1 + 1e-6 and y0 - 1e-6 <= hy <= y1 + 1e-6)
                if inside:
                    best = t
        if best < max_range:
            out.append((best * math.cos(a), best * math.sin(a)))
    return out


def grid_with_room(pose=(0.0, 0.0, 0.0), passes=3):
    g = rmc.Grid(res=0.05, size_m=12.0)
    for _ in range(passes):
        g.integrate(pose, cast(pose))
    return g


class TestLidarFrame(unittest.TestCase):
    """Точки лидара -> оси корпуса: поворот на 180° и сдвиг вперёд на 6,6 см."""

    def scan_from(self, points):
        rover = rmc.Rover("1.2.3.4", 8765, "/scan", min_range=0.05, max_range=8.0)
        saved = rmc.http_json
        rmc.http_json = lambda *a, **k: {"points": points, "age_sec": 0.05}
        try:
            return rover.scan()[0]
        finally:
            rmc.http_json = saved

    def test_razvorot_na_180(self):
        # Стена перед носом ровера видна лидару СЗАДИ: у неё x отрицательный.
        got = self.scan_from([[-2.0, 0.0]])
        self.assertEqual(len(got), 1)
        self.assertAlmostEqual(got[0][0], 2.0 + rmc.LIDAR_DX, places=6)
        self.assertAlmostEqual(got[0][1], 0.0, places=6)

    def test_bok_zerkalitsya(self):
        got = self.scan_from([[0.0, 1.0]])
        self.assertAlmostEqual(got[0][0], rmc.LIDAR_DX, places=6)
        self.assertAlmostEqual(got[0][1], -1.0, places=6)

    def test_svoy_korpus_otbrasyvaetsya(self):
        rover = rmc.Rover("1.2.3.4", 8765, "/scan", min_range=0.22, max_range=8.0)
        saved = rmc.http_json
        # Первая точка после переноса окажется в 6 см от центра — это сам ровер.
        rmc.http_json = lambda *a, **k: {"points": [[0.0, 0.0], [-3.0, 0.0]],
                                         "age_sec": 0.0}
        try:
            got = rover.scan()[0]
        finally:
            rmc.http_json = saved
        self.assertEqual(len(got), 1)


class TestGrid(unittest.TestCase):
    def test_steny_zanyaty_seredina_svobodna(self):
        g = grid_with_room()
        for x, y in ((0.0, 0.0), (1.0, 0.5), (-1.5, -1.0)):
            ix, iy = g.cell(x, y)
            self.assertLessEqual(g.odds[iy * g.w + ix], rmc.Grid.FREE_T,
                                 f"внутри комнаты ({x}, {y}) должно быть свободно")
        for x, y in ((2.0, 0.0), (-2.0, 0.5), (0.0, 1.5)):
            ix, iy = g.cell(x, y)
            self.assertGreaterEqual(g.odds[iy * g.w + ix], rmc.Grid.OCC_T,
                                    f"стена в ({x}, {y}) должна быть занята")

    def test_karta_ne_zerkalnaya(self):
        """Ровер у левой стены: занятой должна стать именно она, а не правая."""
        g = rmc.Grid(res=0.05, size_m=12.0)
        pose = (-1.5, 0.0, 0.0)
        for _ in range(2):   # клетка становится занятой со второго попадания
            g.integrate(pose, cast(pose))
        left = g.cell(-2.0, 0.0)
        right = g.cell(2.0, 0.0)
        self.assertGreaterEqual(g.odds[left[1] * g.w + left[0]], rmc.Grid.OCC_T)
        self.assertGreaterEqual(g.odds[right[1] * g.w + right[0]], rmc.Grid.OCC_T)
        # А вот точка за левой стеной остаётся неизвестной: сквозь стену не видно.
        behind = g.cell(-2.4, 0.0)
        self.assertEqual(g.odds[behind[1] * g.w + behind[0]], 0)

    def test_tochki_mimo_karty_schitayutsya(self):
        g = rmc.Grid(res=0.05, size_m=1.0)   # карта меньше комнаты
        g.integrate((0.0, 0.0, 0.0), cast((0.0, 0.0, 0.0)))
        self.assertGreater(g.lost, 0)


class TestMatch(unittest.TestCase):
    def test_uehavshuyu_odometriyu_vozvrashchaet(self):
        g = grid_with_room()
        true_pose = (0.35, -0.20, math.radians(12))
        pts = cast(true_pose)
        guess = (true_pose[0] - 0.12, true_pose[1] + 0.10,
                 true_pose[2] - math.radians(5))
        got = g.match(guess, pts[::2], max_shift=0.5, max_turn=math.radians(25))
        self.assertIsNotNone(got, "сканматчинг обязан сойтись по своей же карте")
        pose, quality = got
        self.assertLess(math.hypot(pose[0] - true_pose[0], pose[1] - true_pose[1]), 0.06)
        self.assertLess(abs(rmc.wrap(pose[2] - true_pose[2])), math.radians(3))
        self.assertGreater(quality, 25.0)

    def test_pustaya_karta_ne_matchitsya(self):
        g = rmc.Grid(res=0.05, size_m=12.0)
        self.assertIsNone(g.match((0.0, 0.0, 0.0), cast((0.0, 0.0, 0.0)),
                                  0.5, math.radians(25)))

    def test_slishkom_bolshaya_popravka_otvergaetsya(self):
        g = grid_with_room()
        pts = cast((1.0, 0.0, 0.0))
        # Подсказка уехала далеко: правильный ответ дальше предела — берём одометрию.
        got = g.match((0.0, 0.0, 0.0), pts[::2], max_shift=0.10,
                      max_turn=math.radians(5))
        self.assertIsNone(got)


class TestPredict(unittest.TestCase):
    """Шаг одометрии переносится в оси карты через разницу курсов, а не как есть."""

    def test_povorot_osey(self):
        class FakeArgs:
            period = 0.2
            start_mapping = False
            match_points = 160
            max_fix = 0.3
            max_fix_deg = 15.0
            min_quality = 25.0

        m = rmc.Mapper.__new__(rmc.Mapper)     # без потока и без ровера
        m.pose = (1.0, 2.0, math.radians(90))  # в карте ровер смотрит на север
        m.odom_ref = (0.0, 0.0, 0.0)           # а одометрия думает, что на восток
        m.args = FakeArgs()
        got = m.predict((1.0, 0.0, 0.0))       # метр «вперёд» по одометрии
        self.assertAlmostEqual(got[0], 1.0, places=6)
        self.assertAlmostEqual(got[1], 3.0, places=6)   # в карте это метр на север
        self.assertAlmostEqual(got[2], math.radians(90), places=6)


class TestPlanner(unittest.TestCase):
    def make_map(self):
        """Комната со стеной посередине и проходом у верхнего края."""
        g = rmc.Grid(res=0.05, size_m=12.0)
        for x in (-1.9 + 0.05 * i for i in range(int(3.8 / 0.05) + 1)):
            for y in (-1.4, 1.4):
                ix, iy = g.cell(x, y)
                g._occ(iy * g.w + ix, ix, iy)
        for y in (-1.4 + 0.05 * i for i in range(int(2.4 / 0.05))):   # стена с проходом
            ix, iy = g.cell(0.0, y)
            g._occ(iy * g.w + ix, ix, iy)
        for iy in range(g.h):                      # всё внутри считаем разведанным
            for ix in range(g.w):
                i = iy * g.w + ix
                if g.odds[i] == 0:
                    x, y = g.world(ix, iy)
                    if -1.9 < x < 1.9 and -1.4 < y < 1.4:
                        g.odds[i] = rmc.Grid.LO
        return g

    def test_obhodit_stenu_cherez_prohod(self):
        cm = rmc.Costmap(self.make_map(), robot_r=0.15, inflation=0.10)
        path, err = cm.plan((-1.2, 0.0), (1.2, 0.0))
        self.assertIsNotNone(path, err)
        self.assertGreater(rmc.path_len(path), 2.4,
                           "прямой путь режет стену — значит костмапа не работает")
        for i in range(len(path) - 1):
            self.assertTrue(cm.visible(path[i], path[i + 1]),
                            "звено пути проходит по запретной зоне")

    def test_cel_v_stene_ne_prinimaetsya(self):
        cm = rmc.Costmap(self.make_map(), robot_r=0.15, inflation=0.10)
        path, err = cm.plan((-1.2, 0.0), (0.0, 5.0))   # снаружи, в неизвестном
        self.assertIsNone(path)
        self.assertTrue(err)

    def test_neizvestnoe_neprohodimo_po_umolchaniyu(self):
        g = grid_with_room()
        cm = rmc.Costmap(g, robot_r=0.15, inflation=0.10)
        ix, iy = cm.cell(3.0, 0.0)      # за стеной комнаты — там ровер не был
        self.assertFalse(cm.free(ix, iy))
        open_cm = rmc.Costmap(g, robot_r=0.15, inflation=0.10, allow_unknown=True)
        self.assertTrue(open_cm.free(ix, iy))


class TestBumper(unittest.TestCase):
    def test_smotrit_kuda_edem_a_ne_vpered(self):
        pts = [(0.0, 0.30)]      # препятствие слева от ровера
        self.assertFalse(rmc.blocked_ahead(pts, 0.15, 0.0, 0.35, 0.25))
        self.assertTrue(rmc.blocked_ahead(pts, 0.0, 0.15, 0.35, 0.25))

    def test_stoyashchiy_rover_ne_tormozit(self):
        self.assertFalse(rmc.blocked_ahead([(0.1, 0.0)], 0.0, 0.0, 0.35, 0.25))


class TestFiles(unittest.TestCase):
    def test_sohranit_i_zagruzit(self):
        g = grid_with_room()
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "комната")
            files = rmc.save_map(g, base, pose=(0.1, 0.2, 0.3))
            for path in files:
                self.assertTrue(os.path.getsize(path) > 0, path)
            with open(base + ".json", encoding="utf-8") as f:
                data = json.load(f)
            back = rmc.Grid.from_json(data)
            self.assertEqual((back.w, back.h, back.res), (g.w, g.h, g.res))
            self.assertEqual(back.hits, g.hits)
            self.assertEqual(bytes(back.odds), bytes(g.odds))
            self.assertGreater(max(back.lf), 0, "поле правдоподобия должно пересобраться")
            self.assertEqual(data["pose"], [0.1, 0.2, 0.3])

            with open(base + ".png", "rb") as f:
                head = f.read(8)
            self.assertEqual(head, b"\x89PNG\r\n\x1a\n")
            with open(base + ".yaml", encoding="utf-8") as f:
                yaml = f.read()
            self.assertIn("resolution: 0.050", yaml)
            self.assertIn("комната.pgm", yaml)

    def test_zagruzhennaya_karta_matchitsya(self):
        """Карта после круга «сохранил — загрузил» годится для позиционирования."""
        g = grid_with_room()
        back = rmc.Grid.from_json(g.to_json())
        true_pose = (0.3, 0.1, 0.0)
        got = back.match((0.4, 0.0, math.radians(4)), cast(true_pose)[::2],
                         0.5, math.radians(25))
        self.assertIsNotNone(got)
        self.assertLess(math.hypot(got[0][0] - true_pose[0], got[0][1] - true_pose[1]), 0.06)


class TestAscii(unittest.TestCase):
    def test_risuet_i_ne_padaet(self):
        g = grid_with_room()
        art = g.ascii_art(pose=(0.0, 0.0, 0.0), goal=(1.0, 1.0))
        self.assertIn("#", art)
        self.assertIn("R", art)
        self.assertIn("G", art)
        self.assertEqual(rmc.Grid(res=0.05, size_m=2.0).ascii_art(), "карта пустая")


if __name__ == "__main__":
    unittest.main()
