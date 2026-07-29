"""Зрение диспетчера: что видно на кадре дрона-монитора.

Одна задача: по снимку вниз сказать, в какой клетке поля горит. Ни сети, ни ROS,
ни состояния — чистые функции над картинкой, чтобы их можно было гонять на
сохранённых кадрах и на синтетике.

Как кадр привязывается к полю (порядок предпочтения, что сработало — то и пишется
в лог):

1. **две метки площадок в кадре** — масштаб и поворот считаются из их взаимного
   расположения. Точный способ: ничего не предполагаем ни про объектив, ни про то,
   как метки уложены на поле;
2. **одна метка** — масштаб из её стороны (0,25 м, docs/field-map/), поворот из
   угла её верхнего ребра. Здесь появляется единственное соглашение: куда на поле
   смотрит это ребро (vision.marker_edge_deg, проверяется на площадке одним кадром);
3. **метки нет вовсе** — дрон отлетел от площадки. Масштаб считается из высоты и
   угла обзора камеры, центр кадра = точка, куда дрон летел. Грубее, но лучше, чем
   промолчать.

Сторона метки берётся как САМОЕ ДЛИННОЕ ребро квадрата, а не среднее четырёх:
наклонённый дрон видит метку прямоугольником, и среднее занижает сторону — из-за
этого кадр «считает» себя выше, чем есть. Грабли наши, с «Змейки»
(docs/zmeyka.md, hold_aruco/hold_aruco.py:201).

Пожар на нашем поле обозначен физическими «огоньками» без числа, и степень пожара
задаётся тем, СКОЛЬКО жетонов лежит рядом: три огонька кучкой = уровень 3, то есть
три поездки за водой. Поэтому здесь ищется и клетка очага, и число жетонов в кучке.
Считается это так: все пятна нужного цвета переводятся в метры поля, пятна ближе
vision.fire_group_m друг к другу собираются в одну кучку, а число жетонов в кучке —
это число пятен, плюс поправка на слипшиеся (пятно заметно крупнее одиночного
жетона — значит жетонов в нём несколько). Чем именно получено число, пишется в
count_source: blobs (посчитаны пятна) | area (поделили площадь) | mixed.

Чего здесь по-прежнему НЕ делается: уровень не выдумывается. Если кучку посчитать
не вышло или насчитано больше, чем бывает на поле, наружу уходит level=None, и
диспетчер честно берёт уровень из настроек, пометив это в логе.

Проверка кадра руками:

    python3 -m city.vision logs/shots/m1-0012.3.jpg --debug /tmp/раз.jpg
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field as dc_field
from typing import Any, Iterable, Sequence

from .field import Cell, Field, as_cell

try:  # cv2 нужен только для разбора кадров; без него система обязана работать
    import cv2
    import numpy as np

    CV2_ERROR = ""
except Exception as exc:  # noqa: BLE001 — важна причина, а не тип
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    CV2_ERROR = str(exc)

MARKER_M = 0.25  # сторона метки площадки, м — docs/field-map/map.txt
# Цвет «огонька». ЗАМЕРЕНО по восьми фотографиям настоящего жетона на поле
# (photo_fire/, 2026-07-28), а не взято из головы. Что показали замеры:
#   * жетон тёмно-красный: тон 176..181 (то есть по обе стороны нуля), но НЕ оранжевый;
#   * яркость всего 55..190 — первоначальный порог «V >= 120» отбрасывал его в тени;
#   * насыщенность 120..250, и это главное отличие от розового РАЙОНА поля (S 15..43)
#     и от кожи рук и ног в кадре (тон 10..15 при S <= 100).
# Отсюда узкий тон и высокая насыщенность: оранжевый диапазон убран намеренно.
FIRE_HSV = (((0, 120, 40), (5, 255, 255)), ((170, 120, 40), (180, 255, 255)))
# Жетон на поле около 4,5 см. С рабочей высоты 1,5 м это примерно 30 пикселей в
# ширину, то есть пятно порядка 600 пикселей площади: порог 150 даёт четырёхкратный
# запас и всё ещё отсекает блики.
MIN_AREA_PX = 150
MAX_AREA_SHARE = 0.15  # больше — это цветной район поля, а не «огонёк»
FOV_DEG = 65.0  # угол обзора камеры по горизонтали, ГИПОТЕЗА — измерить на площадке

# --- счёт огоньков ---------------------------------------------------------------
# Жетоны одного пожара лежат кучкой, но граница клетки может пройти между ними,
# поэтому кучка собирается по расстоянию НА ПОЛЕ, а не по клетке. 0,4 м — половина
# клетки: три жетона по 4,5 см в такую кучку укладываются, а очаги в разных клетках
# (0,8 м) не слипаются.
GROUP_M = 0.4
TOKEN_M = 0.045  # длинная сторона жетона, м — по фотографиям photo_fire/
# Доля своего квадрата, которую занимает силуэт жетона. ЗАМЕРЕНО по тем же восьми
# фотографиям: площадь пятна к квадрату длинной стороны даёт 0,45..0,49 (жетон —
# язычок пламени, а не квадрат). Нужно только там, где жетоны слиплись в одно пятно
# и делить их приходится по площади.
TOKEN_FILL = 0.47
# Во сколько раз пятно должно быть крупнее одиночного жетона, чтобы считать его за
# несколько. 1,6 — с запасом: одиночный жетон даёт разброс до 1,2, два слипшихся — 2.
SPLIT_RATIO = 1.6
MAX_FIRE_COUNT = 3  # больше огоньков на поле не бывает; насчитали больше — это ошибка


class VisionError(Exception):
    """Кадр не разобрать."""


def _need_cv2() -> None:
    if cv2 is None:
        raise VisionError(
            f"нет OpenCV/numpy, разбирать кадры нечем ({CV2_ERROR}). "
            "Диспетчер должен работать и без них — со сценой из config.yaml"
        )


# --- метки --------------------------------------------------------------------


def _detector():
    """Детектор DICT_4X4_1000 с запасной веткой для OpenCV 4.5.

    Словарь именно на 1000: id 60 и 62 наших меток в DICT_4X4_50 не влезают. Тот же
    словарь стоит у бортовой aruco_detect_node (dictionary_id=3), поэтому опознание
    на ноутбуке и на борту совпадает. На борту OpenCV 4.5.4 — там нет класса
    ArucoDetector, работает старый вызов detectMarkers (сверено на железе 2026-07-27).
    """
    get_dict = getattr(cv2.aruco, "getPredefinedDictionary", None) or cv2.aruco.Dictionary_get
    params_cls = getattr(cv2.aruco, "DetectorParameters", None) or cv2.aruco.DetectorParameters_create
    dictionary = get_dict(cv2.aruco.DICT_4X4_1000)
    params = params_cls()
    if hasattr(cv2.aruco, "ArucoDetector"):
        return cv2.aruco.ArucoDetector(dictionary, params), dictionary, params
    return None, dictionary, params


@dataclass(frozen=True)
class Marker:
    """Метка в кадре: где, какого размера и как повёрнута."""

    id: int
    u: float  # центр, пиксели
    v: float
    side: float  # сторона в пикселях — самое длинное ребро
    angle: float  # угол ребра «угол 0 -> угол 1» в кадре, рад


def markers(bgr) -> dict[int, Marker]:
    """Все метки кадра: {id: Marker}. Фильтра по id нет — отсеиваются вырожденные."""
    _need_cv2()
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr
    detector, dictionary, params = _detector()
    if detector is not None:
        corners, ids, _ = detector.detectMarkers(gray)
    else:
        corners, ids, _ = cv2.aruco.detectMarkers(gray, dictionary, parameters=params)
    if ids is None or len(ids) == 0:
        return {}

    seen: dict[int, Marker] = {}
    for quad, mid in zip(corners, ids.flatten()):
        pts = np.asarray(quad, np.float32).reshape(-1, 2)
        u, v = pts.mean(axis=0)
        side = float(max(np.linalg.norm(pts[i] - pts[(i + 1) % 4]) for i in range(4)))
        if side <= 1.0:
            continue  # вырожденная: масштаб по ней ушёл бы в бесконечность
        edge = pts[1] - pts[0]
        seen[int(mid)] = Marker(
            id=int(mid),
            u=float(u),
            v=float(v),
            side=side,
            angle=math.atan2(float(edge[1]), float(edge[0])),
        )
    return seen


# --- привязка кадра к полю ------------------------------------------------------


@dataclass(frozen=True)
class Anchor:
    """Перевод «пиксель кадра <-> метры поля».

    Камера смотрит вниз, поэтому кадр — это зеркальный поворот плоскости поля:
    правый край кадра идёт вдоль +X, а низ кадра — против +Y. Отсюда матрица

        fx = mpp * ( du*cos(f) + dv*sin(f) )
        fy = mpp * ( du*sin(f) - dv*cos(f) )

    Она сама себе обратная (отражение), поэтому обратный перевод считается той же
    формулой с масштабом 1/mpp — отдельного кода не нужно.
    """

    u0: float  # опорный пиксель…
    v0: float
    x0: float  # …и его точка на поле, м
    y0: float
    mpp: float  # метров на пиксель
    phi: float  # поворот кадра относительно поля, рад
    source: str  # markers | marker | pose
    marker_id: int | None = None

    def to_map(self, u: float, v: float) -> tuple[float, float]:
        du, dv = u - self.u0, v - self.v0
        cos_f, sin_f = math.cos(self.phi), math.sin(self.phi)
        return (
            self.x0 + self.mpp * (du * cos_f + dv * sin_f),
            self.y0 + self.mpp * (du * sin_f - dv * cos_f),
        )

    def to_pixel(self, x: float, y: float) -> tuple[float, float]:
        dx, dy = x - self.x0, y - self.y0
        cos_f, sin_f = math.cos(self.phi), math.sin(self.phi)
        return (
            self.u0 + (dx * cos_f + dy * sin_f) / self.mpp,
            self.v0 + (dx * sin_f - dy * cos_f) / self.mpp,
        )


def anchor_from_markers(
    seen: dict[int, Marker],
    pads: dict[int, Cell],
    field: Field,
    marker_edge: float = 0.0,
) -> Anchor | None:
    """Привязка по меткам площадок. Две метки — точная, одна — с соглашением о ребре."""
    known = {mid: m for mid, m in seen.items() if mid in pads}
    if not known:
        return None
    if len(known) >= 2:
        (id_a, a), (id_b, b) = sorted(known.items())[:2]
        xa, ya = field.cell_to_m(pads[id_a])
        xb, yb = field.cell_to_m(pads[id_b])
        du, dv = b.u - a.u, b.v - a.v
        fx, fy = xb - xa, yb - ya
        pix = math.hypot(du, dv)
        met = math.hypot(fx, fy)
        if pix > 1.0 and met > 1e-6:
            # Поворот кадра: угол вектора между метками на поле плюс его же угол в кадре.
            phi = math.atan2(fy, fx) + math.atan2(dv, du)
            return Anchor(a.u, a.v, xa, ya, met / pix, phi, "markers", id_a)
    mid, m = sorted(known.items())[0]
    x, y = field.cell_to_m(pads[mid])
    return Anchor(m.u, m.v, x, y, MARKER_M / m.side, marker_edge + m.angle, "marker", mid)


def anchor_from_pose(
    xy: Sequence[float],
    alt: float,
    shape: Sequence[int],
    fov_deg: float = FOV_DEG,
) -> Anchor:
    """Запасная привязка: метки в кадре нет, зато известно, куда дрон летел.

    Масштаб — из высоты и угла обзора. Поворот принят нулевым: борт водит команда
    navigate(yaw=0.0), то есть курс дрона в полёте не меняется.
    """
    height, width = int(shape[0]), int(shape[1])
    span = 2.0 * float(alt) * math.tan(math.radians(fov_deg) / 2.0)
    if span <= 0 or width <= 0:
        raise VisionError("угол обзора или высота заданы неверно: масштаб кадра не посчитать")
    return Anchor(width / 2.0, height / 2.0, float(xy[0]), float(xy[1]), span / width, 0.0, "pose")


# --- «огонёк» -------------------------------------------------------------------


@dataclass(frozen=True)
class Blob:
    u: float
    v: float
    area: float  # пиксели
    share: float  # доля площади кадра


def find_fires(bgr, hsv_ranges: Iterable = FIRE_HSV, min_area: float = MIN_AREA_PX,
               max_share: float = MAX_AREA_SHARE) -> list[Blob]:
    """Все пятна цвета огня, крупные первыми.

    Пятен несколько не случайно: степень пожара на поле задана числом жетонов,
    лежащих рядом. Поэтому здесь ничего не схлопывается — кто из пятен образует
    одну кучку, решается уже в метрах поля (см. look).

    Верхний порог площади не декоративный: по углам поля лежат ЦВЕТНЫЕ РАЙОНЫ, и
    красноватый район в кадре — это огромное пятно почти нужного цвета. «Огонёк» —
    предмет размером со спичечный коробок, поэтому пятно во весь кадр отбрасывается.
    """
    _need_cv2()
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = None
    for low, high in hsv_ranges:
        part = cv2.inRange(hsv, np.array(low, np.uint8), np.array(high, np.uint8))
        mask = part if mask is None else cv2.bitwise_or(mask, part)
    if mask is None:
        return []
    # Ядро 3x3, а не 5x5: с рабочей высоты жетон занимает всего десятки пикселей, и
    # более крупное ядро съедало его целиком (проверено на photo_fire/ в уменьшенном
    # до бортового размера виде). Сначала убираем крапинки, потом сращиваем язычки
    # пламени — фигурка узкая, и без этого она распадается на несколько пятен.
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    found = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = found[0] if len(found) == 2 else found[1]  # OpenCV 3 отдавала три значения
    frame_area = float(bgr.shape[0] * bgr.shape[1])
    found_blobs: list[Blob] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        share = area / frame_area if frame_area else 0.0
        if area < min_area or share > max_share:
            continue
        moments = cv2.moments(contour)
        if moments["m00"] <= 0:
            continue
        found_blobs.append(
            Blob(moments["m10"] / moments["m00"], moments["m01"] / moments["m00"], area, share)
        )
    return sorted(found_blobs, key=lambda b: b.area, reverse=True)


def find_fire(bgr, hsv_ranges: Iterable = FIRE_HSV, min_area: float = MIN_AREA_PX,
              max_share: float = MAX_AREA_SHARE) -> Blob | None:
    """Самое крупное пятно цвета огня или None — когда важно «горит ли вообще»."""
    fires = find_fires(bgr, hsv_ranges, min_area, max_share)
    return fires[0] if fires else None


# --- кучка жетонов = степень пожара ------------------------------------------------


@dataclass(frozen=True)
class Spot:
    """Пятно, уже переведённое из пикселей в метры поля."""

    u: float
    v: float
    x: float
    y: float
    area: float
    share: float


@dataclass
class Group:
    """Кучка жетонов: где она и сколько огоньков в ней насчитано."""

    spots: list[Spot]
    count: int
    source: str  # blobs | area | mixed — по чему получилось число
    x: float
    y: float
    area: float
    share: float
    spread: float  # размер кучки, м: далеко разъехавшаяся кучка — повод посмотреть кадр


def token_px(mpp: float, token_m: float = TOKEN_M, token_fill: float = TOKEN_FILL) -> float:
    """Сколько пикселей занимает ОДИН жетон при таком масштабе кадра.

    Нужно ровно для одного случая: жетоны слиплись в единое пятно, и разделить их
    по контурам нельзя. Тогда единственная опора — известный размер жетона.
    Точность здесь равна точности масштаба: с привязкой по метке он измерен по
    настоящему маркеру 25 см, а с привязкой «по точке съёмки» зависит от
    camera.fov_deg, который на площадке ещё надо померить.
    """
    if mpp <= 0:
        return 0.0
    side = token_m / mpp
    return side * side * token_fill


def clusters(spots: Sequence[Spot], group_m: float = GROUP_M) -> list[list[Spot]]:
    """Разбить пятна на кучки: ближе group_m хотя бы к одному соседу — одна кучка.

    Связность именно по соседу, а не по центру кучки: три жетона в ряд образуют
    одну кучку, даже если крайние друг от друга дальше порога. Пятен единицы,
    поэтому наивного перебора хватает с запасом.
    """
    groups: list[list[Spot]] = []
    for spot in spots:
        merged = [spot]
        rest: list[list[Spot]] = []
        for group in groups:
            if any(math.hypot(spot.x - s.x, spot.y - s.y) <= group_m for s in group):
                merged.extend(group)
            else:
                rest.append(group)
        rest.append(merged)
        groups = rest
    return groups


def count_tokens(
    spots: Sequence[Spot],
    unit_px: float,
    split_ratio: float = SPLIT_RATIO,
) -> tuple[int, str]:
    """Сколько жетонов в кучке и по чему это посчитано.

    Основной счёт — по числу пятен: жетоны с зазором дают каждый своё пятно, и это
    точно. Поправка — по площади: слипшиеся жетоны дают одно пятно, зато кратное по
    размеру одиночному. Эталон одиночного берётся, если можно, из самой кучки
    (наименьшее пятно в ней), и только для кучки из одного пятна — из размера жетона
    и масштаба кадра: свой же жетон в кадре — мерка честнее любой расчётной.
    """
    if not spots:
        return 0, "blobs"
    unit = min(s.area for s in spots) if len(spots) >= 2 else unit_px
    if unit <= 0:
        unit = unit_px
    total, split = 0, 0
    for spot in spots:
        n = 1
        if unit > 0 and spot.area >= split_ratio * unit:
            n = max(1, int(round(spot.area / unit)))
        total += n
        if n > 1:
            split += 1
    if not split:
        return total, "blobs"
    return total, "area" if len(spots) == 1 else "mixed"


def _group(spots: Sequence[Spot], unit_px: float, split_ratio: float) -> Group:
    """Собрать кучку в один ответ: центр по площади, размах, число жетонов."""
    area = sum(s.area for s in spots)
    weight = area if area > 0 else float(len(spots))
    if area > 0:
        x = sum(s.x * s.area for s in spots) / weight
        y = sum(s.y * s.area for s in spots) / weight
    else:
        x = sum(s.x for s in spots) / weight
        y = sum(s.y for s in spots) / weight
    spread = max(
        (math.hypot(a.x - b.x, a.y - b.y) for a in spots for b in spots),
        default=0.0,
    )
    count, source = count_tokens(spots, unit_px, split_ratio)
    return Group(
        spots=list(spots),
        count=count,
        source=source,
        x=x,
        y=y,
        area=area,
        share=sum(s.share for s in spots),
        spread=spread,
    )


def _clipped(group: Group, shape: Sequence[int], margin_px: float) -> bool:
    """Кучка подошла к краю кадра — значит часть жетонов могла в него не попасть.

    Такой кадр годится, чтобы сказать ГДЕ горит, но плох, чтобы сказать СКОЛЬКО:
    при сведении наблюдений он уступает кадру, где кучка целиком внутри.
    """
    height, width = float(shape[0]), float(shape[1])
    return any(
        s.u < margin_px or s.u > width - margin_px or s.v < margin_px or s.v > height - margin_px
        for s in group.spots
    )


# --- разбор одного кадра ---------------------------------------------------------


@dataclass
class Observation:
    """Что дал один кадр. Пустой результат — это тоже результат, он идёт в лог."""

    drone: str = ""
    fire_cell: Cell | None = None
    fire_xy: tuple[float, float] | None = None
    blob_uv: tuple[float, float] | None = None  # центр кучки в кадре — для разметки
    fire_count: int = 0  # сколько огоньков насчитано в кучке = степень пожара
    count_source: str = ""  # blobs | area | mixed
    blobs_uv: list[tuple[float, float]] = dc_field(default_factory=list)  # все пятна кучки
    spread_m: float = 0.0  # размах кучки, м
    clipped: bool = False  # кучка у края кадра: считать по нему число ненадёжно
    area: float = 0.0  # суммарная площадь пятен кучки, пиксели
    share: float = 0.0
    anchor: str = "none"  # markers | marker | pose | none
    marker_id: int | None = None
    markers_seen: list[int] = dc_field(default_factory=list)
    # Клетки поля, попавшие в этот кадр. Не «где горит», а «где мы вообще смотрели»:
    # без этого списка «очага не видно» неотличимо от «туда никто не смотрел» (этап 8).
    seen_cells: list[Cell] = dc_field(default_factory=list)
    shot: str = ""
    note: str = ""

    @property
    def found(self) -> bool:
        return self.fire_cell is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "drone": self.drone,
            "fire_cell": list(self.fire_cell) if self.fire_cell else None,
            "fire_xy": [round(v, 3) for v in self.fire_xy] if self.fire_xy else None,
            "fire_count": self.fire_count,
            "count_source": self.count_source,
            "spread_m": round(self.spread_m, 3),
            "clipped": self.clipped,
            "area": round(self.area, 1),
            "share": round(self.share, 4),
            "anchor": self.anchor,
            "marker_id": self.marker_id,
            "markers_seen": self.markers_seen,
            "seen_cells": [list(c) for c in self.seen_cells],
            "shot": self.shot,
            "note": self.note,
        }


def decode(data: bytes):
    """JPEG из сети -> кадр BGR."""
    _need_cv2()
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None or frame.size == 0:
        raise VisionError("кадр не распаковать: пришли не картинка или обрезанный JPEG")
    return frame


def cells_in_frame(anchor: Anchor, field: Field, shape: Sequence[int]) -> list[Cell]:
    """Какие клетки поля попали в этот кадр.

    Считается обратным переводом: центр каждой клетки переводится в пиксель и
    проверяется, лежит ли он внутри кадра. Так учитывается и поворот кадра
    относительно поля, чего не дала бы прикидка «прямоугольник вокруг кадра».

    Клетка засчитывается по своему ЦЕНТРУ: попавший в кадр краешек клетки ничего
    не говорит о том, лежит ли на ней огонёк.
    """
    height, width = int(shape[0]), int(shape[1])
    out = []
    for cell in field.cells():
        u, v = anchor.to_pixel(*field.cell_to_m(cell))
        if 0 <= u < width and 0 <= v < height:
            out.append(cell)
    return out


def look(
    bgr,
    field: Field,
    pads: dict[int, Cell],
    *,
    drone: str = "",
    pose: Sequence[float] | None = None,
    alt: float = 1.5,
    fov_deg: float = FOV_DEG,
    marker_edge: float = 0.0,
    hsv_ranges: Iterable = FIRE_HSV,
    min_area: float = MIN_AREA_PX,
    max_share: float = MAX_AREA_SHARE,
    group_m: float = GROUP_M,
    token_m: float = TOKEN_M,
    token_fill: float = TOKEN_FILL,
    split_ratio: float = SPLIT_RATIO,
) -> Observation:
    """Разобрать кадр целиком: метки -> привязка -> «огоньки» -> клетка и их число."""
    seen = markers(bgr)
    obs = Observation(drone=drone, markers_seen=sorted(seen))
    anchor = anchor_from_markers(seen, pads, field, marker_edge)
    if anchor is None and pose is not None:
        anchor = anchor_from_pose(pose, alt, bgr.shape, fov_deg)
    if anchor is None:
        obs.note = "ни одной известной метки в кадре и неизвестно, откуда снимали"
        return obs
    obs.anchor, obs.marker_id = anchor.source, anchor.marker_id
    obs.seen_cells = cells_in_frame(anchor, field, bgr.shape)

    blobs = find_fires(bgr, hsv_ranges, min_area, max_share)
    if not blobs:
        obs.note = "очага в кадре нет"
        return obs
    spots = []
    for blob in blobs:
        x, y = anchor.to_map(blob.u, blob.v)
        spots.append(Spot(blob.u, blob.v, x, y, blob.area, blob.share))
    inside = [s for s in spots if field.in_bounds(field.m_to_cell(s.x, s.y))]
    if not inside:
        s = spots[0]
        obs.fire_xy, obs.area, obs.share = (s.x, s.y), s.area, s.share
        obs.blob_uv, obs.blobs_uv = (s.u, s.v), [(s.u, s.v)]
        obs.note = f"пятно за границей поля ({s.x:.2f}, {s.y:.2f}) м — не очаг"
        return obs

    unit_px = token_px(anchor.mpp, token_m, token_fill)
    groups = [_group(g, unit_px, split_ratio) for g in clusters(inside, group_m)]
    # Кучек может быть несколько: очаг один, а рядом мог оказаться посторонний
    # красный предмет. Берём самую многочисленную, при равенстве — самую крупную.
    best = max(groups, key=lambda g: (g.count, g.area))
    obs.fire_xy = (best.x, best.y)
    obs.blob_uv = anchor.to_pixel(best.x, best.y)
    obs.blobs_uv = [(s.u, s.v) for s in best.spots]
    obs.fire_count, obs.count_source = best.count, best.source
    obs.spread_m, obs.area, obs.share = best.spread, best.area, best.share
    obs.clipped = _clipped(best, bgr.shape, group_m / 2.0 / anchor.mpp if anchor.mpp > 0 else 0.0)
    obs.fire_cell = field.m_to_cell(best.x, best.y)
    notes = []
    if len(groups) > 1:
        notes.append(f"кучек огня в кадре {len(groups)}, взята самая многочисленная")
    if obs.clipped:
        notes.append("кучка у края кадра — число огоньков по нему считать ненадёжно")
    obs.note = "; ".join(notes)
    return obs


# --- сведение наблюдений ---------------------------------------------------------


@dataclass
class Scene:
    """Итог разведки: где горит и чем это подтверждено."""

    fire_cell: Cell | None = None
    votes: int = 0
    total: int = 0
    by_cell: dict[str, int] = dc_field(default_factory=dict)
    drones: list[str] = dc_field(default_factory=list)
    level: int | None = None  # степень пожара = число огоньков; None — считать не вышло
    level_votes: dict[str, int] = dc_field(default_factory=dict)  # «число огоньков»: кадров
    clipped_only: bool = False  # кучку видели только краем кадра
    count_note: str = ""

    @property
    def found(self) -> bool:
        return self.fire_cell is not None

    @property
    def sure(self) -> bool:
        """Разведка сделала своё дело: клетка найдена И огоньки сосчитаны по целой кучке.

        Именно этим, а не одним «найдено», решается, прекращать ли облёт: кадр, где
        кучка упёрлась в край, говорит ГДЕ горит, но занижает СКОЛЬКО, а заниженный
        уровень — это недовезённая вода.
        """
        return self.found and self.level is not None and not self.clipped_only

    def to_dict(self) -> dict[str, Any]:
        return {
            "fire_cell": list(self.fire_cell) if self.fire_cell else None,
            "votes": self.votes,
            "total": self.total,
            "by_cell": self.by_cell,
            "drones": self.drones,
            "level": self.level,
            "level_votes": self.level_votes,
            "clipped_only": self.clipped_only,
            "count_note": self.count_note,
        }


def merge(observations: Iterable[Observation], max_count: int = MAX_FIRE_COUNT) -> Scene:
    """Голосование по клетке; при равенстве голосов — где пятно крупнее.

    Крупнее — значит ближе: один и тот же «огонёк» на кадре с меньшей высоты и без
    угла занимает больше пикселей.

    Степень пожара считается отдельно и только по кадрам, показавшим победившую
    клетку. Кадры, где кучка упёрлась в край, в счёте не участвуют, пока есть хоть
    один целый: обрезанная кучка занижает число, а заниженная степень — это недовезённая
    вода и невыполненная миссия. Из оставшихся берётся самое частое число, при
    равенстве — большее, по той же причине.
    """
    useful = [o for o in observations if o.found]
    scene = Scene(total=len(useful))
    if not useful:
        return scene
    votes: dict[Cell, int] = {}
    weight: dict[Cell, float] = {}
    for o in useful:
        cell = as_cell(o.fire_cell)
        votes[cell] = votes.get(cell, 0) + 1
        weight[cell] = weight.get(cell, 0.0) + o.area
    best = max(votes, key=lambda c: (votes[c], weight[c]))
    scene.fire_cell = best
    scene.votes = votes[best]
    scene.by_cell = {f"{c[0]},{c[1]}": n for c, n in sorted(votes.items())}
    same = [o for o in useful if as_cell(o.fire_cell) == best]
    scene.drones = [o.drone for o in same]

    counted = [o for o in same if o.fire_count > 0]
    whole = [o for o in counted if not o.clipped]
    all_clipped = not whole and bool(counted)
    if all_clipped:
        whole = counted
    if not whole:
        scene.count_note = "число огоньков не посчитано ни на одном кадре"
        return scene
    tally: dict[int, int] = {}
    for o in whole:
        tally[o.fire_count] = tally.get(o.fire_count, 0) + 1
    level = max(tally, key=lambda n: (tally[n], n))
    scene.level_votes = {str(n): k for n, k in sorted(tally.items())}
    if level > max_count:
        scene.count_note = (
            f"насчитано огоньков {level}, а больше {max_count} на поле не бывает — "
            "это ошибка распознавания, уровень остаётся из настроек"
        )
    elif all_clipped:
        scene.level = level
        scene.clipped_only = True
        scene.count_note = "все кадры с кучкой у края — число огоньков может быть занижено"
    else:
        scene.level = level
    return scene


# --- разметка кадра для человека --------------------------------------------------


def draw(bgr, obs: Observation, field: Field, pads: dict[int, Cell], path: str) -> str:
    """Сохранить кадр с разметкой: метки, пятно, подписанная клетка.

    Этим на площадке подбираются пороги цвета, и этим же показывают на техзащите,
    что решение принято по картинке, а не по файлу настроек.
    """
    _need_cv2()
    canvas = bgr.copy()
    for mid, m in markers(bgr).items():
        known = mid in pads
        colour = (0, 200, 0) if known else (0, 165, 255)
        cv2.circle(canvas, (int(m.u), int(m.v)), int(m.side / 2), colour, 2)
        label = f"id{mid} {list(pads[mid])}" if known else f"id{mid} ?"
        cv2.putText(canvas, label, (int(m.u) - 40, int(m.v) - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2)
    if obs.fire_xy is not None:
        # Кружок вокруг КАЖДОГО жетона кучки: на техзащите по размеченному кадру
        # должно быть видно не только «где горит», но и почему уровень такой.
        one = max(12, int(math.sqrt(max(obs.area, 1.0) / max(obs.fire_count, 1) / math.pi)) + 8)
        for spot in obs.blobs_uv or ([obs.blob_uv] if obs.blob_uv else []):
            u, v = int(spot[0]), int(spot[1])
            cv2.circle(canvas, (u, v), one, (0, 0, 255), 3)
            cv2.line(canvas, (u - one, v), (u + one, v), (0, 0, 255), 1)
            cv2.line(canvas, (u, v - one), (u, v + one), (0, 0, 255), 1)
        count = f" x{obs.fire_count} ({obs.count_source})" if obs.fire_count else ""
        text = f"fire {list(obs.fire_cell) if obs.fire_cell else '?'}{count} anchor={obs.anchor}"
        cv2.putText(canvas, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    else:
        cv2.putText(canvas, obs.note or "no fire", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
    cv2.imwrite(path, canvas)
    return path


# --- запуск руками -----------------------------------------------------------------


def pads_from_config(cfg) -> dict[int, Cell]:
    """{id метки: клетка площадки} из config.yaml. Ключи в YAML строковые."""
    raw = cfg.get("aruco.pads", {})
    items = raw.items() if hasattr(raw, "items") else {}
    return {int(mid): as_cell(cell) for mid, cell in items}


def settings(cfg) -> dict[str, Any]:
    """Всё, что зрение берёт из config.yaml, одним словарём."""
    ranges = cfg.get("vision.fire_hsv", None)
    if ranges:
        hsv = tuple((tuple(low), tuple(high)) for low, high in ranges)
    else:
        hsv = FIRE_HSV
    return {
        "fov_deg": float(cfg.get("camera.fov_deg", FOV_DEG)),
        "marker_edge": math.radians(float(cfg.get("vision.marker_edge_deg", 0.0))),
        "hsv_ranges": hsv,
        "min_area": float(cfg.get("vision.min_area_px", MIN_AREA_PX)),
        "max_share": float(cfg.get("vision.max_area_share", MAX_AREA_SHARE)),
        "group_m": float(cfg.get("vision.fire_group_m", GROUP_M)),
        "token_m": float(cfg.get("vision.token_m", TOKEN_M)),
        "token_fill": float(cfg.get("vision.token_fill", TOKEN_FILL)),
        "split_ratio": float(cfg.get("vision.split_ratio", SPLIT_RATIO)),
    }


def max_count(cfg) -> int:
    """Потолок числа огоньков: больше — считаем ошибкой распознавания."""
    return int(cfg.get("vision.max_fire_count", MAX_FIRE_COUNT))


def main(argv: list[str] | None = None) -> int:
    import argparse

    from . import config as config_mod

    p = argparse.ArgumentParser(prog="city.vision", description="разобрать кадр дрона-монитора")
    p.add_argument("shot", help="файл кадра, например logs/shots/m1-0012.3.jpg")
    p.add_argument("--config", default=config_mod.CONFIG_PATH)
    p.add_argument("--debug", help="куда сохранить кадр с разметкой")
    p.add_argument("--pose", help="откуда снимали, метры x,y — если метки в кадре нет")
    p.add_argument("--alt", type=float, default=1.5, help="высота съёмки, м")
    args = p.parse_args(argv)

    cfg = config_mod.load(args.config)
    field = Field.from_config(cfg)
    pads = pads_from_config(cfg)
    with open(args.shot, "rb") as fh:
        frame = decode(fh.read())
    pose = [float(v) for v in args.pose.split(",")] if args.pose else None
    obs = look(frame, field, pads, drone="файл", pose=pose, alt=args.alt, **settings(cfg))
    print(json.dumps(obs.to_dict(), ensure_ascii=False, indent=2))
    if obs.found:
        print(
            f"очаг в клетке {list(obs.fire_cell)}: огоньков {obs.fire_count} "
            f"(счёт по «{obs.count_source}», кучка {obs.spread_m:.2f} м) — "
            f"столько же раз ехать за водой"
        )
    if args.debug:
        print(f"размеченный кадр: {draw(frame, obs, field, pads, args.debug)}")
    return 0 if obs.found else 1


if __name__ == "__main__":
    raise SystemExit(main())
