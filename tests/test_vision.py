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
        """С высоты видно несколько меток: привязка точная, ответ тот же."""
        spec = SceneSpec(self.field, self.pads, fire_cell=(1, 4))
        obs = self.see((0.0, 0.0), alt=3.0, spec=spec)
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
    def obs(drone, cell, area=1000.0):
        return vision.Observation(drone=drone, fire_cell=cell, area=area)

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


if __name__ == "__main__":
    unittest.main()
