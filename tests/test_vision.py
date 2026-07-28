"""Зрение проверяется на нарисованной сцене: там известен правильный ответ.

Настоящую проверку даёт только кадр с борта, но эти тесты ловят то, что на площадке
ловить некогда: перепутанные оси, потерянный масштаб, «нашёл очаг там, где его нет».
"""

import os
import unittest

from city import config as config_mod
from city import vision
from city.field import Field

try:
    from city.robots.scene import SceneSpec

    NO_CV2 = vision.CV2_ERROR
except Exception as exc:  # noqa: BLE001
    SceneSpec = None
    NO_CV2 = str(exc)


@unittest.skipIf(NO_CV2, f"нет OpenCV: {NO_CV2}")
class TestOneFrame(unittest.TestCase):
    """Один кадр: метка -> привязка -> клетка очага."""

    def setUp(self):
        self.cfg = config_mod.load()
        self.field = Field.from_config(self.cfg)
        self.pads = vision.pads_from_config(self.cfg)
        self.settings = vision.settings(self.cfg)
        self.spec = SceneSpec.from_config(self.cfg)

    def see(self, xy, alt=1.5, pose=None, spec=None):
        spec = spec or self.spec
        frame = vision.decode(spec.render(xy, alt))
        return vision.look(
            frame, self.field, self.pads, drone="t", pose=pose, alt=alt, **self.settings
        )

    def test_marker_over_pad_is_recognised(self):
        for mid, cell in self.pads.items():
            obs = self.see(self.field.cell_to_m(cell))
            self.assertIn(mid, obs.markers_seen, f"метка {mid} над клеткой {cell} не нашлась")

    def test_fire_cell_from_marker_anchor(self):
        """Метка в кадре -> клетка очага считается по ней, без всякой телеметрии."""
        spec = SceneSpec(self.field, self.pads, fire_cell=(4, 2))
        obs = self.see((1.2, -0.8), spec=spec)
        self.assertEqual(obs.anchor, "marker")
        self.assertEqual(obs.fire_cell, (4, 2))

    def test_fire_cell_from_pose_anchor(self):
        """Метки в кадре нет — привязка по точке, куда дрон летел."""
        spec = SceneSpec(self.field, self.pads, fire_cell=(4, 2))
        obs = self.see((1.2, -0.55), pose=(1.2, -0.55), spec=spec)
        self.assertEqual(obs.anchor, "pose")
        self.assertEqual(obs.fire_cell, (4, 2))

    def test_two_markers_give_the_same_answer(self):
        """С высоты видно несколько меток: привязка точная, ответ тот же.

        Порог площади здесь занижен намеренно. Две метки помещаются в кадр только
        с 2,8 м и выше, а жетон 4,5 см с такой высоты даёт около 110 пикселей —
        рабочий порог 150 его уже отсекает. Это не натяжка, а измеренное свойство
        поля: ровно поэтому мониторы снимают с 1,5 м и облетают свой угол. Здесь
        проверяется геометрия привязки по двум меткам, а не дальность зрения.
        """
        settings = dict(self.settings, min_area=60.0)
        spec = SceneSpec(self.field, self.pads, fire_cell=(1, 4))
        frame = vision.decode(spec.render((0.0, 0.0), 3.0))
        obs = vision.look(frame, self.field, self.pads, drone="t", alt=3.0, **settings)
        self.assertEqual(obs.anchor, "markers")
        self.assertEqual(obs.fire_cell, (1, 4))

    def test_every_cell_of_the_field_is_read_back(self):
        """Очаг в любой клетке узнаётся как та же клетка: оси и знаки не перепутаны."""
        for col in range(self.field.cols):
            for row in range(self.field.rows):
                spec = SceneSpec(self.field, self.pads, fire_cell=(col, row))
                xy = self.field.cell_to_m((col, row))
                obs = self.see(xy, pose=xy, spec=spec)
                self.assertEqual(obs.fire_cell, (col, row), f"клетка {(col, row)}")

    def test_empty_field_finds_nothing(self):
        """Нет очага — нет и находки. Выдуманная клетка хуже отсутствия ответа."""
        spec = SceneSpec(self.field, self.pads, fire_cell=None)
        obs = self.see(self.field.cell_to_m((1, 1)), spec=spec)
        self.assertIsNone(obs.fire_cell)
        self.assertTrue(obs.note)

    def test_without_anchor_there_is_no_guess(self):
        """Ни метки, ни известной точки съёмки — честное «не знаю»."""
        spec = SceneSpec(self.field, {}, fire_cell=(4, 2))
        obs = self.see((1.2, -0.55), pose=None, spec=spec)
        self.assertIsNone(obs.fire_cell)
        self.assertEqual(obs.anchor, "none")

    def fire(self, frame):
        return vision.find_fire(
            frame,
            self.settings["hsv_ranges"],
            self.settings["min_area"],
            self.settings["max_share"],
        )

    def test_pink_district_is_not_a_fire(self):
        """Красноватый район поля занимает пол-кадра и всё равно не очаг.

        Отличает его насыщенность: у района она низкая (замер по фотографиям поля
        S 15..43), у жетона высокая. Это главная ловушка поиска огня по цвету.
        """
        import numpy as np

        from city.robots.scene import DISTRICT_BGR

        frame = np.zeros((480, 640, 3), np.uint8)
        frame[:, :] = DISTRICT_BGR["red"]
        self.assertIsNone(self.fire(frame))

    def test_fire_colour_filling_the_frame_is_not_a_fire(self):
        """Даже правильный цвет во весь кадр — не «огонёк»: он размером с коробок."""
        import numpy as np

        from city.robots.scene import FIRE_BGR

        frame = np.zeros((480, 640, 3), np.uint8)
        frame[:, :] = FIRE_BGR
        self.assertIsNone(self.fire(frame))

    def test_fire_is_found_from_the_working_altitude(self):
        """С рабочей высоты жетон в 4,5 см ещё виден. Выше 3 м — уже нет."""
        spec = SceneSpec(self.field, self.pads, fire_cell=(4, 2))
        xy = self.field.cell_to_m((4, 2))
        for alt, want in ((1.0, True), (1.5, True), (2.0, True), (3.5, False)):
            obs = self.see(xy, alt=alt, pose=xy, spec=spec)
            self.assertEqual(obs.found, want, f"высота {alt} м")


@unittest.skipIf(NO_CV2, f"нет OpenCV: {NO_CV2}")
class TestCountingTokens(unittest.TestCase):
    """Степень пожара = сколько жетонов лежит рядом. Значит их надо сосчитать."""

    def setUp(self):
        self.cfg = config_mod.load()
        self.field = Field.from_config(self.cfg)
        self.pads = vision.pads_from_config(self.cfg)
        self.settings = vision.settings(self.cfg)

    def see(self, spec, xy, alt=1.5):
        frame = vision.decode(spec.render(xy, alt))
        return vision.look(
            frame, self.field, self.pads, drone="t", pose=xy, alt=alt, **self.settings
        )

    def test_number_of_tokens_becomes_the_level(self):
        """Один огонёк — уровень 1, три рядом — уровень 3. Это вся суть счёта."""
        for level in (1, 2, 3):
            spec = SceneSpec(self.field, self.pads, fire_cell=(2, 2), fire_level=level)
            obs = self.see(spec, self.field.cell_to_m((2, 2)))
            self.assertEqual(obs.fire_cell, (2, 2), f"{level} огоньков: клетка")
            self.assertEqual(obs.fire_count, level, f"{level} огоньков: счёт")
            # Жетоны кладут с зазором, поэтому нормальный путь — счёт пятен, а не
            # деление площади: делёж включается только на слипшихся.
            self.assertEqual(obs.count_source, "blobs", f"{level} огоньков: чем посчитано")

    def test_group_split_by_a_cell_border_is_still_one_fire(self):
        """Граница клетки прошла между жетонами — это по-прежнему один пожар.

        Ровно поэтому кучка собирается по расстоянию на поле, а не по клеткам:
        иначе три огонька на границе дали бы два пожара уровня 2 и 1.
        """
        border = (-0.05, -0.4)  # между клетками (2,2) и (3,2), граница по x = 0
        spec = SceneSpec(
            self.field, self.pads, fire_cell=(2, 2), fire_level=2, fire_xy=border
        )
        obs = self.see(spec, border)
        self.assertEqual(obs.fire_count, 2)
        self.assertEqual(obs.fire_cell, (2, 2))
        self.assertLess(obs.spread_m, 0.4)

    def test_the_whole_group_is_seen_from_the_working_altitude(self):
        """Три жетона попадают в один кадр с рабочей высоты — иначе счёт бесполезен."""
        spec = SceneSpec(self.field, self.pads, fire_cell=(4, 2), fire_level=3)
        obs = self.see(spec, self.field.cell_to_m((4, 2)), alt=1.5)
        self.assertEqual(obs.fire_count, 3)
        self.assertFalse(obs.clipped, "кучка не должна упираться в край кадра")


class TestGrouping(unittest.TestCase):
    """Группировка и счёт — без OpenCV: это чистая арифметика над пятнами."""

    @staticmethod
    def spot(x, y, area=500.0):
        return vision.Spot(u=0.0, v=0.0, x=x, y=y, area=area, share=0.0)

    def test_close_spots_are_one_fire(self):
        groups = vision.clusters([self.spot(0.0, 0.0), self.spot(0.2, 0.0)], 0.4)
        self.assertEqual(len(groups), 1)

    def test_spots_in_different_cells_are_different_fires(self):
        groups = vision.clusters([self.spot(0.0, 0.0), self.spot(0.9, 0.0)], 0.4)
        self.assertEqual(len(groups), 2)

    def test_a_chain_holds_together(self):
        """Три жетона в ряд — одна кучка, хотя крайние дальше порога друг от друга."""
        spots = [self.spot(0.0, 0.0), self.spot(0.3, 0.0), self.spot(0.6, 0.0)]
        self.assertEqual(len(vision.clusters(spots, 0.4)), 1)

    def test_separate_tokens_are_counted_one_by_one(self):
        spots = [self.spot(0.0, 0.0), self.spot(0.1, 0.0), self.spot(0.2, 0.0)]
        self.assertEqual(vision.count_tokens(spots, unit_px=500.0), (3, "blobs"))

    def test_a_single_token_is_not_split_by_noise(self):
        """Пятно чуть крупнее расчётного — всё равно один жетон, а не два."""
        self.assertEqual(vision.count_tokens([self.spot(0, 0, 600.0)], 500.0), (1, "blobs"))

    def test_stuck_together_tokens_are_counted_by_area(self):
        """Жетоны слиплись в одно пятно: контуров нет, зато есть кратность размера."""
        self.assertEqual(vision.count_tokens([self.spot(0, 0, 1000.0)], 500.0), (2, "area"))

    def test_the_smallest_spot_of_the_group_is_the_yardstick(self):
        """Мерка берётся из самой кучки: свой жетон в кадре честнее расчёта по высоте."""
        spots = [self.spot(0.0, 0.0, 400.0), self.spot(0.2, 0.0, 800.0)]
        self.assertEqual(vision.count_tokens(spots, unit_px=99999.0), (3, "mixed"))

    def test_token_size_follows_the_scale(self):
        """Чем ниже дрон, тем крупнее жетон в пикселях — мерка обязана это учитывать."""
        self.assertGreater(vision.token_px(0.0015), vision.token_px(0.003))
        self.assertEqual(vision.token_px(0.0), 0.0)


PHOTOS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "photo_fire")
# Где на самом деле лежит жетон на каждой фотографии (пиксели оригинала, сверено
# глазами). Это единственный способ проверить, что найден именно огонь, а не нога
# человека в кадре: у кожи тон 10..15, и первый вариант порогов ловил именно её.
PHOTO_FIRE = {
    "photo_2026-07-28 13.58.06.jpeg": (915, 1372),
    "photo_2026-07-28 13.58.08.jpeg": (804, 1310),
    "photo_2026-07-28 13.58.09.jpeg": (814, 1240),
    "photo_2026-07-28 13.58.10.jpeg": (854, 1304),
    "photo_2026-07-28 13.58.11.jpeg": (940, 1440),
    "photo_2026-07-28 13.58.12.jpeg": (821, 1363),
    "photo_2026-07-28 13.58.13.jpeg": (1405, 1118),
    "photo_2026-07-28 13.58.14.jpeg": (1615, 1103),
}


@unittest.skipIf(NO_CV2, f"нет OpenCV: {NO_CV2}")
@unittest.skipUnless(os.path.isdir(PHOTOS), "нет папки photo_fire со снимками настоящего поля")
class TestRealPhotos(unittest.TestCase):
    """Пороги цвета проверяются на фотографиях настоящего жетона, а не на рисунке.

    Рисованная сцена доказывает только математику. Что «огонёк» вообще отличим от
    поля, кожи и розового района, доказывают эти восемь снимков.
    """

    def setUp(self):
        import cv2

        self.cv2 = cv2
        self.settings = vision.settings(config_mod.load())

    def find(self, frame):
        return vision.find_fire(
            frame,
            self.settings["hsv_ranges"],
            self.settings["min_area"],
            self.settings["max_share"],
        )

    def test_fire_found_on_every_photo(self):
        for name, (x, y) in PHOTO_FIRE.items():
            path = os.path.join(PHOTOS, name)
            if not os.path.exists(path):
                continue
            frame = self.cv2.imread(path)
            blob = self.find(frame)
            self.assertIsNotNone(blob, f"{name}: жетон не найден")
            self.assertLess(abs(blob.u - x), 150, f"{name}: найдено не там (u)")
            self.assertLess(abs(blob.v - y), 150, f"{name}: найдено не там (v)")

    def test_one_token_gives_exactly_one_spot(self):
        """На снимках лежит один жетон — и пятно должно быть одно.

        Это обратная сторона счёта огоньков: распадись жетон на два пятна, уровень
        пожара удвоился бы, и ровер поехал бы за водой лишний раз. Проверяется в
        бортовом масштабе, потому что именно его увидит дрон.
        """
        for name in PHOTO_FIRE:
            path = os.path.join(PHOTOS, name)
            if not os.path.exists(path):
                continue
            frame = self.cv2.imread(path)
            height, width = frame.shape[:2]
            small = self.cv2.resize(
                frame, (int(width * 0.25), int(height * 0.25)), interpolation=self.cv2.INTER_AREA
            )
            spots = vision.find_fires(
                small,
                self.settings["hsv_ranges"],
                self.settings["min_area"],
                self.settings["max_share"],
            )
            self.assertEqual(len(spots), 1, f"{name}: пятен {len(spots)}, а жетон один")

    def test_fire_survives_the_drone_camera_scale(self):
        """Кадр уменьшен до бортового размера — жетон всё ещё находится.

        Снимки сделаны с рук почти вплотную, а дрон висит в полутора метрах. Без
        этой проверки пороги были бы подобраны под масштаб, которого в полёте нет.
        """
        for name, (x, y) in PHOTO_FIRE.items():
            path = os.path.join(PHOTOS, name)
            if not os.path.exists(path):
                continue
            frame = self.cv2.imread(path)
            height, width = frame.shape[:2]
            k = 0.25  # жетон становится размером примерно как с высоты 1,5 м
            small = self.cv2.resize(
                frame, (int(width * k), int(height * k)), interpolation=self.cv2.INTER_AREA
            )
            blob = self.find(small)
            self.assertIsNotNone(blob, f"{name}: в уменьшенном кадре жетон потерян")
            self.assertLess(abs(blob.u - x * k), 60, f"{name}: найдено не там (u)")
            self.assertLess(abs(blob.v - y * k), 60, f"{name}: найдено не там (v)")


class TestMerge(unittest.TestCase):
    """Сведение наблюдений: голосование, а не «кто последний сказал»."""

    @staticmethod
    def obs(drone, cell, area=1000.0, count=1, clipped=False):
        return vision.Observation(
            drone=drone, fire_cell=cell, area=area, fire_count=count, clipped=clipped
        )

    def test_majority_wins(self):
        scene = vision.merge([
            self.obs("m1", (4, 2)), self.obs("m2", (4, 2)), self.obs("m3", (1, 1)),
        ])
        self.assertEqual(scene.fire_cell, (4, 2))
        self.assertEqual((scene.votes, scene.total), (2, 3))
        self.assertEqual(scene.drones, ["m1", "m2"])

    def test_tie_goes_to_the_bigger_blob(self):
        """Голоса поровну — верим кадру, где пятно крупнее: он снят ближе."""
        scene = vision.merge([self.obs("m1", (4, 2), 500.0), self.obs("m2", (1, 1), 5000.0)])
        self.assertEqual(scene.fire_cell, (1, 1))

    def test_nothing_seen_is_not_a_find(self):
        scene = vision.merge([vision.Observation(drone="m1"), vision.Observation(drone="m2")])
        self.assertFalse(scene.found)
        self.assertEqual(scene.total, 0)
        self.assertIsNone(scene.level)

    def test_level_is_the_number_most_frames_agree_on(self):
        scene = vision.merge([
            self.obs("m1", (4, 2), count=3),
            self.obs("m2", (4, 2), count=3),
            self.obs("m3", (4, 2), count=2),
        ])
        self.assertEqual(scene.level, 3)
        self.assertEqual(scene.level_votes, {"2": 1, "3": 2})

    def test_a_tie_goes_to_the_bigger_number(self):
        """Поровну — верим большему: обрезанный кадр занижает, а не завышает счёт."""
        scene = vision.merge([self.obs("m1", (4, 2), count=2), self.obs("m2", (4, 2), count=3)])
        self.assertEqual(scene.level, 3)

    def test_a_whole_group_beats_one_cut_by_the_frame_edge(self):
        """Кадр, где кучка целиком, важнее двух кадров, где она у края."""
        scene = vision.merge([
            self.obs("m1", (4, 2), count=1, clipped=True),
            self.obs("m2", (4, 2), count=1, clipped=True),
            self.obs("m3", (4, 2), count=3),
        ])
        self.assertEqual(scene.level, 3)

    def test_only_clipped_frames_are_used_but_flagged(self):
        scene = vision.merge([self.obs("m1", (4, 2), count=2, clipped=True)])
        self.assertEqual(scene.level, 2)
        self.assertIn("занижен", scene.count_note)

    def test_impossible_count_falls_back_to_the_config(self):
        """Насчитали больше, чем бывает на поле, — это ошибка, а не пожар уровня 7."""
        scene = vision.merge([self.obs("m1", (4, 2), count=7)])
        self.assertTrue(scene.found)
        self.assertIsNone(scene.level)
        self.assertIn("ошибка распознавания", scene.count_note)

    def test_the_level_is_counted_only_on_the_winning_cell(self):
        """Кадр, показавший другую клетку, в счёте уровня не участвует."""
        scene = vision.merge([
            self.obs("m1", (4, 2), count=1),
            self.obs("m2", (4, 2), count=1),
            self.obs("m3", (1, 1), count=3),
        ])
        self.assertEqual(scene.fire_cell, (4, 2))
        self.assertEqual(scene.level, 1)


if __name__ == "__main__":
    unittest.main()
