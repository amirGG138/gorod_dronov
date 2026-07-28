#!/home/sverk/venv_fly/bin/python3
"""Удержание дрона над ArUco-меткой: взлёт → захват метки → зависание → посадка.

Тестовая программа для Обрика (ROS 2 Humble, `sverk_interfaces`). Делает ровно
одно: поднимается на рабочую высоту, цепляется за ближайшую видимую метку и
держится над ней HOLD_S секунд, после чего садится. Ни миссий, ни карты поля, ни
роя, ни LLM — это стенд для проверки железа, а не часть зачётного решения.

Весь полёт — теми же командами, что в базовом примере из документации:

    drone.control.navigate(x, y, z, yaw, speed, frame_id="body", auto_arm=...)
    time.sleep(...)
    drone.control.land()

Телеметрия не используется вообще: `get_telemetry` на этой сборке виснет без FCU.
Высота и курс читаются с самой метки — её сторона в пикселях обратно
пропорциональна высоте, а поворот в кадре показывает, как повёрнут дрон. Метры
появляются лишь как масштаб кадра, и тот считается по известной стороне метки, а
не по высоте, так что калибровка камеры не нужна.

Что этим полётом проверяется на площадке в первый день:
  * патч `yuv422_yuy2` — иначе не будет ни одного кадра;
  * реальная сторона метки (MARKER_M, см. docs/field-map/ — на железе не сверялась);
  * знак осей `body` — команда должна идти НАВСТРЕЧУ сдвигу дрона;
  * накопление высоты у `navigate(frame_id="body", z=0)`;
  * что `land()` действительно сажает.

Перед вылетом править только блок НАСТРОЙКИ ниже.

    ~/hold_aruco/hold_aruco.py

Шебанг указывает на ~/venv_fly — отдельное окружение с numpy 1.26. Оно нужно
потому, что на борту через pip поставлен numpy 2.2.6 поверх системного 1.21.5,
а python3-opencv (4.5.4) собран под numpy 1.x и с двойкой падает на импорте
(«numpy.core.multiarray failed to import»). Ломается не только эта программа —
sverk_interfaces тоже импортирует cv2. Систему решено не трогать: numpy 2 нужен
чужому коду на этом же борте (pid-tuning-assistant). Окружение создано так:

    python3 -m venv --system-site-packages ~/venv_fly
    ~/venv_fly/bin/pip install "numpy<2"

--system-site-packages обязателен: rclpy и cv2 берутся из системы, поставить их
через pip нельзя. Само окружение ROS (LD_LIBRARY_PATH и прочее) приходит из
~/.bashrc, который сорсит setup.bash при интерактивном входе.

Ctrl+C — штатный способ прервать: посадка идёт через тот же finally.
"""

import math
import time

import cv2
import numpy as np
import sverk_interfaces

# ═══════════════════════════════════════════════════════════════════════
#  НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════════════════

ALT = 1.5           # рабочая высота, м (потолок по регламенту — 4.0)
HOLD_S = 60.0       # сколько секунд держаться над меткой, потом посадка
# Сторона метки, м — по ней кадр переводится в метры. Значение из
# docs/field-map/map.txt, где карта полигона на железе ЕЩЁ НЕ ПРОВЕРЯЛАСЬ.
# Ошибка здесь даёт систематический промах и «плавающую» высоту: перемерить
# рулеткой в первый день и поправить эту одну константу.
MARKER_M = 0.25

SPEED = 0.5         # скорость доводки, м/с
CLIMB_SPEED = 0.3   # скорость набора высоты — медленнее горизонтальной, взлёт мягче
YAW = 0.0           # курс на взлёте: 0 при frame_id="body" — «не менять»

# Взлёт: пока дрон качает после набора высоты, командовать ему нельзя — наведение
# по прыгающей в кадре метке только раскачивает сильнее. Поэтому сначала ждём,
# пока картинка не устоится, и только потом трогаемся с места.
SETTLE_S = 3.0      # запас на успокоение сверх времени набора высоты, с
SETTLE_FRAMES = 3   # столько кадров подряд метка должна стоять на месте
SETTLE_DRIFT = 0.15 # «стоит на месте»: сдвиг между кадрами меньше этой доли метки
SETTLE_TRIES = 20   # предел ожидания успокоения (кадров), дальше держимся как есть

GAIN = 0.7          # какую долю рассчитанного промаха отрабатывать за раз
# «Над меткой» — промах меньше этого, в МЕТРАХ. В «Змейке» допуск задавался долей
# диагонали кадра, и это правильно для облёта маршрута (там нужно «попасть в узел»),
# но для зависания слишком грубо: 0.08 диагонали на рабочей высоте — это 24 см
# мёртвой зоны, дрон в ней просто дрейфует. Промах у нас и так считается в метрах,
# так что порог честнее задать там же — и он не поедет при смене высоты и камеры.
TOL_M = 0.10
ALT_FIX = 0.3       # предел поправки высоты за одну команду, м
TURN_MAX = 45.0     # поправка курса больше этой — не увод дрона, а повёрнутая метка, град
YAW_DEAD = 3.0      # увод меньше этого не трогаем: шум опознания метки, а не поворот, град
YAW_FIX = 15.0      # предел доворота за одну команду, град — как ALT_FIX для высоты

LOOK_UP = 0.3       # на столько подняться, если метки не видно, м
CLIMB_MAX = 1.0     # выше рабочей высоты не подниматься, м (потолок п. 2.6.3 — 4 м)
BLIND_FRAMES = 2    # столько кадров подряд без метки — и поднимаемся осмотреться
BLIND_MAX = 20      # столько кадров подряд без метки — и на посадку
HOP_MAX_M = 1.0     # длиннее этого одна команда доводки не бывает, м
HOP_PAD = 0.8       # запас к паузе перелёта на разгон, торможение и успокоение, с
FRAME_PAUSE = 0.3   # пауза между кадрами, когда команда не отправлялась, с
NAV_FAIL_MAX = 5    # столько отказов navigate подряд — и полёт прекращается

LAND_TRIES = 3      # столько раз повторить команду посадки, если её не приняли
LAND_S = 8.0        # ждать снижения после принятой посадки, прежде чем гасить ноду
LAND_DROP = 0.4     # снижение началось, если оценка высоты упала на эту долю от рабочей
LAND_DONE = 0.35    # ниже этой оценки высоты дрон считается севшим, м
LAND_LAST_S = 30.0  # сколько ещё слать land, если посадка так и не подтвердилась, с

# ═══════════════════════════════════════════════════════════════════════
#  КАМЕРА
# ═══════════════════════════════════════════════════════════════════════

# Словарь — 4X4_1000, а НЕ 4X4_50 как в «Змейке»: маркеры нашего поля 50, 60, 62, 7
# (docs/field-map/map.txt), и 60 с 62 в словарь на 50 элементов не влезают.
# Тот же словарь стоит по умолчанию у бортовой ноды aruco_detect_node
# (параметр dictionary_id=3), так что опознание совпадёт с бортовым.
_ARUCO_DICT = (cv2.aruco.getPredefinedDictionary if hasattr(cv2.aruco, "getPredefinedDictionary")
               else cv2.aruco.Dictionary_get)(cv2.aruco.DICT_4X4_1000)
_ARUCO_PARAMS = (cv2.aruco.DetectorParameters() if hasattr(cv2.aruco, "DetectorParameters")
                 else cv2.aruco.DetectorParameters_create())
_ARUCO = (cv2.aruco.ArucoDetector(_ARUCO_DICT, _ARUCO_PARAMS)
          if hasattr(cv2.aruco, "ArucoDetector") else None)   # None — OpenCV 4.5/4.6


def patch_yuv(drone):
    """Научить камеру отдавать BGR: бортовая публикует yuv422_yuy2, а to_cv2 его не знает."""
    image = drone.image
    original = getattr(image, "to_cv2", None)
    if original is None:
        return

    def to_cv2(msg):
        if (getattr(msg, "encoding", "") or "").lower() in ("yuv422_yuy2", "yuyv", "yuv422"):
            yuv = np.frombuffer(msg.data, np.uint8).reshape((msg.height, msg.width, 2))
            return cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_YUY2)
        return original(msg)

    image.to_cv2 = to_cv2


def look(drone):
    """Один кадр с камеры (BGR) или None.

    None — и когда камера не отдала кадр, и когда отдала негодный: разбирать такой
    нельзя (cvtColor на пустом или одноканальном кадре бросает исключение), а вся
    программа ниже уже умеет ждать следующего кадра.
    """
    try:
        img = drone.image.take_picture(timeout=2.0)
    except Exception as exc:
        print(f"кадр не получен: {exc}", flush=True)
        return None
    if img is None or getattr(img, "ndim", 0) != 3 or img.size == 0:
        return None
    return img


# ═══════════════════════════════════════════════════════════════════════
#  ЗРЕНИЕ
# ═══════════════════════════════════════════════════════════════════════


def markers(img):
    """Метки на кадре: {ID: (x, y, сторона в пикселях, поворот в радианах)}.

    Поворот — угол верхней стороны квадрата в кадре. Метки на поле уложены
    одинаково, поэтому их поворот показывает, как повёрнут сам дрон.

    Фильтра по ID здесь нет: держимся над любой меткой, какая попалась. Отсеиваются
    только вырожденные (сторона в один пиксель) — на них масштаб кадра ушёл бы в
    бесконечность.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if _ARUCO is not None:
        corners, ids, _ = _ARUCO.detectMarkers(gray)
    else:
        corners, ids, _ = cv2.aruco.detectMarkers(gray, _ARUCO_DICT, parameters=_ARUCO_PARAMS)
    if ids is None or len(ids) == 0:
        return {}

    seen = {}
    for quad, mid in zip(corners, ids.flatten()):
        pts = np.asarray(quad, np.float32).reshape(-1, 2)
        x, y = pts.mean(axis=0)
        # Сторона метки — масштаб кадра, и берётся она как САМОЕ ДЛИННОЕ ребро, а не
        # среднее. Наклонённый дрон видит квадрат метки прямоугольником: рёбра вдоль
        # оси наклона длину сохраняют, поперечные сжимаются в cos наклона. Среднее
        # четырёх занижало сторону, а по ней считается высота — дрон решал, что он
        # выше, чем есть, и на каждом разгоне получал ложную команду вниз.
        side = float(max(np.linalg.norm(pts[i] - pts[(i + 1) % 4]) for i in range(4)))
        edge = pts[1] - pts[0]
        if side > 1.0:
            seen[int(mid)] = (float(x), float(y), side, math.atan2(float(edge[1]), float(edge[0])))
    return seen


def nearest(seen, center):
    """Ближайшая к центру кадра метка — та, над которой висим: (ID, замер) или None."""
    if not seen:
        return None
    mid = min(seen, key=lambda i: math.hypot(seen[i][0] - center[0], seen[i][1] - center[1]))
    return mid, seen[mid]


# ═══════════════════════════════════════════════════════════════════════
#  ВЫСОТА — тоже по метке
# ═══════════════════════════════════════════════════════════════════════
#
# `navigate(frame_id="body", z=0)` держит не высоту, а «сколько было в момент
# команды»: цель считается от текущего положения. При доводке дрон наклоняется и
# слегка всплывает, следующая команда принимает эту высоту за норму — и ошибка
# копится только вверх, тем быстрее, чем чаще команды. Для зависания это главный
# враг: команд тут много, а перемещений почти нет.
#
# Лечится тем же, чем и всё остальное здесь, — меткой: её сторона в пикселях
# обратно пропорциональна высоте. Запоминаем сторону на рабочей высоте сразу после
# взлёта и дальше каждой командой возвращаемся к ней. Телеметрия не нужна.

SIDE_REF = 0.0      # сторона метки на рабочей высоте, пиксели (замер после взлёта)
ANGLE_REF = None    # поворот метки в кадре на взлёте — «нос смотрит туда же, что и тогда»
BLIND_UP = 0.0      # превышение над рабочей высотой, м: замер по метке или счисление
NAV_FAILS = 0       # отказов navigate подряд
TURN_WARNED = False # про повёрнутую метку ругаемся один раз, а не на каждом кадре


class FlightAborted(RuntimeError):
    """Дальше лететь нечем: команды управления не принимаются. Только на посадку."""


def alt_by_side(side):
    """Оценка высоты по стороне метки в кадре, м. 0.0 — эталон ещё не замерен."""
    if SIDE_REF <= 1.0 or side <= 1.0:
        return 0.0
    return ALT * SIDE_REF / side


def hold_alt(side):
    """На сколько подняться (+) или опуститься (−), чтобы вернуться на рабочую высоту."""
    now = alt_by_side(side)
    if not now:
        return 0.0
    correction = ALT - now
    if abs(correction) < 0.05:          # мёртвая зона: не дёргаем дрон по мелочи
        return 0.0
    return max(-ALT_FIX, min(ALT_FIX, correction))


# ═══════════════════════════════════════════════════════════════════════
#  КУРС — тоже по метке
# ═══════════════════════════════════════════════════════════════════════
#
# Смещение метки от центра кадра в поправке на курс не нуждается: кадр
# поворачивается вместе с дроном, и «метка левее центра» означает «сместиться
# влево» при любом курсе. Но сам курс дрон потихоньку теряет, а `yaw=0.0` при
# frame_id="body" его не держит — по документации это «не менять курс», то есть
# каждая команда закрепляет уже накопленный увод. Поэтому увод ещё и
# отрабатывается: читаем его по повороту метки в кадре и отдаём ближайшей же
# команде — отдельной команды разворота не нужно.


def turn_error(angle):
    """На сколько дрон отвернулся от курса взлёта, радианы (−π…π).

    Курс читается по повороту метки в кадре, а это верно лишь пока метка лежит так
    же, как в момент замера эталона. Держимся мы всё время над одной и той же
    меткой, так что подмены раскладки тут быть не может, — но увод больше TURN_MAX
    всё равно неправдоподобен (каждая команда navigate курс удерживает) и означает
    скорее ошибку опознания углов метки. Такая поправка отбрасывается.
    """
    global TURN_WARNED
    if ANGLE_REF is None:
        return 0.0
    error = (angle - ANGLE_REF + math.pi) % (2 * math.pi) - math.pi
    if abs(error) > math.radians(TURN_MAX):
        if not TURN_WARNED:
            print(f"!!! поворот метки {math.degrees(error):+.0f}° — дрон так не отворачивает. "
                  f"Похоже, сбой опознания углов метки; поправку курса игнорируем",
                  flush=True)
            TURN_WARNED = True
        return 0.0
    return error


def hold_yaw(angle):
    """Доворот к курсу взлёта для очередной команды navigate, радианы.

    Ровно то же, что hold_alt делает с высотой, только для курса.

    Знак. `turn_error` даёт увод ПРОТИВ часовой, а положительный yaw в body — это
    тоже против часовой (в документации `set_yaw(-pi/2)` описан как поворот по
    часовой). Значит отработать увод — это скомандовать ему обратный знак.

    Отдаём не весь увод разом, а не больше YAW_FIX: на большом довороте кадр
    смазывается сильнее, чем стоит того выигрыш. Мелочь внутри YAW_DEAD не трогаем
    вовсе — иначе дрон дёргался бы на шуме опознания метки.
    """
    error = turn_error(angle)
    if abs(error) < math.radians(YAW_DEAD):
        return 0.0
    limit = math.radians(YAW_FIX)
    return max(-limit, min(limit, -error))


# ═══════════════════════════════════════════════════════════════════════
#  ПОЛЁТ
# ═══════════════════════════════════════════════════════════════════════


def fly(drone, forward, left, up=0.0, turn=0.0):
    """Смещение по корпусу: x вперёд, y влево, z вверх, turn — доворот курса.

    Команда и пауза — как в примере из документации; `turn` уходит в тот же navigate
    штатным аргументом `yaw`, отдельной команды разворота не появляется.
    """
    distance = math.hypot(forward, left)
    # Доворот проверяется наравне со смещением: дрон, уже стоящий над меткой, никуда
    # не летит — и без этой проверки накопленный увод курса не отрабатывался бы
    # ровно там, где его важнее всего убрать, на зависании.
    if distance < 0.05 and abs(up) < 0.05 and abs(turn) < math.radians(YAW_DEAD):
        return False

    # Метровый бросок при удержании — это почти всегда ошибка опознания, а не
    # реальный снос. Летим только часть: контур замкнут по метке, следующий кадр
    # доведёт остаток.
    if distance > HOP_MAX_M:
        print(f"          поправка {distance:.1f} м урезана до {HOP_MAX_M:.1f} м", flush=True)
        forward, left = forward * HOP_MAX_M / distance, left * HOP_MAX_M / distance
        distance = HOP_MAX_M

    global NAV_FAILS
    # Отказом считается и «success=False», и брошенное исключение: для дрона это
    # одно и то же — команда не выполнена.
    try:
        resp = drone.control.navigate(x=float(forward), y=float(left), z=float(up),
                                      yaw=float(turn), speed=SPEED, frame_id="body",
                                      auto_arm=False)
        refused = resp is not None and not getattr(resp, "success", True)
        why = getattr(resp, "message", "")
    except Exception as exc:
        refused, why = True, f"исключение: {exc}"

    # Одиночный отказ бывает и на исправном дроне — просто повторим. А вот отказы
    # подряд означают, что дрон больше не принимает управление (выбило из OFFBOARD,
    # сработал failsafe): слать в пустоту бессмысленно и опасно — садимся.
    if refused:
        NAV_FAILS += 1
        print(f"          navigate отказал ({NAV_FAILS}/{NAV_FAIL_MAX}): {why}", flush=True)
        if NAV_FAILS >= NAV_FAIL_MAX:
            raise FlightAborted(f"navigate отказал {NAV_FAILS} раз подряд")
    else:
        NAV_FAILS = 0
    # navigate возвращается сразу, дрон летит в фоне — ждать окончания приходится
    # паузой. Время в пути считается по длине с вертикалью, а HOP_PAD добавлен на
    # разгон, торможение и успокоение: снимок, сделанный на ещё летящем дроне, даёт
    # промах и раскачку. Дрон дёргается на каждом шаге — увеличивать надо HOP_PAD.
    time.sleep(math.hypot(distance, up) / SPEED + HOP_PAD)
    return True


def descending(drone):
    """Следить за посадкой: («пошёл вниз», «сел»).

    Принятая команда `land()` ещё не значит, что дрон садится, — а телеметрии, по
    которой это видно всем остальным, у нас нет. Зато есть та же метка, по которой
    держалась высота: `alt_by_side` даёт оценку, и её падение и есть подтверждение.

    Два ответа, а не один, потому что это два разных факта. Падение высоты на
    LAND_DROP говорит лишь, что снижение началось, — объявлять по нему посадку
    нельзя, дрон в этот момент ещё почти в метре над полом. Касание — это либо
    оценка ниже LAND_DONE, либо пропавшая метка после начавшегося снижения: у
    самого пола камера её уже не охватывает.
    """
    started = False
    limit = time.time() + LAND_S
    while time.time() < limit:
        img = look(drone)
        if img is None:
            time.sleep(FRAME_PAUSE)
            continue
        base = nearest(markers(img), (img.shape[1] / 2.0, img.shape[0] / 2.0))
        if base is None:
            if started:
                print("          метки не видно — дрон у самого пола", flush=True)
                return True, True
            time.sleep(FRAME_PAUSE)
            continue
        now = alt_by_side(base[1][2])
        if not now:
            return True, True               # эталона нет — проверить нечем, не мешаем
        print(f"          снижение: h≈{now:.1f} м", flush=True)
        if now <= LAND_DONE:
            return True, True
        if now <= ALT * (1.0 - LAND_DROP):
            started = True
        time.sleep(FRAME_PAUSE)
    return started, False


def touch_down(drone):
    """Посадить дрон. Команда повторяется, пока дрон не пойдёт вниз.

    Единственный вызов `land()` — слишком слабая гарантия для конца полёта: он может
    вернуть success=False, бросить исключение или быть принятым, но ни к чему не
    привести. Поэтому принятая команда ещё и подтверждается снижением по камере.
    Отдельно подстрахована сигнатура: в документации `land()` описан без аргументов,
    а `timeout` — нет, и на другой сборке библиотеки он даёт TypeError.
    """
    for attempt in range(1, LAND_TRIES + 1):
        try:
            try:
                resp = drone.control.land()
            except TypeError:                       # сборка со старой сигнатурой
                resp = drone.control.land(timeout=10.0)
        except Exception as exc:
            print(f"ПОСАДКА: попытка {attempt} сорвалась — {exc}", flush=True)
            time.sleep(1.0)
            continue

        print(f"ПОСАДКА: попытка {attempt} — {getattr(resp, 'success', '?')} "
              f"{getattr(resp, 'message', '')}", flush=True)
        if resp is not None and not getattr(resp, "success", True):
            time.sleep(1.0)
            continue

        started, landed = descending(drone)
        if landed:
            print("ПОСАДКА: дрон на земле", flush=True)
            return True
        if started:
            # Снижение идёт, но до земли на этом отрезке не дошло — просто ждём его
            # дальше, не пересылая команду: повтор land в середине снижения ничего
            # не улучшает, а лог засоряет.
            print("ПОСАДКА: снижается, ждём касания", flush=True)
            _, landed = descending(drone)
            if landed:
                print("ПОСАДКА: дрон на земле", flush=True)
                return True
        print("ПОСАДКА: снижения не видно — повторяем команду", flush=True)

    print("!" * 54, flush=True)
    print("!!! ПОСАДКА НЕ ПОДТВЕРЖДЕНА — САЖАЙТЕ С ПУЛЬТА НЕМЕДЛЕННО !!!", flush=True)
    print("!" * 54, flush=True)
    # Нода не гаснет, пока есть надежда до дрона достучаться: закрыть её — значит
    # потерять последний канал управления. Команда шлётся дальше, пока пилот не
    # перехватит с пульта или не выйдет LAND_LAST_S.
    last = time.time() + LAND_LAST_S
    while time.time() < last:
        try:
            drone.control.land()
        except Exception as exc:
            print(f"ПОСАДКА: {exc}", flush=True)
        print("!!! САЖАЙТЕ С ПУЛЬТА !!!", flush=True)
        if descending(drone)[1]:
            return True
    return False


def climb(drone):
    """Подняться осмотреться, когда метки не видно, — но не выше предела.

    Пока метки нет, высоту проверить нечем: `hold_alt` работает по её размеру в
    кадре. Значит подъём вслепую надо считать самим и вовремя останавливаться,
    иначе дрон, потерявший метку, будет набирать высоту до самого потолка зоны
    (п. 2.6.3 — не выше 4 м). Как только метка нашлась, счётчик обнуляется:
    дальше высоту держит `hold_alt`.
    """
    global BLIND_UP
    if BLIND_UP + LOOK_UP > CLIMB_MAX:
        print(f"          выше не поднимаемся: набрано {BLIND_UP:.1f} м вслепую",
              flush=True)
        return
    BLIND_UP += LOOK_UP
    print(f"          метки не видно — поднимаемся осмотреться (+{BLIND_UP:.1f} м)",
          flush=True)
    # Курс тут не доворачиваем: читать его тоже не с чего, метки в кадре нет.
    fly(drone, 0.0, 0.0, LOOK_UP)


def grounded(side):
    """Метка в кадре — заменить счисленный подъём на измеренный.

    Обнулять счётчик по одному факту «метка нашлась» нельзя: дрон в этот момент
    ещё наверху, `hold_alt` опускает его лишь по ALT_FIX за команду. Метка снова
    пропала — и был бы доступен новый полный подъём, так высота росла бы
    ступеньками мимо предела. Поэтому пока метку видно, счётчик — это честный
    замер превышения над рабочей высотой, а счисление работает только вслепую.
    """
    global BLIND_UP
    now = alt_by_side(side)
    if now:
        BLIND_UP = max(0.0, now - ALT)


def settle(drone):
    """Дождаться спокойного висения. Возвращает (ID метки, сторона, поворот) или None.

    Признак того, что дрон перестал качать, — метка под ним стоит в кадре: между
    соседними кадрами её центр и размер почти не меняются. Пока этого нет, команд
    не отправляем вовсе: доводка по прыгающей метке раскачивает дрон ещё сильнее.

    На спокойном кадре снимаются эталоны высоты и курса, поэтому спешить тут
    нельзя: замер на раскачке испортил бы весь полёт.
    """
    previous = None
    calm = 0
    last = None
    for _ in range(SETTLE_TRIES):
        img = look(drone)
        if img is None:
            time.sleep(FRAME_PAUSE)
            continue

        base = nearest(markers(img), (img.shape[1] / 2.0, img.shape[0] / 2.0))
        if base is None:
            previous, calm = None, 0
            time.sleep(FRAME_PAUSE)
            continue

        mid, (x, y, side, angle) = base
        last = (mid, side, angle)
        if previous is not None and previous[0] == mid:
            px, py, pside = previous[1]
            drift = math.hypot(x - px, y - py) / side      # сдвиг в долях метки
            zoom = abs(side - pside) / side                # и «дыхание» размера
            if drift < SETTLE_DRIFT and zoom < SETTLE_DRIFT:
                calm += 1
                if calm >= SETTLE_FRAMES:
                    print(f"          висим спокойно (метка {mid}, {side:.0f} px)", flush=True)
                    return mid, side, angle
            else:
                calm = 0
        previous = (mid, (x, y, side))
        time.sleep(FRAME_PAUSE)

    if last is None:
        print("          метки под дроном нет — держаться не за что", flush=True)
        return None
    print("          успокоиться не вышло — цепляемся за метку как есть", flush=True)
    return last


# ═══════════════════════════════════════════════════════════════════════
#  УДЕРЖАНИЕ
# ═══════════════════════════════════════════════════════════════════════


def hold(drone, target, started):
    """Держаться над меткой target, пока не выйдет HOLD_S. True — доработали срок.

    Одна метка на весь полёт: перецепляться на соседнюю нельзя, между метками поля
    2.4 м, и дрон запрыгал бы между ними. Пропала своя — считаем кадр слепым, даже
    если в нём видно чужие.
    """
    blind = 0
    while True:
        spent = time.time() - started
        if spent >= HOLD_S:
            print(f"t={spent:5.1f} срок вышел — на посадку", flush=True)
            return True

        img = look(drone)
        if img is None:
            time.sleep(FRAME_PAUSE)
            continue

        height, width = img.shape[:2]
        cx, cy = width / 2.0, height / 2.0
        seen = markers(img)

        if target not in seen:
            blind += 1
            others = " ".join(str(i) for i in sorted(seen)) or "нет"
            print(f"t={spent:5.1f} метка  --  слепой кадр {blind}/{BLIND_MAX} "
                  f"(в кадре: {others})", flush=True)
            if blind >= BLIND_MAX:
                print(f"t={spent:5.1f} метка {target} потеряна — на посадку", flush=True)
                return False
            if blind % BLIND_FRAMES == 0:
                climb(drone)
            else:
                time.sleep(FRAME_PAUSE)
            continue

        blind = 0
        x, y, side, angle = seen[target]
        grounded(side)

        # Пиксели в метры — по стороне самой метки. Камера смотрит вниз: верх кадра
        # это «вперёд», левый край — «влево». Знак минус потому, что двигаться надо
        # НАВСТРЕЧУ смещению метки: метка уехала вниз кадра — дрон отнесло вперёд.
        scale = MARKER_M / side
        miss = math.hypot(x - cx, y - cy) * scale
        up, turn = hold_alt(side), hold_yaw(angle)

        if miss <= TOL_M:
            # Над меткой: горизонталь не трогаем, но высоту и курс вернуть надо —
            # именно на зависании они и уползают.
            forward = left = 0.0
        else:
            forward = -(y - cy) * scale * GAIN
            left = -(x - cx) * scale * GAIN

        print(f"t={spent:5.1f} метка {target:3d}  промах {miss:4.2f} м  "
              f"h≈{alt_by_side(side):4.2f} м  курс {math.degrees(turn_error(angle)):+4.0f}°"
              f"  → вперёд {forward:+5.2f} влево {left:+5.2f} вверх {up:+5.2f}", flush=True)

        # fly() сама молчит, если поправка вся в мёртвой зоне, — тогда паузу между
        # кадрами надо выдержать здесь, иначе цикл закрутится со скоростью камеры.
        if not fly(drone, forward, left, up, turn):
            time.sleep(FRAME_PAUSE)


# ═══════════════════════════════════════════════════════════════════════
#  ГЛАВНОЕ
# ═══════════════════════════════════════════════════════════════════════


def main():
    global SIDE_REF, ANGLE_REF

    drone = sverk_interfaces.init(Nodename="hold_aruco")
    patch_yuv(drone)          # до первого кадра, иначе кадров не будет вовсе
    try:
        print(f"ВЗЛЁТ на {ALT} м, держаться {HOLD_S:.0f} с, метка {MARKER_M} м", flush=True)
        # Отдельной команды takeoff в API нет: взлёт — это navigate вверх по корпусу.
        # auto_arm=True только здесь; она же переводит дрон в OFFBOARD.
        resp = drone.control.navigate(x=0.0, y=0.0, z=ALT, yaw=YAW, speed=CLIMB_SPEED,
                                      frame_id="body", auto_arm=True)
        print(f"взлёт: {getattr(resp, 'success', '?')} {getattr(resp, 'message', '')}",
              flush=True)
        if resp is not None and not getattr(resp, "success", True):
            raise RuntimeError("взлёт не принят — миссия отменена")
        time.sleep(ALT / CLIMB_SPEED + SETTLE_S)

        base = settle(drone)
        if base is None:
            # Держаться не за что: без метки нет ни цели, ни высоты, ни курса.
            raise RuntimeError("после взлёта не видно ни одной метки")

        target, SIDE_REF, ANGLE_REF = base
        print(f"ЦЕЛЬ: метка {target}, эталон {SIDE_REF:.0f} px на {ALT} м, "
              f"курс {math.degrees(ANGLE_REF):+.0f}°", flush=True)

        hold(drone, target, time.time())

    except FlightAborted as exc:
        print(f"ПОЛЁТ ПРЕКРАЩЁН: {exc}", flush=True)
    except KeyboardInterrupt:
        print("ОСТАНОВ С КЛАВИАТУРЫ", flush=True)
    except Exception as exc:
        print(f"ОШИБКА: {exc}", flush=True)
    finally:
        # Взлетели — обязаны сесть, чем бы ни кончился полёт.
        try:
            print("ПОСАДКА", flush=True)
            touch_down(drone)
        finally:
            drone.close()


if __name__ == "__main__":
    main()
