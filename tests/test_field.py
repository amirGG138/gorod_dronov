import unittest

from city.field import Field


class TestGeometry(unittest.TestCase):
    """Сверка с реальной картой маркеров docs/field-map/map.txt."""

    def setUp(self):
        self.f = Field(size=(6, 6), cell=0.8)

    def test_pads_match_map_txt(self):
        # id 50 лежит в (-1.2, +1.2) и это клетка [1,4]; id 7 — (+1.2, -1.2) = [4,1]
        for cell, xy in (
            ((1, 4), (-1.2, 1.2)),
            ((4, 4), (1.2, 1.2)),
            ((1, 1), (-1.2, -1.2)),
            ((4, 1), (1.2, -1.2)),
        ):
            x, y = self.f.cell_to_m(cell)
            self.assertAlmostEqual(x, xy[0], places=6, msg=str(cell))
            self.assertAlmostEqual(y, xy[1], places=6, msg=str(cell))

    def test_roundtrip(self):
        for col in range(6):
            for row in range(6):
                x, y = self.f.cell_to_m((col, row))
                self.assertEqual(self.f.m_to_cell(x, y), (col, row))

    def test_field_fits_the_arena(self):
        # 6 клеток по 0,8 м = 4,8 м, поле центрировано относительно начала map
        x0, _ = self.f.cell_to_m((0, 0))
        x1, _ = self.f.cell_to_m((5, 0))
        self.assertAlmostEqual(x1 - x0, 4.0)  # между центрами крайних клеток

    def test_yaw_origin_shifts_everything(self):
        shifted = Field(size=(6, 6), cell=0.8, origin=(1.0, -0.5, 0.0))
        x, y = shifted.cell_to_m((1, 4))
        self.assertAlmostEqual(x, -0.2)
        self.assertAlmostEqual(y, 0.7)


class TestQuarters(unittest.TestCase):
    """Четверти поля: доля поля, за которую отвечает один дрон-монитор (этап 8)."""

    def setUp(self):
        self.f = Field(size=(6, 6), cell=0.8)

    def test_each_pad_sits_in_its_own_quarter(self):
        pads = [(1, 1), (4, 1), (1, 4), (4, 4)]
        quarters = {self.f.quadrant(pad) for pad in pads}
        self.assertEqual(len(quarters), 4, "площадки обязаны стоять в разных четвертях")

    def test_a_quarter_is_a_three_by_three_block(self):
        cells = self.f.quadrant_cells(self.f.quadrant((1, 1)))
        self.assertEqual(len(cells), 9)
        self.assertIn((0, 0), cells)
        self.assertIn((2, 2), cells)
        self.assertNotIn((3, 0), cells)

    def test_four_quarters_cover_the_field_without_overlap(self):
        seen = []
        for quad in {self.f.quadrant(c) for c in self.f.cells()}:
            seen.extend(self.f.quadrant_cells(quad))
        self.assertEqual(len(seen), 36)
        self.assertEqual(sorted(set(seen)), sorted(self.f.cells()))

    def test_the_pad_is_the_centre_of_its_quarter(self):
        """Дрон висит над серединой своей четверти — иначе край в кадр не влезет."""
        for pad in ((1, 1), (4, 1), (1, 4), (4, 4)):
            cells = self.f.quadrant_cells(self.f.quadrant(pad))
            cols = sorted({c[0] for c in cells})
            rows = sorted({c[1] for c in cells})
            self.assertEqual(pad[0], cols[len(cols) // 2])
            self.assertEqual(pad[1], rows[len(rows) // 2])

    def test_quarters_have_russian_names(self):
        self.assertEqual(self.f.quadrant_name(self.f.quadrant((1, 1))), "ближняя левая")
        self.assertEqual(self.f.quadrant_name(self.f.quadrant((4, 4))), "дальняя правая")


class TestRouting(unittest.TestCase):
    def setUp(self):
        # Копия боевой раскладки из city/config.yaml: четыре пада-крыши плюс три
        # дома без маркеров. Именно копия, а не чтение конфига: конфиг правят на
        # площадке, и тесты алгоритма от этого падать не должны.
        self.f = Field(
            size=(6, 6),
            cell=0.8,
            buildings=[(1, 1), (4, 1), (1, 4), (4, 4), (2, 1), (1, 2), (3, 4)],
        )

    def test_path_goes_around_buildings(self):
        path = self.f.astar((3, 3), (1, 3))
        self.assertEqual(path, [(3, 3), (2, 3), (1, 3)])
        for cell in path:
            self.assertTrue(self.f.is_road(cell))

    def test_no_path_into_building(self):
        self.assertIsNone(self.f.astar((3, 3), (1, 2)))

    def test_blocked_cell_is_avoided(self):
        path = self.f.astar((3, 3), (1, 3), blocked=[(2, 3)])
        self.assertIsNotNone(path)
        self.assertNotIn((2, 3), path)

    def test_no_path_when_walled_off(self):
        walled = Field(size=(6, 6), cell=0.8, buildings=[(0, 1), (1, 1), (1, 0)])
        self.assertIsNone(walled.astar((3, 3), (0, 0)))

    def test_approach_picks_cell_nearest_to_tower(self):
        # к горящему дому [2,1] подъезжаем со стороны башни [1,3], то есть
        # с [2,2] (два переезда), а не с [2,0] или [3,1] (по четыре)
        spot = self.f.approach((2, 1), prefer=(1, 3))
        self.assertEqual(spot, (2, 2))
        self.assertTrue(self.f.is_road(spot))

    def test_approach_none_when_surrounded(self):
        boxed = Field(
            size=(6, 6), cell=0.8, buildings=[(2, 2), (1, 2), (3, 2), (2, 1), (2, 3)]
        )
        self.assertIsNone(boxed.approach((2, 2), prefer=(0, 0)))

    def test_moves_counts_hops(self):
        self.assertEqual(Field.moves([(0, 0), (0, 1), (0, 2)]), 2)
        self.assertEqual(Field.moves([(0, 0)]), 0)
        self.assertEqual(Field.moves(None), 0)

    def test_astar_is_deterministic(self):
        first = self.f.astar((0, 0), (5, 5))
        for _ in range(5):
            self.assertEqual(self.f.astar((0, 0), (5, 5)), first)


if __name__ == "__main__":
    unittest.main()
