#!/usr/bin/env python3
"""Дрон-монитор: борт отвечает на команды диспетчера по сети.

Один файл. Копируется на дрон и запускается ВНУТРИ контейнера sverk_ros2:

    python3 drone_agent.py --port 8020 --name m1

Порт 8020 — внутри контейнера. Снаружи (с ноутбука, с другого борта) этот порт виден
как 2200: на дроне настроен постоянный проброс 2200 → 8020. Порт 80 внутри контейнера
не годится — занять его может только root, а мы работаем под sverk.

Проверка с ноутбука (адрес дрона подставить свой):

    curl http://192.168.1.50:2200/status
    curl -X POST http://192.168.1.50:2200/takeoff -d '{"alt":1.5}'
    curl http://192.168.1.50:2200/shot -o kadr.jpg
    curl -X POST http://192.168.1.50:2200/look -d '{"xy":[-0.7,-0.7],"alt":1.5}'
    curl -X POST http://192.168.1.50:2200/land

Что важно знать про этот файл (всё добыто на живом железе, не выдумано):

* Камера выданных бортов отдаёт bgr8 1280x960 — патч patch_yuv на них не нужен и
  оставлен страховкой под сборку, публикующую yuv422_yuy2: на такой штатный
  перевод в картинку падает и кадров не будет ни одного (sverh_snake/
  Archipelago2026/fly_head.py:173).
* navigate издаётся РОВНО ОДИН РАЗ на команду. Повторный вызов переинициализирует
  траекторию в контроллере, и дрон бесконечно начинает заход заново, никуда не летя.
  Отсюда же дедупликация по command_id: повтор POST по потерянному ответу не должен
  превращаться во второй navigate.
* auto_arm=True всегда: без него просевший и дизармившийся дрон уже не поднимется.
* get_telemetry на наших сборках виснет без полётного контроллера, а /status обязан
  отвечать всегда. Поэтому статус собирается из последней команды, а телеметрия —
  только по флагу --telemetry и только через поток со сроком (_telemetry).
* land() может вернуть успех и ничего не сделать, а на части сборок принимает
  timeout и без него бросает TypeError. Обе сигнатуры обёрнуты, посадка повторяется.
  Принятая команда — это ещё не посадка, поэтому состояний два: landed (подтверждено
  дизармом по телеметрии) и landed_unverified (команда принята, доказательств нет).
* Монитор летает только вокруг СВОЕЙ площадки: /look уводит его на точку обзора в
  метрах и возвращает на метку. Дальше --scan-radius от своей метки он не уйдёт, а
  без --allow-scan откажет и на это. Перелёт в чужую клетку (/goto) по-прежнему
  закрыт ключом --allow-goto. Причина ограничения: на рабочей высоте камера видит
  меньше, чем угол поля, поэтому отлетать нужно, а вот улетать — нет.
* Курс с --frame body дрон теряет сам, а yaw=0.0 его не держит: по документации это
  «не менять курс», то есть каждая команда закрепляет накопленный увод. Держим курс
  по метке своей площадки — так же, как это сделано в стенде hold_aruco/ и в
  прошлогоднем sverh_snake/Archipelago2026/fly_head.py. Выключается --no-yaw-hold.

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

VERSION = "1.2"

# Сколько последних command_id помнить, чтобы узнать повтор. Команд за попытку
# десятки, так что помним с запасом и всё равно не растём в памяти.
DEDUP_KEEP = 64

# Состояния, означающие «дрон не в воздухе». landed — посадка подтверждена
# телеметрией, landed_unverified — команда принята и пауза выждана, доказательств нет.
ON_GROUND = ("idle", "landed", "landed_unverified")

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
#  КУРС ПО МЕТКЕ
# ═══════════════════════════════════════════════════════════════════════════
#
# navigate(frame_id="body", yaw=0.0) курс НЕ держит: по документации это «не менять
# курс», а дрон на этой сборке потихоньку отворачивается сам — значит каждая команда
# закрепляет уже накопленный увод (sverh_snake/Archipelago2026/fly_head.py:72).
# Телеметрии, по которой курс видно всем остальным, у нас нет: get_telemetry виснет.
#
# Зато под монитором лежит метка его площадки, а метки поля уложены одинаково —
# поворот метки в кадре и показывает, как повёрнут сам дрон. Отсюда весь механизм:
# после взлёта запоминаем поворот метки (эталон курса), дальше каждой команде
# перелёта подмешиваем доворот к нему штатным аргументом yaw, а на долгом висении
# доворачиваем отдельным тактом. Ровно это делает стенд hold_aruco/hold_aruco.py.
#
# Всё это касается только --frame body. В aruco_map yaw — абсолютный курс в осях
# карты, там yaw=0.0 и есть удержание, а курс дрону считает бортовая локализация.

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


def marker_angle(frame) -> float | None:
    """Поворот ближайшей к центру кадра метки, радианы. None — метки не видно.

    Ближайшая к центру — та, над которой дрон и висит: своя площадка. Угол берётся
    по верхнему ребру квадрата. Вырожденные метки (сторона в один пиксель) отсеяны:
    у них углы шумят как попало.
    """
    import cv2
    import numpy as np

    dictionary, params, detector = _detector()
    if dictionary is None:
        return None
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if detector is not None:
        corners, ids, _ = detector.detectMarkers(gray)
    else:
        corners, ids, _ = cv2.aruco.detectMarkers(gray, dictionary, parameters=params)
    if ids is None or len(ids) == 0:
        return None

    cx, cy = frame.shape[1] / 2.0, frame.shape[0] / 2.0
    best = None
    for quad in corners:
        pts = np.asarray(quad, np.float32).reshape(-1, 2)
        x, y = pts.mean(axis=0)
        side = max(float(np.linalg.norm(pts[i] - pts[(i + 1) % 4])) for i in range(4))
        if side <= 1.0:
            continue
        away = math.hypot(float(x) - cx, float(y) - cy)
        if best is None or away < best[0]:
            edge = pts[1] - pts[0]
            best = (away, math.atan2(float(edge[1]), float(edge[0])))
    return best[1] if best is not None else None


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


def to_body(forward: float, left: float, error: float, dead_deg: float):
    """Вектор из осей поля в оси корпуса с учётом того, что дрон отвернуло.

    Смещение до точки обзора считается в осях ПОЛЯ (метры от центра поля), а команда
    с frame_id="body" уходит в осях корпуса. Пока дрон смотрит куда взлетал, это одно
    и то же; отвернувшийся дрон без этого поворота полетел бы вкось — тем сильнее,
    чем больше увод.
    """
    if abs(error) < math.radians(dead_deg):
        return forward, left
    c, s = math.cos(error), math.sin(error)
    return forward * c + left * s, -forward * s + left * c


# ═══════════════════════════════════════════════════════════════════════════
#  БОРТ
# ═══════════════════════════════════════════════════════════════════════════


class Job:
    """Одна исполняемая команда: её номер и флаг «тебя сменили».

    Нужен, потому что аварийная посадка вытесняет незаконченный взлёт, а тот в этот
    момент досыпает паузу набора высоты. Без номера проснувшийся взлёт дописал бы в
    статус «вишу» уже после команды на посадку — и оператор увидел бы в пульте
    летящий дрон вместо садящегося.
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
        self.pad = list(self.cell)  # своя площадка: от неё считается предел удаления
        self.xy = self.cell_to_m(self.cell)
        self.alt = 0.0
        # idle | taking_off | hover | landing | landed | landed_unverified
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
        # Курс: эталон снимается по метке после взлёта, drift — последний замер увода.
        self._yaw_ref: float | None = None
        self._yaw_drift: float | None = None
        self._yaw_warned = False

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
        if self.last_error:
            st["last_error"] = self.last_error
        if self.yaw_hold:
            # Градусы, а не радианы: это читает человек в пульте. yaw_ref = null
            # означает «курс держать не по чему», а не «курс ноль».
            st["yaw_ref"] = None if self._yaw_ref is None else round(math.degrees(self._yaw_ref))
            st["yaw_drift"] = (
                None if self._yaw_drift is None else round(math.degrees(self._yaw_drift))
            )
        if self.args.telemetry and self.drone is not None:
            tel, err = self._telemetry()
            if tel is None:
                st["telemetry_error"] = err
            else:
                st["telemetry"] = {k: getattr(tel, k, None) for k in ("x", "y", "z", "armed", "mode")}
        return st

    def _telemetry(self, timeout: float = 2.0):
        """Телеметрия со сроком: вернуть (данные, ошибка).

        По умолчанию выключена флагом --telemetry: на наших сборках вызов виснет без
        полётного контроллера. Поэтому даже включённая, она читается в отдельном
        потоке — зависший вызов не должен запирать ни /status, ни посадку. Поток
        останется висеть до конца работы агента; это дешевле, чем немой борт.
        """
        box: dict = {}

        def read():
            try:
                box["tel"] = self.drone.control.get_telemetry(frame_id="body")
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

    # --- курс ---------------------------------------------------------------

    @property
    def yaw_hold(self) -> bool:
        """Держим ли курс по метке.

        Только с --frame body: в aruco_map yaw это абсолютный курс в осях карты,
        удержание там уже встроено, и подмешивать к нему свой доворот — значит
        крутить дрон дважды.
        """
        return not self.args.no_yaw_hold and self.args.frame == "body"

    def _see_angle(self, what: str) -> float | None:
        """Поворот метки под дроном, радианы. None — нечем или не видно.

        Кадр берётся тем же путём, что и /shot, и через ту же очередь к железу:
        два потока на одном ROS-узле рвут wait set. Любой отказ здесь — не ошибка
        команды: не увидели метку, значит курс на этот раз не правим.
        """
        if self.dry or self.drone is None or not self.camera_ok:
            return None
        try:
            frame = self._hw(
                what, lambda: self.drone.image.take_picture(timeout=2.0), timeout=5.0
            )
        except Exception as exc:  # noqa: BLE001 — кадра нет, курс просто не правим
            say(f"курс: кадр не получен ({exc})")
            return None
        if frame is None or getattr(frame, "ndim", 0) != 3 or frame.size == 0:
            return None
        try:
            return marker_angle(frame)
        except Exception as exc:  # noqa: BLE001
            say(f"курс: метку разобрать не вышло ({exc})")
            return None

    def _set_yaw_ref(self) -> None:
        """Запомнить курс взлёта по метке. Метки не видно — курс держать не по чему."""
        if not self.yaw_hold or self.dry:
            return  # в заглушке нет ни камеры, ни курса, и врать про них незачем
        angle = self._see_angle("эталон курса")
        self._yaw_ref = angle
        self._yaw_drift = None if angle is None else 0.0
        self._yaw_warned = False
        if angle is None:
            say("курс: метки под дроном не видно — держать курс не по чему")
        else:
            say(f"курс: эталон {math.degrees(angle):+.0f}° (по метке своей площадки)")

    def _yaw_error(self) -> float | None:
        """Текущий увод от курса взлёта, радианы. None — замера нет или он негоден."""
        if not self.yaw_hold or self._yaw_ref is None:
            return None
        angle = self._see_angle("замер курса")
        if angle is None:
            return None
        error = turn_error(angle, self._yaw_ref, self.args.yaw_max)
        if error is None:
            if not self._yaw_warned:
                say(f"курс: поворот метки больше {self.args.yaw_max:g}° — дрон так не "
                    f"отворачивает. Похоже, сбой опознания метки; курс не правлю")
                self._yaw_warned = True
            return None
        self._yaw_drift = error
        return error

    def _yaw_turn(self) -> float:
        """Доворот, который надо подмешать в ближайший navigate, радианы."""
        error = self._yaw_error()
        if error is None:
            return 0.0
        turn = yaw_fix(error, self.args.yaw_dead, self.args.yaw_fix)
        if turn:
            say(f"курс: увод {math.degrees(error):+.0f}°, доворачиваю на "
                f"{math.degrees(turn):+.0f}°")
        return turn

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
                # состояние, чтобы следующая команда (например, возврат на метку)
                # прошла проверки.
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
        if self.state in ("taking_off", "hover"):
            # Повторная команда взлёта намеренно не доходит до navigate: второй вызов
            # переинициализирует траекторию, и дрон зависает, начиная заход заново.
            return {
                "accepted": True,
                "command": "takeoff",
                "note": "взлёт уже идёт или дрон в воздухе",
            }
        return self.start("takeoff", lambda job: self._takeoff(alt, job))

    def _takeoff(self, alt: float, job: Job) -> None:
        alt = min(float(alt), self.args.max_alt)
        self._set(job, state="taking_off")
        self.last_error = ""
        say(f"ВЗЛЁТ на {alt:g} м")
        if self.dry:
            wait = 2.0
        else:
            # Ровно один navigate: повторный вызов переинициализирует траекторию.
            resp = self._hw("взлёт", lambda: self.drone.control.navigate(
                x=0.0, y=0.0, z=alt, yaw=0.0,
                speed=self.args.climb_speed, frame_id="body", auto_arm=True,
            ), timeout=20.0)
            ok = getattr(resp, "success", True)
            say(f"взлёт принят: {ok} {getattr(resp, 'message', '')}")
            if resp is not None and not ok:
                raise NavRefused(f"взлёт не принят: {getattr(resp, 'message', '')}")
            # Ждём набор высоты плюс время на успокоение: командовать раскачанным
            # дроном нельзя, и кадр с качающегося борта смазан.
            wait = alt / max(self.args.climb_speed, 0.05) + self.args.settle
        # Высота записывается до паузы: если взлёт вытеснит аварийная посадка, дрон
        # всё равно уже пошёл вверх, и врать про ноль в статусе хуже, чем оценить.
        # А since_move отсчитывается от конца набора: «когда двигался в последний раз».
        self._set(job, alt=alt)
        if not self._wait(job, wait):
            say("взлёт прерван более важной командой — состояние не трогаю")
            return
        self._set(job, state="hover", moved=True)
        # Эталон курса снимается ЗДЕСЬ, после паузы на успокоение: замер на раскачке
        # испортил бы все довороты до конца полёта.
        self._set_yaw_ref()
        say(f"вишу на {alt:g} м")

    def land(self) -> dict:
        return self.start("land", self._land)

    def _land(self, job: Job) -> None:
        self._set(job, state="landing")
        # Эталон курса живёт ровно один полёт: следующий взлёт снимет свой. Сбрасываем
        # до посадки, чтобы фоновый доворот не крутил дрон, пока тот садится.
        self._yaw_ref, self._yaw_drift = None, None
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

    def goto(self, cell, alt: float) -> dict:
        if not self.args.allow_goto:
            raise Refused(
                "перелёт по полю запрещён: монитор снимает со своей площадки. "
                "Если это осознанно — запустите агент с ключом --allow-goto"
            )
        if self.state != "hover":
            raise Refused("перелёт до взлёта")
        return self.start("goto", lambda job: self._goto(cell, alt, job))

    def cell_to_m(self, cell) -> tuple[float, float]:
        """Клетка поля -> метры кадра aruco_map.

        Начало кадра aruco_map — центр квадрата из четырёх маркеров, а он же центр
        поля (docs/field-map/README.md). Поэтому центр клетки [col,row] на поле
        6x6 по 0,8 м это ((col-2.5)*0.8, (row-2.5)*0.8).
        """
        cols, rows = (int(v) for v in self.args.grid.split(","))
        size = self.args.cell_size
        return ((cell[0] - (cols - 1) / 2.0) * size, (cell[1] - (rows - 1) / 2.0) * size)

    def _goto(self, cell, alt: float, job: Job) -> None:
        x, y = self.cell_to_m(cell)
        alt = min(float(alt), self.args.max_alt)
        say(f"перелёт в клетку {list(cell)} = ({x:.2f}, {y:.2f}) м на {alt:g} м")
        if self._fly(x, y, alt, "перелёт", job):
            self.cell = [int(cell[0]), int(cell[1])]

    def look(self, xy, alt: float) -> dict:
        """Точка обзора: отлететь от своей метки на заданные метры и зависнуть.

        Так монитор осматривает свой угол поля: на рабочей высоте кадр уже, чем
        четверть поля. Возврат на метку — это тот же /look с её координатами.
        """
        if not self.args.allow_scan:
            raise Refused(
                "облёт запрещён: запустите агент с ключом --allow-scan, если это осознанно"
            )
        if self.state != "hover":
            raise Refused("точка обзора до взлёта")
        x, y = float(xy[0]), float(xy[1])
        px, py = self.cell_to_m(self.pad)
        away = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
        if away > self.args.scan_radius:
            # Предел не формальность: улетевший в чужой угол монитор — это чужая
            # площадка, чужой дрон в воздухе и потеря своей метки под камерой.
            raise Refused(
                f"точка ({x:.2f}, {y:.2f}) в {away:.2f} м от своей метки, "
                f"предел {self.args.scan_radius:g} м"
            )
        return self.start("look", lambda job: self._look(x, y, alt, job))

    def _look(self, x: float, y: float, alt: float, job: Job) -> None:
        alt = min(float(alt), self.args.max_alt)
        say(f"точка обзора ({x:.2f}, {y:.2f}) м на {alt:g} м")
        self._fly(x, y, alt, "точка обзора", job)

    def _fly(self, x: float, y: float, alt: float, what: str, job: Job) -> bool:
        """Один navigate до точки поля и пауза на долёт.

        navigate издаётся РОВНО ОДИН РАЗ: повторный вызов переинициализирует
        траекторию, и дрон бесконечно начинает заход заново.

        Кадр карты меток (`aruco_map`) требует живой локализации по меткам: если
        её нет, navigate отвечает «SpeedController initialization failed (TF
        error?)». Поэтому с `--frame body` та же точка поля пересчитывается в
        смещение от текущего места — в body координаты относительные, а z это
        приращение высоты, а не сама высота (docs/zmeyka.md).

        Там же, в body, к команде подмешивается доворот курса: сам по себе yaw=0.0
        курс не держит, а увод разворачивает и смещение — поэтому вектор ещё и
        поворачивается в оси корпуса.
        """
        if self.dry:
            wait = 2.0
        else:
            tx, ty, tz, turn = x, y, alt, 0.0
            if self.args.frame == "body":
                tx, ty, tz = x - self.xy[0], y - self.xy[1], alt - self.alt
                error = self._yaw_error()
                if error is not None:
                    tx, ty = to_body(tx, ty, error, self.args.yaw_dead)
                    turn = yaw_fix(error, self.args.yaw_dead, self.args.yaw_fix)
                say(f"{what}: смещаюсь на ({tx:+.2f}, {ty:+.2f}, {tz:+.2f}) м от себя"
                    + (f", доворот {math.degrees(turn):+.0f}°" if turn else ""))
            resp = self._hw(what, lambda: self.drone.control.navigate(
                x=tx, y=ty, z=tz, yaw=turn, speed=self.args.speed,
                frame_id=self.args.frame, auto_arm=True,
            ), timeout=20.0)
            if resp is not None and not getattr(resp, "success", True):
                raise NavRefused(f"{what} не принят: {getattr(resp, 'message', '')}")
            wait = self.args.hop_wait
        if not self._wait(job, wait):
            say(f"{what} прерван более важной командой — положение не переписываю")
            return False
        if not self._set(job, state="hover", alt=alt, moved=True):
            return False
        self.xy = (x, y)
        return True

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

    def stop(self) -> dict:
        """Аварийная остановка: для дрона это немедленная посадка.

        Команда вытесняет текущую. Прерванный взлёт или перелёт просыпается из паузы
        и уходит, не тронув состояние: иначе досыпающий взлёт написал бы «вишу» уже
        поверх посадки. Отменить сам navigate, который в этот момент отрабатывает
        полётный контроллер, отсюда нечем — на что похожа посадка поверх живого
        navigate у Сверх, проверяется только полётом (hold_aruco/README.md).
        """
        say("СТОП — сажусь")
        return self.start("stop-land", self._land, preempt=True)

    # --- курс на висении ----------------------------------------------------

    def _turn(self, turn: float, job: Job) -> None:
        """Один navigate «стой на месте, довернись»: только курс, без перемещения."""
        resp = self._hw("доворот", lambda: self.drone.control.navigate(
            x=0.0, y=0.0, z=0.0, yaw=float(turn), speed=self.args.speed,
            frame_id="body", auto_arm=True,
        ), timeout=20.0)
        if resp is not None and not getattr(resp, "success", True):
            raise NavRefused(f"доворот не принят: {getattr(resp, 'message', '')}")
        # Паузу выжидаем, но состояние не трогаем вовсе: дрон как висел, так и висит,
        # а since_move должен остаться «когда двигался», иначе доворот сам себе
        # отодвигает следующую проверку тишины.
        self._wait(job, self.args.yaw_wait)

    def keeper(self) -> None:
        """Доворачивать курс, пока дрон просто висит.

        Перелёты курс правят сами (поправка уходит в их же navigate), но между
        командами монитор висит над своей меткой минутами — и всё это время увод
        копится, ничем не отрабатываясь. Отсюда отдельный такт.

        Влезать в работу нельзя: доворот идёт только когда борт свободен И с
        последнего движения прошёл целый период. Иначе такт попадал бы ровно между
        «отлетел» и «снял кадр», и диспетчер получал бы 409 «занят» на свою команду.
        """
        period = self.args.yaw_period
        if period <= 0 or self.dry:
            return
        while True:
            time.sleep(min(period, 1.0))
            if not self.yaw_hold or self._yaw_ref is None:
                continue
            if self.state != "hover" or self._busy:
                continue
            if time.monotonic() - self._last_move < period:
                continue
            turn = self._yaw_turn()
            if not turn:
                continue
            try:
                self.start("yaw", lambda job, t=turn: self._turn(t, job))
            except Busy:
                # Между замером и командой борт успели занять — доворот не состоялся,
                # и молчать об этом нельзя: в логе уже стоит «доворачиваю».
                say("курс: борт занят, доворот отложен до следующего такта")

    # --- сторож -------------------------------------------------------------

    def touch(self) -> None:
        self._last_request = time.monotonic()

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
            aloft = self.state in ("taking_off", "hover") or (
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


class Refused(Exception):
    pass


class NoFrame(Exception):
    pass


class NavRefused(Exception):
    """Полётный контроллер не принял navigate — значит дрон никуда и не полетел.

    Отличается от прочих ошибок тем, что аппарат остался ровно там же и таким же:
    висел — висит, стоял — стоит. Поэтому состояние откатывается на то, что было
    до команды, а не становится «error». Иначе висящий дрон запирается в воздухе:
    look и goto требуют hover, и вернуть его на метку будет уже нечем.
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
            if self.path == "/goto":
                cell, alt = body["cell"], body.get("alt", self.agent.args.alt)
                return self._json(200, self.agent.once(cid, lambda: self.agent.goto(cell, alt)))
            if self.path == "/look":
                xy, alt = body["xy"], body.get("alt", self.agent.args.alt)
                return self._json(200, self.agent.once(cid, lambda: self.agent.look(xy, alt)))
            if self.path == "/stop":
                return self._json(200, self.agent.once(cid, self.agent.stop))
        except Busy as exc:
            return self._json(409, {"error": str(exc)})
        except Refused as exc:
            return self._json(403, {"error": str(exc)})
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
    p.add_argument("--alt", type=float, default=1.5, help="рабочая высота, м")
    p.add_argument("--max-alt", type=float, default=3.5, help="потолок, м (регламент 2.6: 4 м)")
    p.add_argument("--climb-speed", type=float, default=0.3, help="скорость набора высоты, м/с")
    p.add_argument("--speed", type=float, default=0.6, help="скорость перелёта, м/с")
    p.add_argument("--settle", type=float, default=2.5, help="пауза на успокоение после взлёта, с")
    p.add_argument("--land-wait", type=float, default=4.0, help="пауза на снижение, с")
    p.add_argument("--hop-wait", type=float, default=6.0, help="пауза на перелёт, с")
    p.add_argument("--watchdog", type=float, default=20.0, help="сесть, если нет команд N с (0 — выкл)")
    p.add_argument(
        "--frame", default="aruco_map",
        help="кадр координат для перелётов: aruco_map (нужна локализация по меткам) "
             "или body (смещение от текущего места, без карты)",
    )
    p.add_argument("--grid", default="6,6", help="размер поля в клетках")
    p.add_argument("--cell-size", type=float, default=0.8, help="сторона клетки, м")
    p.add_argument("--allow-goto", action="store_true", help="разрешить перелёты по полю")
    p.add_argument("--allow-scan", action="store_true", help="разрешить облёт вокруг своей метки")
    p.add_argument(
        "--scan-radius", type=float, default=1.0,
        help="дальше этого от своей метки при облёте не улетать, м",
    )
    p.add_argument(
        "--no-yaw-hold", action="store_true",
        help="не держать курс по метке (по умолчанию держим, но только с --frame body)",
    )
    p.add_argument("--yaw-dead", type=float, default=3.0,
                   help="увод меньше этого не трогаем: шум опознания метки, град")
    p.add_argument("--yaw-fix", type=float, default=15.0,
                   help="предел доворота за одну команду, град")
    p.add_argument("--yaw-max", type=float, default=45.0,
                   help="увод больше этого — сбой опознания метки, а не поворот дрона, град")
    p.add_argument("--yaw-period", type=float, default=8.0,
                   help="как часто доворачивать курс на висении, с (0 — не доворачивать)")
    p.add_argument("--yaw-wait", type=float, default=2.0, help="пауза на доворот, с")
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
    threading.Thread(target=agent.keeper, daemon=True).start()

    if agent.yaw_hold:
        say(f"курс держу по метке: раз в {args.yaw_period:g} с на висении"
            if args.yaw_period > 0 else "курс держу по метке: только в командах перелёта")
    elif not args.no_yaw_hold:
        say(f"курс по метке не держу: с --frame {args.frame} его держит бортовая локализация")
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
