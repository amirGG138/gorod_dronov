#!/usr/bin/env python3
"""Дрон-монитор: висит над своей меткой и ищет огонь. Борт отвечает диспетчеру по сети.

Один файл. Копируется на дрон и запускается ВНУТРИ контейнера sverk_ros2:

    python3 drone_agent.py --port 8020 --name m1 --cell 1,1

Порт 8020 — внутри контейнера. Снаружи (с ноутбука, с другого борта) этот порт виден
как 2200: на дроне настроен постоянный проброс 2200 → 8020. Порт 80 внутри контейнера
не годится — занять его может только root, а мы работаем под sverk.

Проверка с ноутбука (адрес дрона подставить свой):

    curl http://192.168.1.50:2200/status
    curl -X POST http://192.168.1.50:2200/takeoff -d '{"alt":2.0}'
    curl http://192.168.1.50:2200/shot -o kadr.jpg
    curl http://192.168.1.50:2200/fire
    curl -X POST http://192.168.1.50:2200/land

КОНЦЕПЦИЯ: дрон никуда не летит. Он поднимается на рабочую высоту над своей площадкой
и висит там, удерживаясь по СВОЕЙ ArUco-метке, а огонь ищет по кадрам с этой же точки.
Прежняя схема — облёт четырёх точек обзора с удержанием высоты по дальномеру — убрана
целиком: точки обзора выносят дрон за край крыши, дальномер там скачком меняет
показания на высоту дома, и дрон проседает и подскакивает, теряя метку под камерой
(живой прогон 2026-07-28).

Что этим держится и по чему (телеметрия не используется — get_telemetry на наших
сборках виснет без полётного контроллера, а /status обязан отвечать всегда):

* положение — по промаху до ЦЕНТРА метки в кадре, переведённому в метры по её же
  стороне (25 см), поэтому калибровка камеры для этого не нужна;
* высота — по стороне метки в пикселях: она обратно пропорциональна высоте. Оценка
  ОТНОСИТЕЛЬНАЯ: сторона метки запоминается эталоном после набора, и дальше дрон
  возвращается туда, где уже висел (как на стенде hold_aruco). Абсолютная оценка
  через --fov-deg отсюда убрана 30.07.2026: и настоящая сторона маркера, и угол
  обзора камеры у нас гипотезы, а ошибка в любом из них не портит замер слегка —
  она врёт по высоте ровно во столько же раз и всё время в одну сторону, так что
  дрон считает себя ниже, чем есть, и лезет вверх до потолка. Разбор — у alt_by_ref;
* курс — по повороту метки в кадре: метки поля уложены одинаково, значит поворот
  метки в кадре показывает, как повёрнут сам дрон. yaw=0.0 при frame_id="body" курс
  НЕ держит («не менять курс»), то есть каждая команда закрепляла бы накопленный увод.

Такт удержания идёт циклом «замерил → сдвинулся → дал успокоиться → замерил снова»
(--settle): navigate не блокирующий, он только ставит цель, и мерить дрон, пока он к
ней едет и висит с креном, — верный способ получить качку вместо зависания. Разбор в
докстроке hold_tick.

Взлёт идёт В ДВЕ СТУПЕНИ (с 30.07.2026). Первая — --takeoff-blind метров (0,7) ОДНОЙ
командой вслепую: с площадки метка в кадр не помещается, держаться на этой ступени не
за что. Вторая — остаток до рабочей высоты, и его набирает уже контур удержания:
шагами по --climb-step, и каждый шаг он попутно правит положение и курс ПО МЕТКЕ, а
вот высоту по метке не мерит вовсе — сколько осталось набрать, борт знает по своим же
командам. Высота начинает мериться по метке только после того, как набор кончился:
тогда снимается эталон (см. alt_by_ref) и включается обычное удержание.

Почему высота на наборе именно по счёту, а не по метке. navigate не блокирующий, и
пока дрон едет вверх, кадр показывает высоту, которая уже отрабатывается: контур,
меряющий её в этот момент, видит недобор, досылает его поверх — и набор складывается
сам с собой. Со счётом этого нет: борт вычитает из остатка ровно то, что скомандовал,
и следующий шаг уходит только после того, как предыдущий доехал (--settle).

Состояние на время набора — climbing, а не hover: «вишу» означает «стою на рабочей
высоте», и диспетчер по нему решает, можно ли снимать кадр для огня.

Метки нет в кадре — держаться не за что, и после --blind-max таких кадров борт не
замирает, а ИЩЕТ её: поднимается на --search-rise (шире обзор) и по очереди отходит на
--search-step в каждую сторону, возвращаясь в точку потери. Подниматься вверх разрешено
не больше --search-rise × --search-rise-max метров над рабочей высотой и никогда выше
--max-alt; пока метку видно, это превышение не счисляется, а измеряется по ней же.
Разбор в докстроках _search и hold_tick.

Что важно знать про этот файл (всё добыто на живом железе, не выдумано):

* Камера выданных бортов отдаёт bgr8 1280x960 — патч patch_yuv на них не нужен и
  оставлен страховкой под сборку, публикующую yuv422_yuy2: на такой штатный
  перевод в картинку падает и кадров не будет ни одного (sverh_snake/
  Archipelago2026/fly_head.py:173).
* navigate на ОДНУ КОМАНДУ издаётся ровно один раз: повторный вызов
  переинициализирует траекторию, и дрон бесконечно начинает заход заново. К такту
  удержания это не относится — там каждая команда есть новая короткая цель от
  текущего места, и переинициализация как раз и нужна (так же устроен стенд
  hold_aruco/hold_aruco.py). Дедупликация по command_id остаётся: повтор POST по
  потерянному ответу не должен превращаться во второй взлёт.
* auto_arm=True всегда: без него просевший и дизармившийся дрон уже не поднимется.
* land() может вернуть успех и ничего не сделать, а на части сборок принимает
  timeout и без него бросает TypeError. Обе сигнатуры обёрнуты, посадка повторяется.
  Принятая команда — это ещё не посадка, поэтому состояний два: landed (подтверждено
  дизармом по телеметрии) и landed_unverified (команда принята, доказательств нет).
* Плечо камеры: body отсчитывается от ЦЕНТРА корпуса, а метку наводит ОБЪЕКТИВ.
  Разница снимается ключом --cam-fwd, но по умолчанию он 0: поправка вводится
  только по замеренному на площадке промаху, а не вслепую.

Требуется только стандартная библиотека + sverk_interfaces + cv2/numpy, которые на
борту уже стоят. Режим --dry позволяет запустить файл где угодно без железа.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "2.0"

# Сколько последних command_id помнить, чтобы узнать повтор. Команд за попытку
# десятки, так что помним с запасом и всё равно не растём в памяти.
DEDUP_KEEP = 64

# Состояния, означающие «дрон не в воздухе». landed — посадка подтверждена
# телеметрией, landed_unverified — команда принята и пауза выждана, доказательств нет.
ON_GROUND = ("idle", "landed", "landed_unverified")

# Состояния «дрон в воздухе»: сюда же входит climbing — набор остатка высоты контуром
# после слепой ступени взлёта. Всё, что сажает дрон по факту «мы наверху» (сторож,
# выход из программы, защита от второго взлёта), смотрит именно сюда.
ALOFT = ("taking_off", "climbing", "hover")

# Сторона метки площадки, м (docs/field-map/map.txt). По ней кадр переводится в метры,
# поэтому ошибка здесь даёт систематический промах и «плавающую» высоту: перемерить
# рулеткой в первый день.
MARKER_M = 0.25

# Какой маркер лежит на какой площадке (docs/field-map/README.md). Дрон цепляется
# только за свой: между метками поля 2,4 м, и без фильтра по номеру он перепрыгивал бы
# на соседнюю. Клетки 0-based, как везде в проекте.
PAD_MARKER = {(1, 4): 50, (4, 4): 60, (1, 1): 62, (4, 1): 7}

# Куда отходить, разыскивая потерянную метку: вперёд, назад, влево, вправо (доли
# --search-step по осям body). После каждого отхода дрон ВОЗВРАЩАЕТСЯ в центр, и
# только потом пробует следующую сторону: иначе четыре отхода подряд уводят его на
# метр с лишним от точки, где метку видели последний раз, и поиск сам себя губит.
SEARCH_LEGS = ((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0))

# Цвет «огонька» в HSV OpenCV (H 0..180). Два диапазона: красный лежит по обоим краям
# круга. ЗАМЕРЕНО по восьми фотографиям настоящего жетона (photo_fire/, 2026-07-28):
# тон 176..181, насыщенность 120..250, яркость 55..190 — он ТЁМНО-КРАСНЫЙ, не
# оранжевый. Высокая насыщенность отделяет его от розового района поля (S 15..43) и от
# кожи рук в кадре (тон 10..15). Те же числа лежат в city/config.yaml.
FIRE_HSV = (((0, 120, 40), (5, 255, 255)), ((170, 120, 40), (180, 255, 255)))

# Заглушка-кадр для режима --dry: настоящий, хоть и крохотный, JPEG.
DRY_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABsSFBcUERsXFhceHBsgKEIrKCUlKFE6PTBCYFVlZF9VXVtqeJmB"
    "anGQc1tdhbWGkJ6jq62rZ4C8ybqmx5moq6T/2wBDARweHigjKE4rK06kbl1upKSkpKSkpKSkpKSkpKSkpKSk"
    "pKSkpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKT/wAARCAAQABADASIAAhEBAxEB/8QAFQABAQAAAAAA"
    "AAAAAAAAAAAAAAP/xAAaEAACAgMAAAAAAAAAAAAAAAAEEgAREyJB/8QAFAEBAAAAAAAAAAAAAAAAAAAAAP/E"
    "ABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AJDD522Va5cEj4F2Zr5UDEYG1Zq7UEkZ11Vb7cD/"
    "2Q=="
)


def say(text: str) -> None:
    """Строка в терминал дрона. Её читает человек, стоящий рядом с аппаратом."""
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
#  КАМЕРА
# ═══════════════════════════════════════════════════════════════════════════


def patch_yuv(drone, color: str = "bgr") -> bool:
    """Научить камеру отдавать картинку: бортовая может публиковать yuv422_yuy2, а to_cv2 его не знает.

    Порядок каналов на выходе делаем таким же, как у штатного take_picture (см. --color),
    иначе один и тот же кадр будет разного цвета в зависимости от сборки камеры.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        say("ВНИМАНИЕ: нет cv2/numpy — кадры отдавать нечем")
        return False

    image = getattr(drone, "image", None)
    original = getattr(image, "to_cv2", None)
    if original is None:
        return False

    target = cv2.COLOR_YUV2RGB_YUY2 if color == "rgb" else cv2.COLOR_YUV2BGR_YUY2

    def to_cv2(msg):
        if (getattr(msg, "encoding", "") or "").lower() in ("yuv422_yuy2", "yuyv", "yuv422"):
            yuv = np.frombuffer(msg.data, np.uint8).reshape((msg.height, msg.width, 2))
            return cv2.cvtColor(yuv, target)
        return original(msg)

    image.to_cv2 = to_cv2
    return True


def encode_jpeg(frame, color: str = "bgr") -> bytes | None:
    """Сжать кадр в JPEG.

    Порядок каналов у камеры борта — BGR, как и объявлено в топике (bgr8): проверено
    глазами на полу известного цвета 2026-07-28. cv2.imencode ждёт ровно его, поэтому
    по умолчанию кадр не трогаем. Флаг --color rgb оставлен на случай другой сборки
    камеры: если на кадре красное выглядит синим, каналы надо переставить.
    """
    import cv2

    if color == "rgb":
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes() if ok else None


# ═══════════════════════════════════════════════════════════════════════════
#  ЗРЕНИЕ: метки в кадре
# ═══════════════════════════════════════════════════════════════════════════
#
# Словарь 4X4_1000, а не 4X4_50: маркеры нашего поля 50, 60, 62, 7 (docs/field-map/),
# и 60 с 62 в словарь на 50 элементов не влезают. Тот же словарь стоит по умолчанию
# у бортовой aruco_detect_node (dictionary_id=3), так что опознание совпадёт.

_DETECTOR = None  # собирается один раз при первом кадре: cv2 импортируется лениво


def _detector():
    """Опознаватель меток: (словарь, параметры, детектор-объект). Словарь None — нечем.

    Объект-детектор есть только с OpenCV 4.7+; на борту 4.5.4, там работает старая
    функция cv2.aruco.detectMarkers — поэтому третий элемент бывает None, и это норма.
    """
    global _DETECTOR
    if _DETECTOR is not None:
        return _DETECTOR
    try:
        import cv2

        aruco = cv2.aruco
    except (ImportError, AttributeError):
        _DETECTOR = (None, None, None)
        return _DETECTOR
    dictionary = (aruco.getPredefinedDictionary if hasattr(aruco, "getPredefinedDictionary")
                  else aruco.Dictionary_get)(aruco.DICT_4X4_1000)
    params = (aruco.DetectorParameters() if hasattr(aruco, "DetectorParameters")
              else aruco.DetectorParameters_create())
    detector = aruco.ArucoDetector(dictionary, params) if hasattr(aruco, "ArucoDetector") else None
    _DETECTOR = (dictionary, params, detector)
    return _DETECTOR


class Fix:
    """Замер одной метки в кадре: где её центр, какого она размера и как повёрнута."""

    __slots__ = ("id", "u", "v", "side", "angle")

    def __init__(self, mid: int, u: float, v: float, side: float, angle: float) -> None:
        self.id = int(mid)
        self.u = float(u)          # центр метки в кадре, пиксели
        self.v = float(v)
        self.side = float(side)    # сторона, пиксели — масштаб кадра
        self.angle = float(angle)  # поворот верхнего ребра, радианы


def quad_center(pts) -> tuple[float, float]:
    """Центр четырёхугольника — точка пересечения его диагоналей.

    Не среднее четырёх углов: камера смотрит на метку под наклоном, квадрат виден
    трапецией, и центр трапеции — это именно пересечение диагоналей, а среднее углов
    от него заметно уезжает. На зависании держаться надо за центр метки, поэтому
    считаем честно; вырожденный случай (диагонали почти параллельны — метка видна с
    ребра, углы опознаны криво) откатывается на среднее.
    """
    (x1, y1), (x2, y2), (x3, y3), (x4, y4) = (
        (float(p[0]), float(p[1])) for p in (pts[0], pts[1], pts[2], pts[3])
    )
    ax, ay = x3 - x1, y3 - y1          # диагональ 0->2
    bx, by = x4 - x2, y4 - y2          # диагональ 1->3
    denominator = ax * by - ay * bx
    if abs(denominator) < 1e-6:
        return (x1 + x2 + x3 + x4) / 4.0, (y1 + y2 + y3 + y4) / 4.0
    t = ((x2 - x1) * by - (y2 - y1) * bx) / denominator
    return x1 + ax * t, y1 + ay * t


def markers(frame) -> dict[int, Fix]:
    """Все метки кадра: {id: Fix}. Пусто — меток нет или разбирать нечем.

    Сторона метки берётся как САМОЕ ДЛИННОЕ ребро, а не среднее четырёх. Наклонённый
    дрон видит квадрат метки прямоугольником: рёбра вдоль оси наклона длину сохраняют,
    поперечные сжимаются. Среднее занижало сторону, а по ней считается высота — дрон
    решал, что он выше, чем есть (грабли «Змейки», docs/zmeyka.md).
    """
    import cv2
    import numpy as np

    dictionary, params, detector = _detector()
    if dictionary is None:
        return {}
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    if detector is not None:
        corners, ids, _ = detector.detectMarkers(gray)
    else:
        corners, ids, _ = cv2.aruco.detectMarkers(gray, dictionary, parameters=params)
    if ids is None or len(ids) == 0:
        return {}

    seen: dict[int, Fix] = {}
    for quad, mid in zip(corners, ids.flatten()):
        pts = np.asarray(quad, np.float32).reshape(-1, 2)
        side = max(float(np.linalg.norm(pts[i] - pts[(i + 1) % 4])) for i in range(4))
        if side <= 1.0:
            continue  # вырожденная: масштаб по ней ушёл бы в бесконечность
        u, v = quad_center(pts)
        edge = pts[1] - pts[0]
        seen[int(mid)] = Fix(mid, u, v, side, math.atan2(float(edge[1]), float(edge[0])))
    return seen


# ═══════════════════════════════════════════════════════════════════════════
#  ГЕОМЕТРИЯ: пиксели, метры, высота
# ═══════════════════════════════════════════════════════════════════════════


def focal_px(width: float, fov_deg: float) -> float:
    """Фокусное расстояние камеры в пикселях по её углу обзора и ширине кадра.

    Нужно ровно для одного: перевести сторону метки в АБСОЛЮТНУЮ высоту. Угол обзора
    65° — гипотеза (city/vision.py), поэтому на площадке его калибруют одной рулеткой:
    подвесить дрон на известной высоте h, взять из лога сторону метки s и посчитать
    focal = s * h / 0.25, а затем задать ключом --focal-px.
    """
    half = math.radians(float(fov_deg)) / 2.0
    if width <= 0 or half <= 0 or half >= math.pi / 2:
        return 0.0
    return (float(width) / 2.0) / math.tan(half)


def alt_by_side(side: float, focal: float, marker_m: float = MARKER_M) -> float | None:
    """Абсолютная высота над плоскостью метки по её стороне в кадре, м. None — нечем.

    Сторона в пикселях обратно пропорциональна высоте: s = focal * L / h.

    УДЕРЖАНИЕ ВЫСОТЫ ЭТИМ НЕ ПОЛЬЗУЕТСЯ (с 30.07.2026, см. alt_by_ref) — только
    зрение огня, которому нужен масштаб кадра там, где метки под дроном нет вовсе.
    """
    if side <= 1.0 or focal <= 0.0:
        return None
    return focal * marker_m / side


def alt_by_ref(side: float, side_ref: float, alt_ref: float) -> float | None:
    """Высота по стороне метки ОТНОСИТЕЛЬНО эталона, м. None — посчитать нечем.

    Перенесено со стенда (hold_aruco/hold_aruco.py: alt_by_side): запомнили сторону
    метки на рабочей высоте — и дальше каждой командой возвращаемся к ней,
    h = alt_ref * side_ref / side.

    Чем это лучше абсолютной формулы, стоявшей здесь до 30.07.2026. В абсолютной два
    числа, которых мы не знаем: настоящая сторона маркера (MARKER_M — гипотеза из
    docs/field-map/, рулеткой не мерена) и настоящий угол обзора камеры (--fov-deg —
    тоже гипотеза). Ошибка в любом из них не «немного портит замер»: она ровно во
    столько же раз врёт по высоте, причём в одну сторону всё время. Дрон считает, что
    висит ниже, чем на самом деле, честно лезет вверх — и упирается в потолок, потому
    что «долетел» по его счёту не наступает никогда. Здесь обе неизвестных
    сокращаются: сколько бы ни было в метре пикселей, дрон возвращается туда, где он
    уже висел.

    Плата ровно одна: эталон надо снять, и снимается он ПОСЛЕ набора высоты. Значит
    рабочая высота такая, какую отработал взлёт, — промах взлёта эталон закрепит. Это
    видно по side_ref в /status и лечится ключом --alt, а в потолок так не уйти.
    """
    if side <= 1.0 or side_ref <= 1.0 or alt_ref <= 0.0:
        return None
    return alt_ref * side_ref / side


def aim(fix: Fix, width: float, height: float, cam_fwd: float, cam_left: float,
        sign_fwd: float = 1.0, sign_left: float = 1.0) -> tuple[float, float]:
    """Насколько дрон стоит мимо центра метки: (вперёд, влево) в метрах.

    Пиксели в метры переводятся по стороне самой метки, поэтому калибровка камеры
    здесь не нужна. Камера смотрит вниз: верх кадра — «вперёд», левый край — «влево».

    Знак. Метка ниже центра кадра (v > cy) лежит ПОЗАДИ объектива — значит дрон
    отнесло вперёд и лететь надо назад; отсюда минус. Ни знак «вперёд», ни знак
    «влево» на железе не сверялись, поэтому оба вынесены в ключи --sign-fwd и
    --sign-left: если дрон уезжает от метки ровно вдвое быстрее, чем должен бы
    возвращаться, знак перевёрнут.

    Плечо камеры. body отсчитывается от ЦЕНТРА корпуса, а метку наводит ОБЪЕКТИВ,
    вынесенный вперёд. Разница снимается сдвигом точки прицеливания: целимся на
    cam_fwd метров назад. Проверяется тремя зависаниями подряд — если дрон устойчиво
    стоит мимо метки на одну и ту же величину в одну и ту же сторону, это оно; если
    промах вырос вдвое, знак надо перевернуть, а не увеличивать число.
    """
    scale = MARKER_M / fix.side
    forward = sign_fwd * -(fix.v - height / 2.0) * scale - cam_fwd
    left = sign_left * -(fix.u - width / 2.0) * scale - cam_left
    return forward, left


def turn_error(angle: float, reference: float, limit_deg: float) -> float | None:
    """Насколько дрон отвернулся от курса взлёта, радианы (−π…π). None — не верим замеру.

    Увод больше limit_deg неправдоподобен: каждая команда navigate курс всё-таки
    удерживает, а метка под монитором одна и та же. Столько даёт либо сбой опознания
    углов метки, либо чужая метка, положенная повёрнутой, — отработать такой «увод»
    значит развернуть дрон на десятки градусов на ровном месте. Поэтому не поправка
    нулём, а честное «замер негодный»: про это надо сказать в лог.
    """
    error = (angle - reference + math.pi) % (2 * math.pi) - math.pi
    return None if abs(error) > math.radians(limit_deg) else error


def yaw_fix(error: float, dead_deg: float, fix_deg: float) -> float:
    """Доворот для очередного navigate, радианы.

    Знак: turn_error даёт увод ПРОТИВ часовой, и положительный yaw в body — тоже
    против часовой (в документации set_yaw(-pi/2) описан как поворот по часовой),
    значит отработать увод — скомандовать ему обратный знак.

    Отдаём не весь увод разом, а не больше fix_deg: на большом довороте кадр
    смазывается сильнее, чем стоит того выигрыш. Мелочь внутри dead_deg не трогаем
    вовсе — иначе дрон дёргался бы на шуме опознания метки.
    """
    if abs(error) < math.radians(dead_deg):
        return 0.0
    limit = math.radians(fix_deg)
    return max(-limit, min(limit, -error))


# ═══════════════════════════════════════════════════════════════════════════
#  ПЛАВНЫЙ КОНТУР УДЕРЖАНИЯ
# ═══════════════════════════════════════════════════════════════════════════
#
# Стенд hold_aruco отрабатывал промах чистым пропорциональным контуром с большим
# коэффициентом: увидел 20 см — полетел на 14 см. На перелётах это правильно, а на
# долгом зависании даёт качку, потому что складываются три вещи: шум опознания метки
# (несколько сантиметров от кадра к кадру), запаздывание (команда исполняется уже
# после того, как кадр устарел) и перелёт цели.
#
# Здесь всё три лечатся сразу и по отдельности:
#   * шум — сглаживанием замера (--smooth): дрон отрабатывает тенденцию, а не дрожь;
#   * перелёт — демпфированием (--damp): к промаху добавляется член по скорости его
#     изменения, и быстро сокращающийся промах отрабатывается слабее;
#   * дёрганье по мелочи — мёртвой зоной ПО ПРОМАХУ (--hold-tol).
# Плюс своя, медленная скорость доводки.
#
# Мёртвая зона считается именно по промаху, а не по длине команды (так было до
# 29.07.2026, и это оказалось главной причиной «висит рядом, а не над меткой»):
# команда короче --min-hop не отправлялась, а команда есть доля --gain от промаха,
# поэтому дрон переставал править всё, что меньше min_hop/gain — при 0,04 и 0,35 это
# 11 см, которые контур не видел принципиально. Теперь --min-hop это только «не
# дёргать борт микрокомандой», а докуда доводить, задаёт --hold-tol.
#
# Класс намеренно ничего не знает ни про дрон, ни про ROS: только числа и время. Так
# его можно проверить тестами до полёта — на живом борте это проверяется дорого.


class Holder:
    """Из промаха до метки делает команду, которую не стыдно отдать дрону."""

    def __init__(self, gain: float, damp: float, smooth: float, min_hop: float,
                 max_hop: float, alt_dead: float, alt_fix: float,
                 yaw_dead: float, yaw_step: float, tol: float = 0.05) -> None:
        self.gain = gain            # какую долю промаха отрабатывать
        self.damp = damp            # вес скорости изменения промаха, с
        self.smooth = min(max(smooth, 0.05), 1.0)  # 1.0 — сглаживания нет вовсе
        self.tol = tol              # промах меньше этого считаем нулевым, м
        self.min_hop = min_hop      # короче этой команду дотягиваем: меньше не доедет, м
        self.max_hop = max_hop      # длиннее этой урезается, м
        self.alt_dead = alt_dead    # уход высоты меньше этого не трогаем, м
        self.alt_fix = alt_fix      # предел поправки высоты за команду, м
        self.yaw_dead = yaw_dead    # увод меньше этого не трогаем, град
        self.yaw_step = yaw_step    # предел доворота за команду, град
        self.reset()

    def reset(self) -> None:
        """Забыть сглаженное: новый взлёт начинает контур с чистого листа."""
        self.fwd: float | None = None    # сглаженный промах вперёд, м
        self.left: float | None = None
        self.up: float | None = None     # сглаженная нехватка высоты, м
        self.rate_fwd = 0.0              # скорость изменения промаха, м/с
        self.rate_left = 0.0
        self.at = 0.0                    # время последнего замера

    def _blend(self, old: float | None, raw: float) -> float:
        return raw if old is None else old + self.smooth * (raw - old)

    def command(self, forward: float, left: float, alt_error: float,
                yaw_error: float | None, now: float, up_room: float | None = None):
        """Сгладить замер и выдать (вперёд, влево, вверх, доворот) — или None.

        None означает «команду отдавать не надо»: всё в мёртвых зонах, дрон и так
        стоит где нужно. Это не то же самое, что нули: нулевую команду navigate
        отправлять незачем, она только занимает борт.

        up_room — сколько ещё разрешено подняться, м; выше этого поправка вверх не
        уйдёт, сколько бы ни показал замер. Это последняя защита от потолка, и она
        не заменяет проверку в hold_tick, а страхует её: ошибиться в замере высоты
        дрон может, а пробить потолок — нет (регламент 2.6.3).

        Поправка высоты ограничена alt_fix В ОБЕ СТОРОНЫ. До 30.07.2026 набор после
        взлёта шёл здесь же и без предела (alt_limit), и это было вторым слагаемым
        ухода в потолок: вверх дрон отдавал весь мнимый недобор разом, а возвращался
        ступеньками по 25 см с паузой на каждую. Теперь набор целиком в _takeoff —
        контуру остаётся только править уже набранное.
        """
        dt = now - self.at if self.at else 0.0
        smooth_fwd = self._blend(self.fwd, forward)
        smooth_left = self._blend(self.left, left)
        smooth_up = self._blend(self.up, alt_error)
        # Скорость изменения промаха считаем только по разумному промежутку: после
        # долгой паузы (потеряли метку, снимали кадр) разность даёт выброс, и
        # демпфирование по нему толкнуло бы дрон вместо того, чтобы придержать.
        # Порог 4 с, а не 2: между соседними замерами теперь стоит пауза на успокоение
        # (--settle плюс время самой поправки), и при 2 с демпфирование молча
        # выключалось бы ровно на рабочем цикле контура.
        if self.fwd is not None and 0.0 < dt <= 4.0:
            self.rate_fwd = (smooth_fwd - self.fwd) / dt
            self.rate_left = (smooth_left - self.left) / dt
        else:
            self.rate_fwd = self.rate_left = 0.0
        self.fwd, self.left, self.up, self.at = smooth_fwd, smooth_left, smooth_up, now

        # Мёртвая зона — по промаху, а не по длине команды: иначе она умножалась бы
        # на 1/gain и дрон бросал бы доводку, не дойдя до метки (см. врезку выше).
        go_fwd = go_left = hop = 0.0
        if math.hypot(smooth_fwd, smooth_left) >= self.tol:
            # Пропорциональная часть плюс демпфирующая: промах, который и так быстро
            # сокращается, отрабатывается слабее — именно это гасит раскачку.
            go_fwd = self.gain * smooth_fwd + self.damp * self.rate_fwd
            go_left = self.gain * smooth_left + self.damp * self.rate_left
            hop = math.hypot(go_fwd, go_left)
            # Промах вне допуска — значит двигаться НАДО, и короткая команда здесь не
            # повод не двигаться, а повод дотянуть её до min_hop: иначе слабый --gain
            # снова превращался бы в мёртвую зону шириной min_hop/gain. Ровный ноль не
            # трогаем: его дало демпфирование, то есть промах и так уже сокращается.
            limit = min(max(hop, self.min_hop), self.max_hop)
            if hop > 0.0 and limit != hop:
                go_fwd, go_left = go_fwd * limit / hop, go_left * limit / hop
                hop = limit

        go_up = 0.0
        if abs(smooth_up) >= self.alt_dead:
            go_up = max(-self.alt_fix, min(self.alt_fix, smooth_up))
            if up_room is not None and go_up > 0.0:
                go_up = min(go_up, max(0.0, up_room))

        turn = 0.0 if yaw_error is None else yaw_fix(yaw_error, self.yaw_dead, self.yaw_step)

        if not hop and not go_up and not turn:
            return None
        return go_fwd, go_left, go_up, turn


# ═══════════════════════════════════════════════════════════════════════════
#  ЗРЕНИЕ: «огонёк» и его клетка
# ═══════════════════════════════════════════════════════════════════════════
#
# Пожар на нашем поле обозначен физическими «огоньками» без числа, и степень пожара
# задаётся тем, СКОЛЬКО жетонов лежит рядом: три огонька кучкой = три поездки за
# водой. Поэтому ищется и клетка очага, и число жетонов в кучке.
#
# Логика та же, что в city/vision.py (она проверена на фотографиях photo_fire/), но
# привязка кадра к полю здесь ТОЧНЕЕ: борт знает, над какой меткой он висит, поэтому
# масштаб и поворот берутся из настоящего маркера 25 см, а не из угла обзора.


class Anchor:
    """Перевод «пиксель кадра -> метры поля».

    Камера смотрит вниз, поэтому кадр — зеркальный поворот плоскости поля: правый край
    кадра идёт вдоль +X, а низ кадра — против +Y. Формула та же, что в city/vision.py,
    чтобы клетка, посчитанная на борту и на ноутбуке, совпадала.
    """

    __slots__ = ("u0", "v0", "x0", "y0", "mpp", "phi", "source", "marker_id")

    def __init__(self, u0, v0, x0, y0, mpp, phi, source, marker_id=None) -> None:
        self.u0, self.v0 = float(u0), float(v0)
        self.x0, self.y0 = float(x0), float(y0)
        self.mpp = float(mpp)          # метров на пиксель
        self.phi = float(phi)          # поворот кадра относительно поля, рад
        self.source = source           # marker | pose
        self.marker_id = marker_id

    def to_map(self, u: float, v: float) -> tuple[float, float]:
        du, dv = u - self.u0, v - self.v0
        cos_f, sin_f = math.cos(self.phi), math.sin(self.phi)
        return (
            self.x0 + self.mpp * (du * cos_f + dv * sin_f),
            self.y0 + self.mpp * (du * sin_f - dv * cos_f),
        )


class Blob:
    """Пятно цвета огня в кадре и то же пятно в метрах поля."""

    __slots__ = ("u", "v", "x", "y", "area", "share")

    def __init__(self, u, v, area, share) -> None:
        self.u, self.v = float(u), float(v)
        self.area, self.share = float(area), float(share)
        self.x = self.y = 0.0


def find_fires(frame, hsv_ranges=FIRE_HSV, min_area: float = 80.0,
               max_share: float = 0.15) -> list[Blob]:
    """Все пятна цвета огня, крупные первыми.

    Пятен несколько не случайно: степень пожара задана числом жетонов, лежащих рядом,
    поэтому здесь ничего не схлопывается — кто из пятен образует одну кучку, решается
    уже в метрах поля.

    Верхний порог площади не декоративный: по углам поля лежат ЦВЕТНЫЕ РАЙОНЫ, и
    красноватый район в кадре — огромное пятно почти нужного цвета. «Огонёк» — предмет
    размером со спичечный коробок, поэтому пятно во весь кадр отбрасывается.
    """
    import cv2
    import numpy as np

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = None
    for low, high in hsv_ranges:
        part = cv2.inRange(hsv, np.array(low, np.uint8), np.array(high, np.uint8))
        mask = part if mask is None else cv2.bitwise_or(mask, part)
    if mask is None:
        return []
    # Ядро 3x3, а не 5x5: с рабочей высоты жетон занимает десятки пикселей, и более
    # крупное ядро съедало его целиком. Сначала убираем крапинки, потом сращиваем
    # язычки пламени — фигурка узкая, и без этого она распадается на несколько пятен.
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    found = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = found[0] if len(found) == 2 else found[1]  # OpenCV 3 отдавала три значения
    frame_area = float(frame.shape[0] * frame.shape[1])
    blobs: list[Blob] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        share = area / frame_area if frame_area else 0.0
        if area < min_area or share > max_share:
            continue
        moments = cv2.moments(contour)
        if moments["m00"] <= 0:
            continue
        blobs.append(
            Blob(moments["m10"] / moments["m00"], moments["m01"] / moments["m00"], area, share)
        )
    return sorted(blobs, key=lambda b: b.area, reverse=True)


def token_px(mpp: float, token_m: float, token_fill: float) -> float:
    """Сколько пикселей занимает ОДИН жетон при таком масштабе кадра.

    Нужно ровно для одного случая: жетоны слиплись в единое пятно, и разделить их по
    контурам нельзя. Тогда единственная опора — известный размер жетона (4,5 см) и
    доля своего квадрата, которую занимает его силуэт (0,47 — замерено по photo_fire/).
    """
    if mpp <= 0:
        return 0.0
    side = token_m / mpp
    return side * side * token_fill


def clusters(blobs, group_m: float) -> list[list[Blob]]:
    """Разбить пятна на кучки: ближе group_m хотя бы к одному соседу — одна кучка.

    Связность по соседу, а не по центру кучки: три жетона в ряд образуют одну кучку,
    даже если крайние друг от друга дальше порога. Пятен единицы, поэтому наивного
    перебора хватает с запасом.
    """
    groups: list[list[Blob]] = []
    for blob in blobs:
        merged = [blob]
        rest: list[list[Blob]] = []
        for group in groups:
            if any(math.hypot(blob.x - o.x, blob.y - o.y) <= group_m for o in group):
                merged.extend(group)
            else:
                rest.append(group)
        rest.append(merged)
        groups = rest
    return groups


def count_tokens(blobs, unit_px: float, split_ratio: float) -> tuple[int, str]:
    """Сколько жетонов в кучке и по чему это посчитано.

    Основной счёт — по числу пятен: жетоны с зазором дают каждый своё пятно, и это
    точно. Поправка — по площади: слипшиеся жетоны дают одно пятно, зато кратное по
    размеру одиночному. Эталон одиночного берётся, если можно, из самой кучки
    (наименьшее пятно), и только для кучки из одного пятна — из размера жетона и
    масштаба кадра: свой же жетон в кадре — мерка честнее любой расчётной.
    """
    if not blobs:
        return 0, "blobs"
    unit = min(b.area for b in blobs) if len(blobs) >= 2 else unit_px
    if unit <= 0:
        unit = unit_px
    total, split = 0, 0
    for blob in blobs:
        n = 1
        if unit > 0 and blob.area >= split_ratio * unit:
            n = max(1, int(round(blob.area / unit)))
        total += n
        if n > 1:
            split += 1
    if not split:
        return total, "blobs"
    return total, "area" if len(blobs) == 1 else "mixed"


def group_center(blobs) -> tuple[float, float, float, float, float]:
    """Кучка одним ответом: (x, y, площадь, доля кадра, размах) — центр взвешен площадью."""
    area = sum(b.area for b in blobs)
    weight = area if area > 0 else float(len(blobs))
    if area > 0:
        x = sum(b.x * b.area for b in blobs) / weight
        y = sum(b.y * b.area for b in blobs) / weight
    else:
        x = sum(b.x for b in blobs) / weight
        y = sum(b.y for b in blobs) / weight
    spread = max((math.hypot(a.x - b.x, a.y - b.y) for a in blobs for b in blobs), default=0.0)
    return x, y, area, sum(b.share for b in blobs), spread


def clipped(blobs, shape, margin_px: float) -> bool:
    """Кучка подошла к краю кадра — часть жетонов могла в него не попасть.

    Такой кадр годится, чтобы сказать ГДЕ горит, но плох, чтобы сказать СКОЛЬКО.
    """
    height, width = float(shape[0]), float(shape[1])
    return any(
        b.u < margin_px or b.u > width - margin_px or b.v < margin_px or b.v > height - margin_px
        for b in blobs
    )


# ═══════════════════════════════════════════════════════════════════════════
#  БОРТ
# ═══════════════════════════════════════════════════════════════════════════


class Job:
    """Одна исполняемая команда: её номер и флаг «тебя сменили».

    Нужен, потому что аварийная посадка вытесняет незаконченный взлёт, а тот в этот
    момент досыпает паузу. Без номера проснувшийся взлёт дописал бы в статус «вишу»
    уже после команды на посадку — и оператор увидел бы в пульте летящий дрон вместо
    садящегося.
    """

    def __init__(self, seq: int, name: str) -> None:
        self.seq = seq
        self.name = name
        self.cancel = threading.Event()


class Agent:
    """Состояние борта и все обращения к железу. Команды исполняются по одной."""

    role = "drone"

    def __init__(self, args) -> None:
        self.args = args
        self.name = args.name
        self.cell = [int(v) for v in args.cell.split(",")]
        self.pad = list(self.cell)
        self.xy = self.cell_to_m(self.cell)
        self.alt = 0.0                  # высота, на которой дрон ДОЛЖЕН висеть
        # idle | taking_off | climbing | hover | landing | landed | landed_unverified
        # | land_failed | error
        self.state = "idle"
        self.last_error = ""
        self.frames = 0
        self.dry = args.dry
        self.camera_ok = False
        self.drone = None
        self._lock = threading.Lock()
        self._busy = False
        self.current = ""
        self._job: Job | None = None
        self._seq = 0
        self._done: dict[str, dict] = {}  # command_id -> уже выданный ответ
        self._done_lock = threading.Lock()
        self._hw_lock = threading.Lock()
        self._last_move = time.monotonic()
        self._last_request = time.monotonic()

        # Своя метка: за неё, и только за неё, держится контур.
        self.marker = (
            int(args.marker) if args.marker is not None
            else PAD_MARKER.get((self.pad[0], self.pad[1]), -1)
        )
        # Курс: эталон снимается по метке первым же кадром после взлёта.
        self._yaw_ref: float | None = None
        self._yaw_drift: float | None = None
        self._yaw_warned = False
        # Что контур видел в последний раз — уходит в /status, чтобы оператор понимал,
        # держится дрон за метку или уже потерял её.
        self.alt_seen: float | None = None   # высота по стороне метки, м
        self.miss: float | None = None       # промах до центра метки, м
        self.side_seen: float | None = None  # сторона метки, пиксели (для калибровки)
        self.blind = 0                       # кадров подряд без своей метки
        self.marker_lost = False
        # Эталон высоты: сторона своей метки на рабочей высоте, пиксели. Снимается
        # после набора и живёт один полёт — вся высота считается от него (alt_by_ref).
        self.side_ref: float | None = None
        # Сколько метров осталось набрать до рабочей высоты. Пока больше нуля, борт
        # НЕ мерит высоту по метке и не снимает эталон: он ещё едет вверх, и кадр
        # показывает высоту, которая уже отрабатывается (разбор — в шапке файла).
        self._climb_left = 0.0
        self._ref_prev: float | None = None  # сторона на прошлом такте: эталон по двум
        self._ref_tries = 0                  # тактов потрачено на согласие двух кадров
        # Поиск потерянной метки: где сейчас стоим относительно точки потери и какой
        # отход пробуем следующим.
        self._search_off = (0.0, 0.0)
        self._search_leg = 0
        # На сколько метров дрон уже выше рабочей высоты. Пока метка видна — это
        # ИЗМЕРЕННОЕ превышение, вслепую — счисленное по своим же командам подъёма.
        # Жёсткий предел: вверх дрон уходит от площадки к потолку, и без счёта поиск
        # выдавил бы его туда ступеньками (перенесено со стенда: BLIND_UP/grounded).
        self._blind_up = 0.0
        self.holder = Holder(
            gain=args.gain, damp=args.damp, smooth=args.smooth, tol=args.hold_tol,
            min_hop=args.min_hop, max_hop=args.max_hop,
            alt_dead=args.alt_dead, alt_fix=args.alt_fix,
            yaw_dead=args.yaw_dead, yaw_step=args.yaw_fix,
        )
        # До этого момента замерять бесполезно: дрон ещё едет по прошлой команде и
        # висит с креном, а кадр наклонённой камеры показывает промах, которого нет.
        self._settle_until = 0.0
        self.focal = float(args.focal_px) if args.focal_px else 0.0
        self.last_fire: dict | None = None   # последний ответ про огонь

    # --- железо -------------------------------------------------------------

    def open(self) -> None:
        if self.dry:
            say("режим --dry: железо не трогаем, отвечаем как дрон и ничего не делаем")
            return
        import sverk_interfaces

        say("подключаюсь к дрону…")
        self.drone = sverk_interfaces.init(Nodename=f"agent_{self.name}")
        self.camera_ok = patch_yuv(self.drone, self.args.color)
        say(
            f"дрон на связи, камера {'готова' if self.camera_ok else 'НЕ ГОТОВА'}"
            f" (цвет: {self.args.color})"
        )

    def close(self) -> None:
        if self.drone is not None:
            try:
                self.drone.close()
            except Exception as exc:  # noqa: BLE001 — на выходе глушим всё
                say(f"закрытие: {exc}")

    # --- отчёт о состоянии --------------------------------------------------

    def status(self) -> dict:
        st = {
            "ok": True,
            "role": self.role,
            "name": self.name,
            "state": self.state,
            "cell": self.cell,
            "xy": [round(v, 2) for v in self.xy],
            "alt": round(self.alt, 2),
            "since_move": round(time.monotonic() - self._last_move, 2),
            "busy": self._busy,
            "camera": self.camera_ok,
            "version": VERSION,
        }
        if self.dry:
            st["dry"] = True  # честно: на том конце заглушка, а не аппарат
        if self.climbing:
            # Сколько ещё набирать. Поле есть только на наборе, и по нему видно, что
            # alt в статусе — это ЦЕЛЬ, а сам дрон пока ниже неё на столько метров.
            st["climb_left"] = round(self._climb_left, 2)
        if self.last_error:
            st["last_error"] = self.last_error
        if self.hold_on:
            # Что борт думает про своё зависание. alt_seen = null означает «метку не
            # вижу, высоту проверить нечем», а не «высота ноль».
            st["marker"] = self.marker
            st["alt_seen"] = None if self.alt_seen is None else round(self.alt_seen, 2)
            # Эталон высоты: по нему считается alt_seen, и по нему же оператор судит,
            # на какой высоте дрон закрепился. null — эталона ещё нет, высоту не правим.
            st["side_ref"] = None if self.side_ref is None else round(self.side_ref)
            st["miss"] = None if self.miss is None else round(self.miss, 2)
            # Куда сдвинута точка прицеливания. Промах в кадре может быть нулевым, а
            # дрон при этом висеть мимо метки — разницу видно только отсюда.
            st["aim"] = [round(self.args.cam_fwd, 3), round(self.args.cam_left, 3)]
            st["side_px"] = None if self.side_seen is None else round(self.side_seen)
            st["blind"] = self.blind
            if time.monotonic() < self._settle_until:
                # Не «завис», а честно ждёт, пока доедет поправка: без этого поля
                # оператор видел бы замерший miss и думал, что контур встал.
                st["settling"] = True
            # На сколько дрон выше рабочей высоты: пока метку видно — замер, вслепую —
            # счисление по своим командам подъёма. По нему видно, ищет поиск ещё вверх
            # или уже упёрся в предел и шарит только вширь.
            st["above"] = round(self._blind_up, 2)
            if self.marker_lost:
                st["marker_lost"] = True
        if self.yaw_hold:
            # Градусы, а не радианы: это читает человек в пульте. yaw_ref = null
            # означает «курс держать не по чему», а не «курс ноль».
            st["yaw_ref"] = None if self._yaw_ref is None else round(math.degrees(self._yaw_ref))
            st["yaw_drift"] = (
                None if self._yaw_drift is None else round(math.degrees(self._yaw_drift))
            )
        if self.last_fire is not None:
            st["fire"] = self.last_fire
        if self.args.telemetry and self.drone is not None:
            tel, err = self._telemetry()
            if tel is None:
                st["telemetry_error"] = err
            else:
                st["telemetry"] = {k: getattr(tel, k, None) for k in ("x", "y", "z", "armed", "mode")}
        return st

    def _telemetry(self, frame_id: str = "body", timeout: float = 2.0):
        """Телеметрия со сроком: вернуть (данные, ошибка).

        В статусе по умолчанию выключена флагом --telemetry: на наших сборках вызов
        виснет без полётного контроллера. Поэтому даже включённая, она читается в
        отдельном потоке — зависший вызов не должен запирать ни /status, ни посадку.
        Поток останется висеть до конца работы агента; это дешевле, чем немой борт.
        """
        box: dict = {}

        def read():
            try:
                box["tel"] = self.drone.control.get_telemetry(frame_id=frame_id)
            except Exception as exc:  # noqa: BLE001 — любой отказ здесь это «нет данных»
                box["err"] = str(exc)

        worker = threading.Thread(target=read, daemon=True)
        worker.start()
        worker.join(timeout)
        if "tel" in box:
            return box["tel"], ""
        if "err" in box:
            return None, box["err"]
        return None, f"телеметрия не ответила за {timeout:g} с"

    # --- поле ---------------------------------------------------------------

    def cell_to_m(self, cell) -> tuple[float, float]:
        """Клетка поля -> метры от центра поля.

        Начало координат — центр квадрата из четырёх маркеров, он же центр поля
        (docs/field-map/README.md). Поэтому центр клетки [col,row] на поле 6x6 по
        0,8 м это ((col-2.5)*0.8, (row-2.5)*0.8).
        """
        cols, rows = (int(v) for v in self.args.grid.split(","))
        size = self.args.cell_size
        return ((cell[0] - (cols - 1) / 2.0) * size, (cell[1] - (rows - 1) / 2.0) * size)

    def m_to_cell(self, x: float, y: float) -> tuple[int, int]:
        """Метры от центра поля -> клетка. Обратное к cell_to_m, тем же округлением."""
        cols, rows = (int(v) for v in self.args.grid.split(","))
        size = self.args.cell_size
        return (
            int(round(x / size + (cols - 1) / 2.0)),
            int(round(y / size + (rows - 1) / 2.0)),
        )

    def in_field(self, cell) -> bool:
        cols, rows = (int(v) for v in self.args.grid.split(","))
        return 0 <= cell[0] < cols and 0 <= cell[1] < rows

    # --- курс ---------------------------------------------------------------

    @property
    def yaw_hold(self) -> bool:
        """Держим ли курс по метке. Выключается --no-yaw-hold."""
        return not self.args.no_yaw_hold

    def _yaw_error(self, fix: Fix) -> float | None:
        """Увод от курса взлёта по этому замеру метки, радианы. None — замер негоден."""
        if not self.yaw_hold or self._yaw_ref is None:
            return None
        error = turn_error(fix.angle, self._yaw_ref, self.args.yaw_max)
        if error is None:
            if not self._yaw_warned:
                say(f"курс: поворот метки больше {self.args.yaw_max:g}° — дрон так не "
                    f"отворачивает. Похоже, сбой опознания метки; курс не правлю")
                self._yaw_warned = True
            return None
        self._yaw_drift = error
        return error

    # --- удержание над меткой -----------------------------------------------

    @property
    def hold_on(self) -> bool:
        """Работает ли контур удержания. Выключается --no-hold и режимом --dry."""
        return not self.args.no_hold and not self.dry

    @property
    def climbing(self) -> bool:
        """Идёт ли ещё набор остатка высоты после слепой ступени взлёта.

        Пока идёт, высота по метке не мерится вовсе (эталон снимать не с чего: дрон
        едет вверх), а горизонталь и курс правятся как обычно.
        """
        return self._climb_left > 1e-6

    @property
    def climb_room(self) -> float:
        """Сколько метров вверх от рабочей высоты ещё разрешает потолок, м.

        --max-alt отсчитывается от площадки, а не от пола, поэтому запас честно
        меряется от --alt. Через этот предел не пускается ничто: ни поиск метки, ни
        контур удержания. Даже если замер высоты совсем разъедется, выше дрон не
        уйдёт — до 30.07.2026 такой проверки не было вовсе, и это была главная
        причина «улетает до крыши».
        """
        return max(0.0, self.args.max_alt - self.alt)

    @property
    def search_room(self) -> float:
        """Насколько выше рабочей высоты разрешено подниматься в поиске метки, м.

        Свой предел (--search-rise на --search-rise-max подъёмов) и потолок; берётся
        меньший. Потолок отдельно, потому что просевший дрон контур обязан поднимать
        и при выключенном поиске.
        """
        own = max(0.0, self.args.search_rise) * max(0, self.args.search_rise_max)
        return min(own, self.climb_room)

    def height(self, side: float) -> float | None:
        """Высота над плоскостью метки по её стороне, м. None — посчитать нечем.

        Пока в полёте снят эталон, это он: он не зависит ни от настоящего размера
        маркера, ни от угла обзора камеры (разбор — у alt_by_ref). Эталона нет (дрон
        на земле, зрение огня смотрит чужой кадр) — остаётся абсолютная оценка через
        --fov-deg, и тогда высота настолько верна, насколько верна калибровка.
        """
        if self.side_ref is not None:
            return alt_by_ref(side, self.side_ref, self.alt)
        return alt_by_side(side, self.focal or focal_px(1280.0, self.args.fov_deg))

    def _take_ref(self, side: float) -> None:
        """Снять эталон высоты — сторону своей метки на рабочей высоте, пиксели.

        Берётся не первый попавшийся кадр, а два подряд согласных: сразу после набора
        дрон ещё качает, а эталон, снятый на раскачке, испортит высоту на весь полёт —
        она вся считается от него. Согласие проверяется по «дыханию» размера метки
        (--ref-calm, доля стороны), ровно как на стенде (hold_aruco: settle).

        Если согласия нет --ref-tries тактов подряд, эталон берётся как есть: висеть
        вовсе без удержания высоты хуже, чем держать её по неидеальному замеру. Про
        такой случай пишем в лог — а что вышло, видно по side_ref в /status.
        """
        previous, self._ref_prev = self._ref_prev, side
        self._ref_tries += 1
        calm = previous is not None and abs(side - previous) <= self.args.ref_calm * side
        if not calm and self._ref_tries < self.args.ref_tries:
            return
        self.side_ref = (side + previous) / 2.0 if calm else side
        say(f"высота: эталон {self.side_ref:.0f} px = рабочие {self.alt:.2f} м "
            f"(метка {self.marker}{'' if calm else ', успокоиться не вышло'})")

    def _frame(self, what: str):
        """Кадр с камеры через общую очередь к железу. None — кадра нет.

        Два потока на одном ROS-узле рвут wait set, поэтому кадр берётся тем же путём,
        что и /shot. Любой отказ здесь — не ошибка: не увидели, значит на этот раз не
        правим.
        """
        if self.dry or self.drone is None or not self.camera_ok:
            return None
        try:
            frame = self._hw(
                what, lambda: self.drone.image.take_picture(timeout=2.0), timeout=5.0
            )
        except Busy:
            return None
        except Exception as exc:  # noqa: BLE001
            say(f"{what}: кадр не получен ({exc})")
            return None
        if frame is None or getattr(frame, "ndim", 0) != 3 or frame.size == 0:
            return None
        return frame

    def hold_keeper(self) -> None:
        """Крутить такт удержания, пока дрон висит.

        Такт: кадр → своя метка → промах, высота, курс → одна команда navigate. Темп
        задаётся --hold-period: чаще смысла нет (кадр и команда сами занимают время),
        реже — дрон успевает уйти между тактами.
        """
        period = self.args.hold_period
        if period <= 0 or self.dry:
            return
        while True:
            time.sleep(period)
            try:
                self.hold_tick()
            except Exception as exc:  # noqa: BLE001 — контур не должен ронять борт
                say(f"удержание: такт сорвался ({exc})")

    def hold_tick(self) -> str:
        """Один такт удержания. Возвращает, чем такт кончился (это же читают тесты).

        Отдельным методом, потому что весь смысл — в решении «куда и насколько
        двинуться», а проверять его на живом борте дорого.

        Такт идёт циклом «замерил → сдвинулся → дал успокоиться → замерил снова», и
        средний шаг здесь не для красоты (переделано 29.07.2026 — дрон висел рядом с
        меткой, а не над ней). navigate не блокирующий: он лишь ставит цель, и дрон
        едет к ней ещё секунду после ответа. Пока он едет, кадр врёт дважды —
        показывает промах, который уже отрабатывается, и вдобавок снят наклонённой
        камерой (крен на разгоне 5° это 17 см мнимого промаха с высоты 2 м). Прежняя
        версия мерила каждые полсекунды и на каждый такой кадр досылала новую цель
        поверх недоехавшей: цели складывались, дрон проскакивал метку и раскачивался.
        Поэтому после команды такт молчит, пока она не доедет (--settle).

        Команда идёт МИМО очереди start(): это не команда борта, а короткое обращение
        к железу. Через start() такт получал бы «занят» ровно тогда, когда дрон висит
        и его надо держать, а с вытеснением отменял бы чужую команду.

        На состоянии climbing такт работает так же, с одной разницей: высота не
        мерится по метке, а НАБИРАЕТСЯ шагами по --climb-step из остатка, который борт
        считает по своим же командам (разбор — в шапке файла). Горизонталь и курс при
        этом правятся с первого же кадра, где метка видна.
        """
        if not self.hold_on or self.state not in ("hover", "climbing"):
            return "idle"
        if self._busy:
            return "busy"       # идёт посадка или взлёт: под ноги не лезем
        if time.monotonic() < self._settle_until:
            return "settling"   # прошлая поправка ещё едет: мерить нечего

        frame = self._frame("удержание")
        if frame is None:
            return "no-frame"
        seen = markers(frame)
        fix = seen.get(self.marker)
        if fix is None:
            self.blind += 1
            if self.blind == 1 or self.blind % 10 == 0:
                others = " ".join(str(i) for i in sorted(seen)) or "нет"
                say(f"удержание: своей метки {self.marker} не видно "
                    f"{self.blind} кадров подряд (в кадре: {others})")
            if self.blind < self.args.blind_max:
                return "blind"
            if not self.marker_lost:
                self.marker_lost = True
                say(f"МЕТКУ {self.marker} ПОТЕРЯЛ: начинаю искать")
            return self._search()
        if self.blind:
            say(f"удержание: метка {self.marker} снова в кадре")
        self.blind, self.marker_lost = 0, False
        self._search_off, self._search_leg = (0.0, 0.0), 0

        if self.focal <= 0.0:
            self.focal = focal_px(frame.shape[1], self.args.fov_deg)
        if self._yaw_ref is None and self.yaw_hold:
            # Эталон курса снимается ПЕРВЫМ ЖЕ кадром со своей меткой, а не после
            # паузы на успокоение: ждать нечего, замер всё равно сглаживается.
            self._yaw_ref, self._yaw_drift = fix.angle, 0.0
            say(f"курс: эталон {math.degrees(fix.angle):+.0f}° (по метке {self.marker})")

        height, width = frame.shape[:2]
        forward, left = aim(fix, width, height, self.args.cam_fwd, self.args.cam_left,
                            self.args.sign_fwd, self.args.sign_left)
        self.miss = math.hypot(forward, left)
        self.side_seen = fix.side
        climbing = self.climbing
        # Эталон снимается только с дрона, который уже никуда не едет: снятый на
        # наборе, он закрепил бы промежуточную высоту как рабочую на весь полёт.
        if self.side_ref is None and not climbing:
            self._take_ref(fix.side)
        self.alt_seen = (
            None if self.side_ref is None
            else alt_by_ref(fix.side, self.side_ref, self.alt)
        )
        # Эталона ещё нет — высоту проверить нечем, и это НЕ повод её править: нулевой
        # промах по высоте честнее выдуманного. Горизонталь и курс работают и так,
        # им эталон не нужен.
        alt_error = 0.0 if self.alt_seen is None else self.alt - self.alt_seen

        # Пока метку видно, превышение над рабочей высотой — измеренное, а не
        # счисленное. Обнулять его по одному факту «метка нашлась» нельзя: дрон в этот
        # момент ещё наверху, и вниз контур идёт по alt_fix за такт. Метка пропала
        # снова — и поиску был бы доступен новый полный подъём, так высота росла бы
        # ступеньками мимо предела (стенд: grounded).
        if self.alt_seen is not None:
            self._blind_up = max(0.0, self.alt_seen - self.alt)
        command = self.holder.command(
            forward, left, alt_error, self._yaw_error(fix), time.monotonic(),
            up_room=self.climb_room - self._blind_up,
        )
        # Шаг набора идёт МИМО Holder: тот правит уже набранную высоту по замеру, а
        # здесь высота не мерится вовсе — она добирается по счёту. Из-за этого шаг и
        # не гасится ни мёртвой зоной, ни сглаживанием: гасить нечего, промаха нет.
        step = min(self._climb_left, max(0.01, self.args.climb_step)) if climbing else 0.0
        if command is None and not step:
            return "hold"
        go_fwd, go_left, go_up, turn = command or (0.0, 0.0, 0.0, 0.0)
        if climbing:
            go_up = step
        seen_alt = "?" if self.alt_seen is None else f"{self.alt_seen:.2f}"
        # Промах пишется и по осям: постоянный остаток в одну сторону — это плечо
        # камеры (--cam-fwd/--cam-left), а не «дрон плохо держит», и по логу видно, по
        # какой оси его подкручивать.
        tail = "" if not climbing else f", добрать ещё {self._climb_left:.2f} м"
        say(f"{'НАБОР' if climbing else 'удержание'}: метка {self.marker}, "
            f"промах {self.miss:4.2f} м "
            f"(вперёд {forward:+5.2f} влево {left:+5.2f}), "
            f"h≈{seen_alt}/{self.alt:.2f} м ({fix.side:.0f} px) → "
            f"вперёд {go_fwd:+5.2f} влево {go_left:+5.2f} вверх {go_up:+5.2f} "
            f"доворот {math.degrees(turn):+.0f}°{tail}")
        outcome = self._push(go_fwd, go_left, go_up, turn, climb=climbing)
        if climbing and outcome == "moved":
            self._climbed(go_up)
        return outcome

    def _climbed(self, up: float) -> None:
        """Записать набранные метры и, если набор кончился, объявить дрон висящим.

        Остаток считается по СКОМАНДОВАННОМУ, а не по замеру: замер на наборе врёт
        (разбор — в шапке файла). Промах команды из-за этого закрепится как рабочая
        высота, ровно как промах взлёта закреплялся раньше, — видно это по side_ref в
        /status и лечится ключом --alt.
        """
        self._climb_left = max(0.0, self._climb_left - max(0.0, up))
        if self.climbing or self.state != "climbing":
            return
        self.state = "hover"
        self._last_move = time.monotonic()
        say(f"набор {self.alt:.2f} м закончен: беру эталон высоты по метке {self.marker}")

    def _search(self) -> str:
        """Один шаг поиска потерянной метки: подъём и короткие отходы во все стороны.

        Пока метки нет в кадре, править положение не по чему, а стоять на месте
        бессмысленно: если дрон снесло за край поля зрения, сам он туда не вернётся.
        Поэтому поиск делает ровно две вещи, обе дешёвые и обратимые.

        Подъём на --search-rise расширяет поле зрения: с 2 м камера видит на полу
        квадрат примерно 2,5 м, и каждые 10 см вверх добавляют к нему ~12 см. Считается
        он в МЕТРАХ превышения над рабочей высотой (search_room) — и это не мелочь.
        До 30.07.2026 стоял счётчик подъёмов, который обнулялся, стоило метке мелькнуть
        в кадре: дрон в этот момент ещё наверху (вниз контур идёт по alt_fix за такт),
        а поиску уже был доступен новый полный подъём — и высота росла ступеньками
        мимо любого предела. Теперь пока метку видно, превышение измеряется по ней же
        (см. hold_tick), а счисление работает только вслепую.

        Отход на --search-step обшаривает стороны по очереди, и после каждого отхода
        дрон возвращается в центр (разбор — у SEARCH_LEGS). Дальше 30 см от точки
        потери он не уходит вообще: метку сносит с кадра метрами, а не десятками
        метров, и широкий поиск скорее увёл бы дрон к соседней площадке.

        Курс здесь не трогаем совсем: разворот меняет вид метки в кадре и сбивает
        эталон, а помогает только когда метку потеряли из-за поворота, чего наш
        контур не допускает.
        """
        args = self.args
        if args.search_step <= 0.0:
            return "lost"       # поиск выключен: держимся на автопилоте, как раньше
        off_fwd, off_left = self._search_off
        up, rise = 0.0, False
        if off_fwd or off_left:
            go_fwd, go_left = -off_fwd, -off_left
            next_off, next_leg = (0.0, 0.0), self._search_leg
            where = "возвращаюсь в центр"
        else:
            leg = self._search_leg % len(SEARCH_LEGS)
            rise = leg == 0 and args.search_rise > 0.0 and (
                self._blind_up + args.search_rise <= self.search_room + 1e-6
            )
            if rise:
                up = args.search_rise
            d_fwd, d_left = SEARCH_LEGS[leg]
            go_fwd = d_fwd * args.search_step
            go_left = d_left * args.search_step
            next_off, next_leg = (go_fwd, go_left), self._search_leg + 1
            where = ("вперёд", "назад", "влево", "вправо")[leg]
        above = self._blind_up + up
        say(f"поиск метки {self.marker}: {where} "
            f"({go_fwd:+.2f}/{go_left:+.2f} м, вверх {up:+.2f} м, "
            f"набрано {above:.2f}/{self.search_room:.2f} м над рабочей высотой)")
        outcome = self._push(go_fwd, go_left, up, 0.0)
        if outcome != "moved":
            # Команда не ушла (борт занят, отказ) — шаг не считается: иначе поиск
            # «пропустил» бы сторону, а учёт отхода разошёлся бы с тем, где дрон
            # на самом деле висит, и возврат в центр увёл бы его мимо.
            return outcome
        self._search_off, self._search_leg = next_off, next_leg
        # Метку потеряли на наборе — подъём поиска идёт В СЧЁТ набора: дрон ещё НИЖЕ
        # рабочей высоты, и записать те же метры ещё и в превышение значило бы
        # посчитать их дважды, а потом добрать их же поверх.
        if up > 0.0 and self.climbing:
            used = min(up, self._climb_left)
            self._climbed(used)
            above -= used
        self._blind_up = max(0.0, above)
        return "search"

    def _push(self, forward: float, left: float, up: float, turn: float,
              climb: bool = False) -> str:
        """Отдать одну поправку. Скорость меньше полётной: доводка должна быть плавной.

        Шаг набора (climb=True) и насыщенная поправка высоты означают, что дрон ещё
        едет вверх, — тогда идём скоростью набора, а не медленной скоростью доводки.

        Здесь же взводится пауза до следующего замера: путь делится на скорость, плюс
        --settle на успокоение. Без неё контур мерил бы дрон в движении и с креном —
        разбор в hold_tick.
        """
        climbing = climb or abs(up) >= self.args.alt_fix - 1e-6
        speed = self.args.climb_speed if climbing else self.args.fix_speed
        try:
            resp = self._hw("удержание", lambda: self.drone.control.navigate(
                x=float(forward), y=float(left), z=float(up), yaw=float(turn),
                speed=speed, frame_id="body", auto_arm=True,
            ), timeout=self.args.hold_period)
        except Busy:
            return "occupied"           # борт занят кадром или командой: пропускаем такт
        except Exception as exc:  # noqa: BLE001 — отказ железа не должен ронять поток
            say(f"удержание: команда не прошла ({exc})")
            return "failed"
        if resp is not None and not getattr(resp, "success", True):
            say(f"удержание: команда не принята ({getattr(resp, 'message', '')})")
            return "refused"
        self._settle_until = time.monotonic() + self._travel(forward, left, up, speed)
        return "moved"

    def _travel(self, forward: float, left: float, up: float, speed: float) -> float:
        """Сколько ждать, пока поправка доедет и дрон успокоится, с.

        Путь берётся по самой длинной составляющей, а не по сумме: горизонталь и
        высота отрабатываются одновременно. Ноль скорости и отрицательный --settle
        отсекаются, иначе контур либо замирал бы навсегда, либо не ждал вовсе.
        """
        way = max(math.hypot(forward, left), abs(up))
        moving = way / speed if speed > 0 else 0.0
        return moving + max(0.0, self.args.settle)

    # --- команды ------------------------------------------------------------

    def once(self, command_id: str, run):
        """Исполнить команду один раз на command_id: повтор получает прежний ответ.

        Повтор приходит не от ошибки диспетчера, а от переотправки: ответ на POST
        теряется в Wi-Fi чаще, чем сама команда, и клиент шлёт её заново. Для взлёта
        это был бы второй navigate — то есть дрон, бесконечно начинающий заход
        заново. Отказ (занят, запрещено) не запоминается: это не выполненная работа,
        и повтор имеет право получить свежий отказ.
        """
        if not command_id:
            return run()
        with self._done_lock:  # дубль, пришедший впритык, ждёт здесь, а не летит
            if command_id in self._done:
                say(f"повтор команды {command_id[:8]} — второй раз не исполняю")
                return {**self._done[command_id], "deduplicated": True}
            result = run()
            self._done[command_id] = result
            while len(self._done) > DEDUP_KEEP:
                del self._done[next(iter(self._done))]
            return result

    def start(self, name: str, fn, *, preempt: bool = False) -> dict:
        """Принять команду и исполнять её в фоне: ответ по сети должен быть мгновенным.

        preempt=True — команда важнее текущей (аварийная посадка, сторож). Прежний
        исполнитель просыпается из паузы и уходит, ничего не записав: состояние
        пишет только тот, чей Job сейчас лежит в self._job.
        """
        with self._lock:
            if self._busy and not preempt:
                raise Busy(f"{self.name} занят: идёт «{self.current}»")
            if self._job is not None:
                self._job.cancel.set()
            self._seq += 1
            job = self._job = Job(self._seq, name)
            self._busy = True
            self.current = name
            was = self.state

        def worker():
            try:
                fn(job)
            except NavRefused as exc:
                # Команду не приняли — аппарат не двинулся. Возвращаем прежнее
                # состояние, чтобы следующая команда прошла проверки.
                if self._job is job:
                    self.state = was
                    self.last_error = f"{name}: {exc}"
                say(f"ОТКАЗ в «{name}»: {exc} (остаюсь как был: {was})")
            except Exception as exc:  # noqa: BLE001 — падать целиком борту нельзя
                if self._job is job:
                    self.state = "error"
                    self.last_error = f"{name}: {exc}"
                say(f"ОШИБКА в «{name}»: {exc}")
            finally:
                with self._lock:
                    if self._job is job:
                        self._busy = False
                        self._job = None

        threading.Thread(target=worker, daemon=True).start()
        return {"accepted": True, "command": name}

    def _hw(self, what: str, fn, timeout: float):
        """Обращаться к железу строго по одному потоку за раз.

        sverk_interfaces крутит spin общего узла прямо в вызывающем потоке
        (spin_until_future_complete в navigate, spin_once в take_picture), а два
        потока на одном узле рвут wait set: «wait set index for status
        subscription is out of bounds». Команда и запрос кадра приходят по сети
        независимо и попадают в разные потоки, так что очередь к железу нужна
        своя — библиотека её не держит.
        """
        if not self._hw_lock.acquire(timeout=timeout):
            raise Busy(f"{what}: борт {timeout:g} с занят другим обращением к железу")
        try:
            return fn()
        finally:
            self._hw_lock.release()

    def _set(self, job: Job, state: str | None = None, alt: float | None = None,
             moved: bool = False) -> bool:
        """Записать состояние, если эту команду не сменили. Иначе молча уйти."""
        if self._job is not job:
            return False
        if state is not None:
            self.state = state
        if alt is not None:
            self.alt = alt
        if moved:
            self._last_move = time.monotonic()
        return True

    @staticmethod
    def _wait(job: Job, seconds: float) -> bool:
        """Пауза, из которой можно разбудить. False — команду сменили, дальше не идём."""
        return not job.cancel.wait(seconds)

    def takeoff(self, alt: float) -> dict:
        if self.state in ALOFT:
            # Повторная команда взлёта намеренно не доходит до navigate: второй вызов
            # переинициализирует траекторию, и дрон зависает, начиная заход заново.
            return {
                "accepted": True,
                "command": "takeoff",
                "note": "взлёт уже идёт или дрон в воздухе",
            }
        return self.start("takeoff", lambda job: self._takeoff(alt, job))

    def _takeoff(self, alt: float, job: Job) -> None:
        """Слепая ступень взлёта, а остаток высоты добирает контур по метке.

        Одной командой уходит только --takeoff-blind метров, и держит дрон на них
        автопилот: с площадки метка либо не в кадре, либо занимает его целиком, так
        что цепляться на этой ступени всё равно не за что. Пауза здесь — путь этой
        ступени на скорость набора плюс успокоение и --lock-wait.

        Дальше борт переходит в climbing, и остаток набирает такт удержания: шагами по
        --climb-step, попутно правя положение и курс по метке. Высоту на этих шагах он
        НЕ мерит (разбор — в шапке файла и у _climbed): пока дрон едет вверх, кадр
        показывает высоту, которая уже отрабатывается, и контур, поверивший ему,
        досылал бы недобор поверх недоехавшей команды — набор складывался бы сам с
        собой. До 30.07.2026 так и было, только слепой шла вся высота целиком.
        """
        alt = min(float(alt), self.args.max_alt)
        # Слепой ступени больше заказанной высоты не бывает: 0,7 м из --takeoff-blind
        # рассчитаны на рабочие 2 м, а команда «взлети на полметра» — это полметра.
        # Контур выключен (--no-hold, --dry) — добирать остаток некому, и вся высота
        # уходит вслепую: иначе дрон навсегда остался бы висеть на слепой ступени.
        blind = alt if not self.hold_on else max(0.0, min(float(self.args.takeoff_blind), alt))
        self._set(job, state="taking_off")
        self.last_error = ""
        self.holder.reset()
        self._settle_until = 0.0        # новый полёт — новый цикл замеров, ждать нечего
        # Эталон высоты живёт ровно один полёт: он снят на прошлой рабочей высоте, и
        # на новой (или после перестановки дрона) врал бы ровно на разницу.
        self.side_ref, self._ref_prev, self._ref_tries = None, None, 0
        self._climb_left = 0.0
        self._blind_up = 0.0
        self._yaw_ref, self._yaw_drift, self._yaw_warned = None, None, False
        self.blind, self.marker_lost = 0, False
        self._search_off, self._search_leg = (0.0, 0.0), 0
        rest = max(0.0, alt - blind)
        say(f"ВЗЛЁТ на {alt:g} м: {blind:g} м вслепую"
            + (f", остальные {rest:.2f} м — по метке {self.marker}" if rest else ""))
        if self.dry:
            wait = 2.0
        else:
            # Ровно один navigate: повторный вызов переинициализирует траекторию.
            resp = self._hw("взлёт", lambda: self.drone.control.navigate(
                x=0.0, y=0.0, z=blind, yaw=0.0,
                speed=self.args.climb_speed, frame_id="body", auto_arm=True,
            ), timeout=20.0)
            ok = getattr(resp, "success", True)
            say(f"взлёт принят: {ok} {getattr(resp, 'message', '')}")
            if resp is not None and not ok:
                raise NavRefused(f"взлёт не принят: {getattr(resp, 'message', '')}")
            # Ждём всю слепую ступень, а не «когда команда принята»: контур не должен
            # включаться посреди неё — разбор в докстроке.
            speed = max(self.args.climb_speed, 0.01)
            wait = blind / speed + max(0.0, self.args.settle) + self.args.lock_wait
        # Высота записывается до паузы: если взлёт вытеснит аварийная посадка, дрон
        # всё равно уже пошёл вверх, и врать про ноль в статусе хуже, чем оценить.
        # Это ЦЕЛЬ: на время набора дрон ниже неё на climb_left (см. /status).
        self._set(job, alt=alt)
        if not self._wait(job, wait):
            say("взлёт прерван более важной командой — состояние не трогаю")
            return
        # Остаток пишется только после проверки: команду мог вытеснить land, и тогда
        # набирать высоту садящемуся дрону — последнее, что нужно.
        if not self._set(job, state="climbing" if rest else "hover", moved=True):
            return
        self._climb_left = rest
        if rest:
            say(f"слепая ступень {blind:g} м набрана: остаток {rest:.2f} м добираю "
                f"шагами по {self.args.climb_step:g} м, правя место и курс по метке")
        else:
            say(f"{alt:g} м набрано, удержание по метке включено")

    def land(self) -> dict:
        return self.start("land", self._land)

    def _land(self, job: Job) -> None:
        self._set(job, state="landing")
        # Эталон курса живёт ровно один полёт: следующий взлёт снимет свой. Сбрасываем
        # до посадки, чтобы контур не тянул садящийся дрон обратно на высоту.
        self._yaw_ref, self._yaw_drift = None, None
        self.holder.reset()
        self._settle_until = 0.0
        # Эталон снят на рабочей высоте: на снижении он уже ни о чём не говорит.
        self.side_ref, self._ref_prev, self._ref_tries = None, None, 0
        # Недобранный остаток здесь и кончается: садящемуся дрону добирать нечего.
        self._climb_left = 0.0
        self._blind_up = 0.0
        self.alt_seen = self.miss = self.side_seen = None
        say("ПОСАДКА")
        if self.dry:
            self._wait(job, 2.0)
            self._set(job, state="landed", alt=0.0, moved=True)
            return
        for attempt in range(1, 4):
            try:
                try:
                    resp = self._hw("посадка", self.drone.control.land, timeout=25.0)
                except TypeError:  # сборка со старой сигнатурой
                    resp = self._hw(
                        "посадка", lambda: self.drone.control.land(timeout=10.0), timeout=25.0
                    )
            except Exception as exc:  # noqa: BLE001
                say(f"посадка: попытка {attempt} сорвалась — {exc}")
                if not self._wait(job, 1.0):
                    return
                continue
            ok = getattr(resp, "success", True)
            say(f"посадка: попытка {attempt} — {ok} {getattr(resp, 'message', '')}")
            if ok:
                self._wait(job, self.args.land_wait)  # снижение идёт и после вытеснения
                self._set(job, alt=0.0, moved=True)
                confirmed, how = self._on_ground()
                self._set(job, state="landed" if confirmed else "landed_unverified")
                say(f"сел: {how}")
                return
            if not self._wait(job, 1.0):
                return
        self._set(job, state="land_failed")
        self.last_error = "борт не принял команду на посадку: сажайте пультом"
        say("ПОСАДКА НЕ ПРИНЯТА БОРТОМ — сажайте пультом")

    def _on_ground(self) -> tuple[bool, str]:
        """Есть ли доказательство, что дрон на земле, и какое.

        Единственный доступный на борту признак — дизарм в телеметрии. Она включается
        флагом --telemetry, то есть только там, где оператор уже убедился, что вызов
        не виснет. Без неё честный ответ — «доказательств нет»: принятая команда и
        выжданная пауза посадкой не являются, land() умеет вернуть успех и ничего
        не сделать.
        """
        if not self.args.telemetry:
            return False, (
                "команда принята и пауза выждана, подтверждения нет "
                "(телеметрия выключена) — проверьте глазами"
            )
        tel, err = self._telemetry()
        if tel is None:
            return False, f"подтвердить нечем: телеметрия молчит ({err}) — проверьте глазами"
        armed = getattr(tel, "armed", None)
        if armed is False:
            return True, "подтверждено телеметрией: дрон дизармлен"
        return False, f"телеметрия отвечает, но armed={armed} — дрон, похоже, ещё в воздухе"

    def shot(self) -> bytes:
        if self.dry:
            self.frames += 1
            return DRY_JPEG
        if not self.camera_ok:
            raise NoFrame("камера не готова (нет cv2/numpy или патча yuv)")
        try:
            frame = self._hw(
                "кадр", lambda: self.drone.image.take_picture(timeout=2.0), timeout=20.0
            )
        except Busy as exc:
            raise NoFrame(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise NoFrame(f"камера не отдала кадр: {exc}") from exc
        if frame is None or getattr(frame, "ndim", 0) != 3 or frame.size == 0:
            raise NoFrame("камера отдала пустой кадр")
        data = encode_jpeg(frame, self.args.color)
        if not data:
            raise NoFrame("кадр не удалось сжать в JPEG")
        self.frames += 1
        return data

    # --- огонь --------------------------------------------------------------

    def anchor(self, seen: dict[int, Fix], shape) -> Anchor | None:
        """Чем привязать этот кадр к полю: своя метка, чужая известная или высота.

        Порядок не случаен. Метка даёт масштаб по настоящему предмету 25 см и поворот
        по её же ребру — гипотез про объектив в этом пути нет вовсе. Своя метка
        предпочтительнее чужой просто потому, что она под дроном, то есть в середине
        кадра, где искажения меньше.

        Метки нет вовсе — считаем масштаб из высоты и угла обзора, а центром кадра
        объявляем свою площадку: дрон над ней и висит. Это грубее (угол обзора —
        гипотеза), но лучше, чем промолчать.
        """
        known = [self.marker] + [m for m in sorted(seen) if m in PAD_MARKER.values()]
        for mid in known:
            fix = seen.get(mid)
            if fix is None:
                continue
            cell = next((c for c, m in PAD_MARKER.items() if m == mid), None)
            if cell is None:
                continue
            x, y = self.cell_to_m(list(cell))
            return Anchor(fix.u, fix.v, x, y, MARKER_M / fix.side,
                          math.radians(self.args.marker_edge_deg) + fix.angle, "marker", mid)

        alt = self.alt_seen or self.alt
        span = 2.0 * float(alt) * math.tan(math.radians(self.args.fov_deg) / 2.0)
        width = float(shape[1])
        if span <= 0 or width <= 0:
            return None
        px, py = self.cell_to_m(self.pad)
        return Anchor(width / 2.0, shape[0] / 2.0, px, py, span / width, 0.0, "pose")

    def see_fire(self, frame) -> dict:
        """Разобрать один кадр: где горит и сколько там огоньков.

        Уровень пожара НЕ выдумывается: не нашли — так и пишем. Диспетчер в этом
        случае честно берёт уровень из настроек и помечает это в логе.
        """
        report: dict = {
            "found": False, "cell": None, "xy": None, "count": 0, "count_source": "",
            "spread_m": 0.0, "area": 0.0, "share": 0.0, "clipped": False,
            "anchor": "none", "marker_id": None, "markers": [], "alt": None,
            "at": round(time.time(), 1), "note": "",
        }
        seen = markers(frame)
        report["markers"] = sorted(seen)
        own = seen.get(self.marker)
        if own is not None:
            # Высота, с которой снят этот кадр, по своей же метке. None остаётся None:
            # «не знаю» и «ноль метров» — разные вещи, и врать тут нечего.
            height = self.height(own.side)
            report["alt"] = None if height is None else round(height, 2)
        anchor = self.anchor(seen, frame.shape)
        if anchor is None:
            report["note"] = "кадр не к чему привязать: ни метки, ни высоты"
            return report
        report["anchor"], report["marker_id"] = anchor.source, anchor.marker_id

        blobs = find_fires(frame, self.fire_hsv, self.args.min_area_px, self.args.max_area_share)
        if not blobs:
            report["note"] = "очага в кадре нет"
            return report
        for blob in blobs:
            blob.x, blob.y = anchor.to_map(blob.u, blob.v)
        inside = [b for b in blobs if self.in_field(self.m_to_cell(b.x, b.y))]
        if not inside:
            b = blobs[0]
            report["xy"] = [round(b.x, 2), round(b.y, 2)]
            report["area"], report["share"] = round(b.area, 1), round(b.share, 4)
            report["note"] = f"пятно за границей поля ({b.x:.2f}, {b.y:.2f}) м — не очаг"
            return report

        unit = token_px(anchor.mpp, self.args.token_m, self.args.token_fill)
        groups = clusters(inside, self.args.fire_group_m)
        counted = [(count_tokens(g, unit, self.args.split_ratio), g) for g in groups]
        # Кучек может быть несколько: очаг один, а рядом мог оказаться посторонний
        # красный предмет. Берём самую многочисленную, при равенстве — самую крупную.
        (count, source), best = max(counted, key=lambda it: (it[0][0], sum(b.area for b in it[1])))
        x, y, area, share, spread = group_center(best)
        cell = self.m_to_cell(x, y)
        margin = self.args.fire_group_m / 2.0 / anchor.mpp if anchor.mpp > 0 else 0.0
        notes = []
        if count > self.args.max_fire:
            notes.append(f"насчитано {count} огоньков — больше, чем бывает на поле; "
                         f"обрезано до {self.args.max_fire}")
            count = self.args.max_fire
        if len(groups) > 1:
            notes.append(f"кучек огня в кадре {len(groups)}, взята самая многочисленная")
        report.update({
            "found": True,
            "cell": [int(cell[0]), int(cell[1])],
            "xy": [round(x, 2), round(y, 2)],
            "count": int(count),
            "count_source": source,
            "spread_m": round(spread, 3),
            "area": round(area, 1),
            "share": round(share, 4),
            "clipped": clipped(best, frame.shape, margin),
        })
        if report["clipped"]:
            notes.append("кучка у края кадра — число огоньков по нему считать ненадёжно")
        report["note"] = "; ".join(notes)
        return report

    def fire(self) -> dict:
        """Свежий кадр -> ответ про огонь. Он же запоминается и уходит в /status."""
        if self.dry:
            self.last_fire = {
                "found": False, "note": "режим --dry: камеры нет, огонь искать не по чему",
                "at": round(time.time(), 1), "dry": True,
            }
            return self.last_fire
        if not self.camera_ok:
            raise NoFrame("камера не готова (нет cv2/numpy или патча yuv)")
        frame = self._frame("огонь")
        if frame is None:
            raise NoFrame("камера не отдала кадр")
        report = self.see_fire(frame)
        self.last_fire = report
        if report["found"]:
            say(f"ОГОНЬ: клетка {report['cell']}, огоньков {report['count']} "
                f"(счёт «{report['count_source']}», привязка «{report['anchor']}»)"
                + (f"; {report['note']}" if report["note"] else ""))
        else:
            say(f"огня не вижу: {report['note']}")
        return report

    @property
    def fire_hsv(self):
        """Пороги цвета огонька: из ключа --fire-hsv или замеренные по photo_fire/."""
        if not self.args.fire_hsv:
            return FIRE_HSV
        try:
            raw = json.loads(self.args.fire_hsv)
            return tuple((tuple(low), tuple(high)) for low, high in raw)
        except Exception as exc:  # noqa: BLE001 — ключ задаётся руками на площадке
            say(f"--fire-hsv не разобрать ({exc}) — беру замеренные пороги")
            return FIRE_HSV

    # --- аварийный останов и сторож -----------------------------------------

    def stop(self) -> dict:
        """Аварийная остановка: для дрона это немедленная посадка.

        Команда вытесняет текущую. Прерванный взлёт просыпается из паузы и уходит, не
        тронув состояние: иначе досыпающий взлёт написал бы «вишу» уже поверх посадки.
        """
        say("СТОП — сажусь")
        return self.start("stop-land", self._land, preempt=True)

    def touch(self) -> None:
        self._last_request = time.monotonic()

    # --- подстройка прицела --------------------------------------------------

    def trim(self, fwd: float, left: float) -> dict:
        """Сдвинуть точку прицеливания по НАБЛЮДАЕМОМУ увода дрона, метры.

        Контур приводит к нулю промах В КАДРЕ, а не расстояние между корпусом и
        меткой, и эти две величины расходятся на постоянную: объектив вынесен из
        центра корпуса, оптическая ось не проходит ровно через центр кадра, дрон
        висит с небольшим креном. Итог один и тот же — дрон устойчиво стоит мимо
        метки в одну и ту же сторону, а по кадру считает, что попал. Увидеть это
        может только человек, поэтому поправка вводится с его слов.

        Аргументы — куда именно уехал ДРОН относительно метки (вперёд/влево, м).
        Прицел на столько же и сдвигается: в равновесии он ровно и компенсирует
        уход. Меняется на лету — перезапускать борт и садиться незачем.
        """
        self.args.cam_fwd += float(fwd)
        self.args.cam_left += float(left)
        # Сглаженный промах снят при старом прицеле: оставить его — значит первую
        # поправку после подстройки выдать наполовину по старой цели.
        self.holder.reset()
        self._settle_until = 0.0
        say(f"прицел сдвинут на вперёд {fwd:+.2f} влево {left:+.2f} м → "
            f"вперёд {self.args.cam_fwd:+.2f} влево {self.args.cam_left:+.2f} м")
        return {
            "accepted": True,
            "command": "trim",
            "aim": [round(self.args.cam_fwd, 3), round(self.args.cam_left, 3)],
        }

    def watchdog(self) -> None:
        """Потеряли ноутбук — садимся сами (регламент 2.6: Failsafe при потере сигнала)."""
        limit = self.args.watchdog
        if limit <= 0:
            return
        while True:
            time.sleep(0.5)
            quiet = time.monotonic() - self._last_request
            # «error» в списке намеренно: дрон, у которого сорвалась команда, висит
            # ровно так же, как исправный, и без этого остаётся в воздухе навсегда —
            # Failsafe обязан сажать по факту «мы в воздухе», а не по факту «всё хорошо».
            aloft = self.state in ALOFT or (
                self.state == "error" and self.alt > 0.0
            )
            if quiet > limit and aloft:
                say(f"СТОРОЖ: {quiet:.0f} с без команд с ноутбука — сажусь сам")
                self._last_request = time.monotonic()
                # Вытесняет, а не встаёт в очередь: посадка по Failsafe не должна
                # ждать, пока доиграет взлёт, из-за которого дрон и висит.
                self.start("watchdog-land", self._land, preempt=True)


class Busy(Exception):
    pass


class NoFrame(Exception):
    pass


class NavRefused(Exception):
    """Полётный контроллер не принял navigate — значит дрон никуда и не полетел.

    Отличается от прочих ошибок тем, что аппарат остался ровно там же и таким же:
    висел — висит, стоял — стоит. Поэтому состояние откатывается на то, что было
    до команды, а не становится «error».
    """


# ═══════════════════════════════════════════════════════════════════════════
#  СЕТЬ
# ═══════════════════════════════════════════════════════════════════════════


class Handler(BaseHTTPRequestHandler):
    agent: Agent = None  # подставляется в main()

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    def log_message(self, fmt: str, *args) -> None:
        pass  # свой вывод понятнее: сыпать в терминал дрона строками HTTP незачем

    def do_GET(self) -> None:  # noqa: N802
        self.agent.touch()
        try:
            if self.path in ("/status", "/"):
                return self._json(200, self.agent.status())
            if self.path == "/fire":
                return self._json(200, self.agent.fire())
            if self.path == "/shot":
                data = self.agent.shot()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                return self.wfile.write(data)
        except NoFrame as exc:
            return self._json(503, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return self._json(500, {"error": str(exc)})
        self._json(404, {"error": f"нет такого пути: {self.path}"})

    def do_POST(self) -> None:  # noqa: N802
        self.agent.touch()
        body = self._body()
        # command_id ставит клиент и повторяет его при переотправке. Тела без него
        # исполняются как раньше: curl с руки никакого id не шлёт.
        cid = str(body.get("command_id") or "")
        try:
            if self.path == "/takeoff":
                alt = body.get("alt", self.agent.args.alt)
                return self._json(200, self.agent.once(cid, lambda: self.agent.takeoff(alt)))
            if self.path == "/land":
                return self._json(200, self.agent.once(cid, self.agent.land))
            if self.path == "/stop":
                return self._json(200, self.agent.once(cid, self.agent.stop))
            if self.path == "/trim":
                fwd = float(body.get("fwd", 0.0))
                left = float(body.get("left", 0.0))
                return self._json(200, self.agent.once(cid, lambda: self.agent.trim(fwd, left)))
        except Busy as exc:
            return self._json(409, {"error": str(exc)})
        except KeyError as exc:
            return self._json(400, {"error": f"в теле запроса нет поля {exc}"})
        except Exception as exc:  # noqa: BLE001
            return self._json(500, {"error": str(exc)})
        self._json(404, {"error": f"нет такого пути: {self.path}"})


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Агент дрона-монитора «Города дронов»")
    p.add_argument("--port", type=int, default=8020)
    p.add_argument("--name", default="m1", help="имя борта в логе диспетчера")
    p.add_argument("--cell", default="1,1", help="на какой площадке стоит, col,row")
    p.add_argument("--marker", type=int, default=None,
                   help="номер своей ArUco-метки; по умолчанию из карты поля по --cell")
    p.add_argument("--alt", type=float, default=2.0, help="рабочая высота над площадкой, м")
    p.add_argument("--max-alt", type=float, default=3.0,
                   help="потолок, м (регламент 2.6: 4 м от пола, площадка до 0,825 м)")
    p.add_argument("--climb-speed", type=float, default=0.3, help="скорость набора высоты, м/с")
    p.add_argument("--takeoff-blind", type=float, default=0.7,
                   help="сколько метров взлёта идёт вслепую одной командой, м; остаток "
                        "до --alt добирает контур, правя место и курс по метке")
    p.add_argument("--climb-step", type=float, default=0.3,
                   help="каким шагом контур добирает остаток высоты, м")
    p.add_argument("--land-wait", type=float, default=4.0, help="пауза на снижение, с")
    p.add_argument("--lock-wait", type=float, default=0.5,
                   help="запас паузы после слепой ступени взлёта до первой поправки "
                        "контура, с (сама ступень и --settle ждутся сверх этого)")
    p.add_argument("--watchdog", type=float, default=120.0, help="сесть, если нет команд N с (0 — выкл)")
    p.add_argument("--grid", default="6,6", help="размер поля в клетках")
    p.add_argument("--cell-size", type=float, default=0.8, help="сторона клетки, м")

    # --- удержание над меткой ---
    p.add_argument("--no-hold", action="store_true",
                   help="не держаться за метку (высота и положение остаются на автопилоте)")
    p.add_argument("--hold-period", type=float, default=0.5,
                   help="как часто идёт такт удержания, с (0 — не держать)")
    p.add_argument("--settle", type=float, default=0.6,
                   help="пауза на успокоение после поправки, с: пока дрон едет и висит "
                        "с креном, замер по кадру врёт (0 — мерить не переставая)")
    p.add_argument("--fix-speed", type=float, default=0.25, help="скорость доводки, м/с")
    p.add_argument("--gain", type=float, default=0.5,
                   help="какую долю промаха отрабатывать за раз")
    p.add_argument("--damp", type=float, default=0.1,
                   help="вес скорости изменения промаха, с: больше — спокойнее, но вялее")
    p.add_argument("--smooth", type=float, default=0.8,
                   help="сглаживание замера, 0..1 (1 — не сглаживать вовсе)")
    p.add_argument("--hold-tol", type=float, default=0.02,
                   help="промах меньше этого не правим: докуда доводить дрон, м. "
                        "Ниже 0,01 смысла нет — там шум опознания углов метки")
    p.add_argument("--min-hop", type=float, default=0.01,
                   help="самая короткая поправка, м: команду короче дотягиваем до неё")
    p.add_argument("--max-hop", type=float, default=0.4,
                   help="предел одной поправки положения, м")
    p.add_argument("--alt-dead", type=float, default=0.07,
                   help="уход высоты меньше этого не трогаем, м")
    p.add_argument("--alt-fix", type=float, default=0.25,
                   help="предел поправки высоты за одну команду, м (в обе стороны)")
    p.add_argument("--ref-calm", type=float, default=0.15,
                   help="эталон высоты снимается по двум подряд кадрам, где сторона "
                        "метки разошлась меньше этой доли: замер на раскачке испортил "
                        "бы высоту на весь полёт")
    p.add_argument("--ref-tries", type=int, default=6,
                   help="столько тактов ждём согласия двух кадров, дальше берём эталон "
                        "как есть: без него высота не держится вовсе")
    p.add_argument("--blind-max", type=int, default=30,
                   help="столько кадров подряд без своей метки — и объявляем её потерянной")
    p.add_argument("--search-step", type=float, default=0.3,
                   help="на столько метров отходить в каждую сторону, разыскивая "
                        "потерянную метку (0 — не искать, висеть на автопилоте)")
    p.add_argument("--search-rise", type=float, default=0.1,
                   help="на столько метров подниматься в поиске: выше — шире обзор, м")
    p.add_argument("--search-rise-max", type=int, default=5,
                   help="сколько раз за одну потерю разрешено подняться (0 — не подниматься)")
    p.add_argument("--cam-fwd", type=float, default=0.0,
                   help="плечо камеры: на столько метров целимся НАЗАД, потому что body "
                        "считается от центра корпуса, а метку наводит объектив "
                        "(0 — поправки нет, включать только по замеренному промаху)")
    p.add_argument("--cam-left", type=float, default=0.0, help="то же поперёк, м")
    p.add_argument("--sign-fwd", type=float, default=1.0,
                   help="знак оси «вперёд» (−1, если поправка уводит дрон от метки)")
    p.add_argument("--sign-left", type=float, default=1.0, help="знак оси «влево»")
    p.add_argument("--fov-deg", type=float, default=65.0,
                   help="угол обзора камеры по горизонтали, град. ГИПОТЕЗА, и удержание "
                        "высоты ею БОЛЬШЕ НЕ ПОЛЬЗУЕТСЯ (высота идёт от эталона): "
                        "осталась только привязка кадра к полю там, где метки не видно")
    p.add_argument("--focal-px", type=float, default=0.0,
                   help="фокусное расстояние в пикселях; задано — --fov-deg не используется")

    # --- курс ---
    p.add_argument("--no-yaw-hold", action="store_true", help="не держать курс по метке")
    p.add_argument("--yaw-dead", type=float, default=3.0,
                   help="увод меньше этого не трогаем: шум опознания метки, град")
    p.add_argument("--yaw-fix", type=float, default=10.0,
                   help="предел доворота за одну команду, град")
    p.add_argument("--yaw-max", type=float, default=45.0,
                   help="увод больше этого — сбой опознания метки, а не поворот дрона, град")

    # --- огонь ---
    p.add_argument("--fire-hsv", default="",
                   help="пороги цвета огонька в HSV, JSON [[[H,S,V],[H,S,V]],…]; "
                        "по умолчанию замеренные по photo_fire/")
    p.add_argument("--min-area-px", type=float, default=80.0,
                   help="пятно мельче этого — не огонёк, а шум (с 2 м жетон даёт ~240)")
    p.add_argument("--max-area-share", type=float, default=0.15,
                   help="пятно крупнее этой доли кадра — цветной РАЙОН поля, а не огонёк")
    p.add_argument("--fire-group-m", type=float, default=0.4,
                   help="пятна ближе этого друг к другу — одна кучка, м")
    p.add_argument("--token-m", type=float, default=0.045, help="длинная сторона жетона, м")
    p.add_argument("--token-fill", type=float, default=0.47,
                   help="какую долю своего квадрата занимает силуэт жетона")
    p.add_argument("--split-ratio", type=float, default=1.6,
                   help="во сколько раз пятно крупнее одиночного жетона, чтобы делить его")
    p.add_argument("--max-fire", type=int, default=3, help="больше огоньков на поле не бывает")
    p.add_argument("--marker-edge-deg", type=float, default=0.0,
                   help="куда на поле смотрит верхнее ребро метки, град (как в city/config.yaml)")

    p.add_argument("--telemetry", action="store_true", help="добавлять телеметрию в статус (может виснуть)")
    p.add_argument(
        "--color", choices=("bgr", "rgb"), default="bgr",
        help="порядок каналов у камеры борта: bgr — как на наших дронах (проверено), "
             "rgb — если на кадре красное выглядит синим",
    )
    p.add_argument("--dry", action="store_true", help="без железа: отвечать, но ничего не делать")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    agent = Agent(args)
    agent.open()

    handler = type("Bound", (Handler,), {"agent": agent})
    try:
        server = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    except OSError as exc:
        # Самая частая ошибка запуска: агент уже работает с прошлого раза. Голый
        # traceback про «Address already in use» этого не объясняет.
        say(f"ПОРТ {args.port} УЖЕ ЗАНЯТ — похоже, агент уже запущен ({exc})")
        # Скобки в шаблоне не опечатка: без них pkill/pgrep находят и убивают
        # собственную же команду (ssh-сессия падает с кодом 255).
        say('  посмотреть:  pgrep -af "[d]rone_agent"')
        say('  остановить:  pkill -9 -f "[d]rone_agent"')
        say(f"  или запустить этот на другом порту:  --port {args.port + 1}")
        agent.close()
        return 1
    threading.Thread(target=agent.watchdog, daemon=True).start()
    threading.Thread(target=agent.hold_keeper, daemon=True).start()

    if agent.marker < 0:
        say(f"ВНИМАНИЕ: для клетки {agent.cell} в карте поля нет метки — задайте --marker, "
            f"иначе держаться будет не за что")
    if agent.hold_on:
        aim_note = (f"прицел на {args.cam_fwd * 100:.0f} см назад"
                    if args.cam_fwd else "прицел в центр метки")
        say(f"держусь по метке {agent.marker}: такт раз в {args.hold_period:g} с, "
            f"взлёт {args.takeoff_blind:g} м вслепую и остаток шагами по "
            f"{args.climb_step:g} м по метке, высота {args.alt:g} м по её стороне "
            f"(эталон снимается после набора), "
            f"потолок {args.max_alt:g} м над площадкой, {aim_note}")
    elif args.no_hold and not args.dry:
        say("за метку не держусь: запущен с --no-hold, положение и высота на автопилоте")
    if agent.yaw_hold:
        say("курс держу по метке: эталон снимается первым же кадром после взлёта")
    say(f"агент «{args.name}» слушает порт {args.port}" + (" (ЗАГЛУШКА)" if args.dry else ""))
    say(f"проверка: curl http://<адрес-дрона>:{args.port}/status")
    say("остановить: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        say("остановка по Ctrl+C")
        if agent.state not in ON_GROUND:
            say("дрон в воздухе — сажаю перед выходом")
            agent.stop()
            # Посадка идёт в фоновом потоке, а он демон: выйти раньше, чем дрон
            # сядет, значит бросить его в воздухе.
            deadline = time.monotonic() + args.land_wait + 10.0
            while agent.state not in ON_GROUND and time.monotonic() < deadline:
                time.sleep(0.2)
            say(f"состояние на выходе: {agent.state}")
    finally:
        server.server_close()
        agent.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
