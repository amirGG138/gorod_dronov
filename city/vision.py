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

Пожар на нашем поле обозначен физическим «огоньком» без числа, поэтому здесь
ищется только КЛЕТКА очага, по цвету. Уровень пожара (сколько раз ехать за водой)
цветом не определяется: он приходит из настроек, а с этапа 7 — от VLM. Выдумывать
уровень по картинке нельзя.

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


def find_fire(bgr, hsv_ranges: Iterable = FIRE_HSV, min_area: float = MIN_AREA_PX,
              max_share: float = MAX_AREA_SHARE) -> Blob | None:
    """Самое крупное пятно цвета огня или None.

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
        return None
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
    best: Blob | None = None
    for contour in contours:
        area = float(cv2.contourArea(contour))
        share = area / frame_area if frame_area else 0.0
        if area < min_area or share > max_share:
            continue
        moments = cv2.moments(contour)
        if moments["m00"] <= 0:
            continue
        blob = Blob(moments["m10"] / moments["m00"], moments["m01"] / moments["m00"], area, share)
        if best is None or blob.area > best.area:
            best = blob
    return best


# --- разбор одного кадра ---------------------------------------------------------


@dataclass
class Observation:
    """Что дал один кадр. Пустой результат — это тоже результат, он идёт в лог."""

    drone: str = ""
    fire_cell: Cell | None = None
    fire_xy: tuple[float, float] | None = None
    blob_uv: tuple[float, float] | None = None  # где пятно в кадре — для разметки
    area: float = 0.0
    share: float = 0.0
    anchor: str = "none"  # markers | marker | pose | none
    marker_id: int | None = None
    markers_seen: list[int] = dc_field(default_factory=list)
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
            "area": round(self.area, 1),
            "share": round(self.share, 4),
            "anchor": self.anchor,
            "marker_id": self.marker_id,
            "markers_seen": self.markers_seen,
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
) -> Observation:
    """Разобрать кадр целиком: метки -> привязка -> «огонёк» -> клетка."""
    seen = markers(bgr)
    obs = Observation(drone=drone, markers_seen=sorted(seen))
    anchor = anchor_from_markers(seen, pads, field, marker_edge)
    if anchor is None and pose is not None:
        anchor = anchor_from_pose(pose, alt, bgr.shape, fov_deg)
    if anchor is None:
        obs.note = "ни одной известной метки в кадре и неизвестно, откуда снимали"
        return obs
    obs.anchor, obs.marker_id = anchor.source, anchor.marker_id

    blob = find_fire(bgr, hsv_ranges, min_area, max_share)
    if blob is None:
        obs.note = "очага в кадре нет"
        return obs
    x, y = anchor.to_map(blob.u, blob.v)
    cell = field.m_to_cell(x, y)
    obs.fire_xy, obs.area, obs.share = (x, y), blob.area, blob.share
    obs.blob_uv = (blob.u, blob.v)
    if not field.in_bounds(cell):
        obs.note = f"пятно за границей поля ({x:.2f}, {y:.2f}) м — не очаг"
        return obs
    obs.fire_cell = cell
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

    @property
    def found(self) -> bool:
        return self.fire_cell is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fire_cell": list(self.fire_cell) if self.fire_cell else None,
            "votes": self.votes,
            "total": self.total,
            "by_cell": self.by_cell,
            "drones": self.drones,
        }


def merge(observations: Iterable[Observation]) -> Scene:
    """Голосование по клетке; при равенстве голосов — где пятно крупнее.

    Крупнее — значит ближе: один и тот же «огонёк» на кадре с меньшей высоты и без
    угла занимает больше пикселей.
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
    scene.drones = [o.drone for o in useful if as_cell(o.fire_cell) == best]
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
        if obs.blob_uv is not None:
            u, v = int(obs.blob_uv[0]), int(obs.blob_uv[1])
            radius = max(12, int(math.sqrt(max(obs.area, 1.0) / math.pi)) + 8)
            cv2.circle(canvas, (u, v), radius, (0, 0, 255), 3)
            cv2.line(canvas, (u - radius, v), (u + radius, v), (0, 0, 255), 1)
            cv2.line(canvas, (u, v - radius), (u, v + radius), (0, 0, 255), 1)
        anchor_note = f"anchor={obs.anchor}"
        text = f"fire {list(obs.fire_cell) if obs.fire_cell else '?'} {anchor_note}"
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
    }


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
    if args.debug:
        print(f"размеченный кадр: {draw(frame, obs, field, pads, args.debug)}")
    return 0 if obs.found else 1


if __name__ == "__main__":
    raise SystemExit(main())
