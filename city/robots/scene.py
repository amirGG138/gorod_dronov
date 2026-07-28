"""Синтетический кадр «вид сверху»: то, что увидела бы камера дрона.

Нужен дважды. Первое: прогон `python3 -m city.run --sim --drones` должен
показывать работу зрения, а не его молчание, — заглушкой 16x16 пикселей нельзя
найти ни метку, ни очаг. Второе: на нарисованной сцене известен правильный ответ,
поэтому на ней проверяется разбор кадра (tests/test_vision.py).

Это НЕ симулятор камеры: нет ни перспективы, ни наклона, ни шума. Ровно столько,
чтобы через всю цепочку «кадр -> метка -> клетка очага» прошли настоящие данные.
Настоящую проверку даёт только кадр с борта.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from ..field import Cell, Field, as_cell
from ..vision import MARKER_M, Anchor, anchor_from_pose

try:
    import cv2
    import numpy as np
except Exception:  # noqa: BLE001 — без OpenCV просто не рисуем
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]

FLOOR = (225, 222, 218)  # светлое поле с голубизной, как на настоящем полотне
# «Огонёк» — тёмно-красный жетон, а не оранжевый: цвет и размер взяты с фотографий
# настоящего поля (photo_fire/, 2026-07-28). Рисовать его оранжевым было бы удобно и
# бесполезно: проверка шла бы против цвета, которого на поле нет.
FIRE_BGR = (40, 30, 190)
FIRE_M = 0.045  # длинная сторона жетона на поле, м — по фотографиям
# Жетон — язычок пламени: вытянутый и заполняющий свой квадрат примерно наполовину
# (замер по photo_fire/: длинная сторона к короткой 1,4, площадь к квадрату длинной
# 0,45..0,49). Рисуем эллипсом с теми же пропорциями, а не кругом: круг заполняет
# 0,79, и счёт слипшихся жетонов по площади проверялся бы против формы, которой на
# поле нет.
FIRE_ASPECT = 1.4
FIRE_GAP_M = 0.12  # на сколько расходятся жетоны одной кучки от её центра
# Цветные районы по углам: бледные, но красноватый район — главная ловушка для
# поиска огня по цвету, поэтому в нарисованном мире он есть.
DISTRICT_BGR = {
    "red": (200, 200, 240),
    "yellow": (190, 235, 245),
    "blue": (240, 220, 200),
    "green": (200, 235, 205),
}
DISTRICT_CELLS = 3  # район занимает угловой квадрат 3x3 клетки
SIZE = (960, 1280)  # высота, ширина — как у камеры борта (сверено 2026-07-27)


@dataclass
class SceneSpec:
    """Что стоит на поле в этом прогоне. Диспетчер этого не знает — он это ищет."""

    field: Field
    pads: dict[int, Cell]
    fire_cell: Cell | None = None
    # Сколько жетонов лежит в клетке очага: на поле это и есть степень пожара, и
    # диспетчер обязан прочитать её с картинки. Рисовать всегда один жетон значило бы
    # проверять счёт против сцены, где считать нечего.
    fire_level: int = 1
    # Куда положить кучку в метрах, минуя центр клетки. Нужно, чтобы проверить
    # кучку, разрезанную границей клетки: на поле жетоны кладут не по линейке.
    fire_xy: tuple[float, float] | None = None
    fov_deg: float = 65.0
    size: tuple[int, int] = SIZE
    districts: dict[str, Cell] = None  # type: ignore[assignment]

    @classmethod
    def from_config(cls, cfg) -> "SceneSpec":
        from ..vision import pads_from_config

        # sim.fire_cell позволяет поставить очаг НЕ туда, где он записан в сценарии:
        # так проверяется, что диспетчер верит картинке, а не файлу настроек.
        # Значение «none» — поле без очага: проверка честного отказа разведки.
        fire = cfg.get("sim.fire_cell", None) or cfg.get("scenario.fire.cell", None)
        if isinstance(fire, str):
            fire = None
        # sim.fire_count — то же самое для числа жетонов: позволяет положить на
        # нарисованное поле не столько огоньков, сколько записано в сценарии, и
        # убедиться, что уровень тоже берётся с картинки, а не из файла.
        level = cfg.get("sim.fire_count", None)
        if level is None:
            level = cfg.get("scenario.fire.level", 1)
        raw = cfg.get("districts", {})
        districts = {
            name: as_cell(cell) for name, cell in (raw.items() if hasattr(raw, "items") else ())
        }
        return cls(
            field=Field.from_config(cfg),
            pads=pads_from_config(cfg),
            fire_cell=as_cell(fire) if fire else None,
            fire_level=max(1, int(level)),
            fov_deg=float(cfg.get("camera.fov_deg", 65.0)),
            districts=districts,
        )

    def render(self, xy: Sequence[float], alt: float) -> bytes | None:
        """JPEG с точки (x, y) метров и высоты alt, или None если рисовать нечем."""
        if cv2 is None:
            return None
        frame = np.full((self.size[0], self.size[1], 3), FLOOR, np.uint8)
        anchor = anchor_from_pose(xy, alt, self.size, self.fov_deg)
        for name, cell in (self.districts or {}).items():
            _draw_district(frame, anchor, self.field, name, cell)
        for mid, cell in self.pads.items():
            _draw_marker(frame, anchor, mid, self.field.cell_to_m(cell))
        if self.fire_cell is not None:
            centre = self.fire_xy or self.field.cell_to_m(self.fire_cell)
            for xy in fire_spots(centre, self.fire_level):
                _draw_fire(frame, anchor, xy)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return buf.tobytes() if ok else None


def _visible(frame, u: float, v: float, pad: float) -> bool:
    height, width = frame.shape[:2]
    return -pad <= u <= width + pad and -pad <= v <= height + pad


def _draw_marker(frame, anchor: Anchor, mid: int, xy: tuple[float, float]) -> None:
    """Метка площадки: сама картинка маркера плюс белое поле вокруг.

    Метка рисуется без поворота: верхнее ребро идёт вправо по кадру. Это ровно то
    соглашение, которое в config.yaml названо vision.marker_edge_deg = 0.
    """
    side = int(round(MARKER_M / anchor.mpp))
    if side < 12:
        return  # с такой высоты метку всё равно не опознать
    u, v = anchor.to_pixel(*xy)
    if not _visible(frame, u, v, side):
        return
    get_dict = getattr(cv2.aruco, "getPredefinedDictionary", None) or cv2.aruco.Dictionary_get
    dictionary = get_dict(cv2.aruco.DICT_4X4_1000)
    draw = getattr(cv2.aruco, "generateImageMarker", None) or cv2.aruco.drawMarker
    tile = draw(dictionary, int(mid), side)
    tile = cv2.cvtColor(tile, cv2.COLOR_GRAY2BGR)

    quiet = max(4, side // 6)  # белое поле: без него детектор метку не берёт
    u0, v0 = int(round(u - side / 2)), int(round(v - side / 2))
    height, width = frame.shape[:2]
    bx0, by0 = max(0, u0 - quiet), max(0, v0 - quiet)
    bx1, by1 = min(width, u0 + side + quiet), min(height, v0 + side + quiet)
    if bx1 <= bx0 or by1 <= by0:
        return
    frame[by0:by1, bx0:bx1] = (255, 255, 255)

    # Обрезка по краю кадра: метка может торчать наружу, это нормально.
    sx0, sy0 = max(0, -u0), max(0, -v0)
    tx0, ty0 = max(0, u0), max(0, v0)
    tx1, ty1 = min(width, u0 + side), min(height, v0 + side)
    if tx1 <= tx0 or ty1 <= ty0:
        return
    frame[ty0:ty1, tx0:tx1] = tile[sy0:sy0 + (ty1 - ty0), sx0:sx0 + (tx1 - tx0)]


def _draw_district(frame, anchor: Anchor, field: Field, name: str, cell: Cell) -> None:
    """Цветной район: угловой квадрат 3x3 клетки бледного цвета.

    Он здесь не для красоты. Красноватый район — единственное крупное пятно на поле,
    близкое к цвету огня, и проверять поиск очага без него значит проверять его в
    условиях, которых на площадке не будет.
    """
    half = DISTRICT_CELLS * field.cell / 2.0
    # Угол района — тот, в котором лежит его клетка; двигаем центр внутрь поля.
    cx, cy = field.cell_to_m(cell)
    sx = 1.0 if cx <= field.x0 else -1.0
    sy = 1.0 if cy <= field.y0 else -1.0
    centre = (cx + sx * (half - field.cell / 2.0), cy + sy * (half - field.cell / 2.0))
    corners = [
        anchor.to_pixel(centre[0] + dx * half, centre[1] + dy * half)
        for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    ]
    pts = np.array([[int(round(u)), int(round(v))] for u, v in corners], np.int32)
    cv2.fillPoly(frame, [pts], DISTRICT_BGR.get(name, FLOOR))


def fire_spots(centre: tuple[float, float], level: int) -> list[tuple[float, float]]:
    """Где лежат жетоны кучки: один в центре клетки, несколько — кольцом вокруг.

    Радиус кольца подобран так, чтобы жетоны не касались друг друга (иначе их не
    разделить по контурам), кучка целиком помещалась в клетку 0,8 м и укладывалась
    в порог vision.fire_group_m.
    """
    count = max(1, int(level))
    if count == 1:
        return [centre]
    return [
        (
            centre[0] + FIRE_GAP_M * math.cos(2 * math.pi * i / count),
            centre[1] + FIRE_GAP_M * math.sin(2 * math.pi * i / count),
        )
        for i in range(count)
    ]


def _draw_fire(frame, anchor: Anchor, xy: tuple[float, float]) -> None:
    long_px = max(2, int(round(FIRE_M / anchor.mpp)))
    short_px = max(2, int(round(FIRE_M / FIRE_ASPECT / anchor.mpp)))
    u, v = anchor.to_pixel(*xy)
    if not _visible(frame, u, v, long_px):
        return
    cv2.ellipse(
        frame,
        (int(round(u)), int(round(v))),
        (long_px // 2, short_px // 2),
        0.0,
        0.0,
        360.0,
        FIRE_BGR,
        -1,
    )
