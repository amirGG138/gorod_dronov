#!/usr/bin/env python3
"""Пульт РОВЕРА: короткие команды вместо веб-морды и curl.

    python3 rovPult.py --ip 192.168.1.125

Наземный инструмент оператора, а не часть зачётной попытки: в попытке роверу
командует диспетчер (`python3 -m city.run`) через `onboard/rover_agent.py`.
Здесь — руки: проверить железо, подвигать ровер, снять кадр, помигать лентой.

Команды:

    п                проверить системы: связь, Nav2, ЛИДАР, ноды ROS, камера,
                     одометрия, батарея, карта, температура
    н [x y [курс]]   поднять навигацию: завести мотор лидара, активировать ноды
                     Nav2 и задать AMCL начальную позу. Повторять после каждой
                     перезагрузки борта. Без координат поза ставится в (0,0,0) —
                     Nav2 поднимется, но считать себя ровер будет в начале карты
    о <x> <y>        переехать на x, y метров ОТНОСИТЕЛЬНО СЕБЯ через Nav2
                     (x вперёд, y влево), курс не меняя
    е <x> <y> <w> [м] ехать вручную: скорости м/с и рад/с, пока не пройдёт столько
                     МЕТРОВ по одометрии (поворот на месте меряется в радианах).
                     Работает БЕЗ Nav2 — этим ровер двигают, пока навигация лежит
    л on|blink|off   лента
    к [файл]         снять кадр с камеры в файл
    м [имя|стоп]     маршруты: без имени — список, с именем — запустить
    стоп             немедленная остановка
    q                остановить и выйти

Работает НАПРЯМУЮ с ровером, минуя нашего агента. Два его сетевых API:

* `rover_control_api` на `:8767` — лиз управления и цели Nav2 в метрах карты.
  Лиз, продление и отказы переиспользуются из `onboard/rover_agent.py`: второй
  копии этой механики в репозитории быть не должно.
* `rover_web` на `:8765` (он же на `:80` — та же морда, что открывается по
  `http://<ip>/`) — всё остальное: ручная езда, лента, камера, лидар, граф ROS,
  маршруты, стоп. Разобрано по `assets/app.js` живой морды 2026-07-29.

Про «относительно себя». Nav2 принимает цель в метрах СВОЕЙ карты, поэтому пульт
читает позу (x, y, yaw) и сам поворачивает смещение в оси карты. Клетки поля тут
ни при чём — это пульт, а не миссия; сетку калибрует агент.

Нужна только стандартная библиотека.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "onboard"))
from rover_agent import (  # noqa: E402  — путь дописан выше
    ControlApiBackend, RoverLinkError, RoverRefused, _http as http_json,
)

if hasattr(sys.stdout, "reconfigure"):  # кириллица в консоли Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HELP = """
Команды:
  п                  проверить системы (связь, Nav2, лидар, ноды, камера, АКБ)
  н                  поднять навигацию: лидар, ноды Nav2, начальная поза AMCL
  н <x> <y> [курс]   то же, но сказать AMCL, где ровер стоит на карте
  н сброс            то же плюс глобальный сброс локализации AMCL
  о <x> <y>          переехать через Nav2 на x вперёд, y влево (метры, от себя)
  е <x> <y> <w> [м]  ехать вручную: м/с вперёд, м/с влево, рад/с поворот, сколько метров
  л on|blink|off     лента
  к [файл]           снять кадр с камеры
  м [имя|стоп]       маршруты: список / запустить / остановить
  стоп               немедленная остановка
  ?                  эта подсказка
  q                  остановить и выйти

  Ctrl+C             прервать ожидание (ровер тормозится); на пустой строке — выход
"""

# Топики, по которым проверяются системы (имена сверены по графу ROS живого ровера).
LIDAR_RAW = ("/scan", "sensor_msgs/msg/LaserScan")
LIDAR_NAV = ("/scan_filtered", "sensor_msgs/msg/LaserScan")  # именно он едет в Nav2
ODOM = ("/odom", "nav_msgs/msg/Odometry")
BATTERY = ("/battery_voltage", "std_msgs/msg/Float32")
CAMERA = ("/image_raw/compressed", "sensor_msgs/msg/CompressedImage")

# Предел одного поворота на месте, рад: полный оборот. Для езды предел свой — ключ
# --max-dist в метрах; здесь константа, потому что крутиться дольше оборота незачем.
MAX_TURN = 6.3

# Ноды, без которых ровер либо не поедет, либо не увидит. Их отсутствие в графе —
# самый быстрый способ поймать упавший драйвер: веб-морда при этом бодрая.
KEY_NODES = {
    "base_driver_node": "драйвер моторов (без него ровер не тронется)",
    "sllidar_node": "лидар",
    "usb_camera_node": "камера",
    "led_strip_node": "лента",
    "twist_mux": "мультиплексор скоростей",
    "amcl": "локализация по карте",
    "bt_navigator": "Nav2",
    "controller_server": "Nav2",
}


# Ноды Nav2 — автоматы жизненного цикла: рабочее состояние «active», всё
# остальное значит, что менеджер их не поднял. Порядок как в цепочке запуска.
NAV_NODES = (
    "/map_server", "/amcl",
    "/global_costmap/global_costmap", "/local_costmap/local_costmap",
    "/planner_server", "/controller_server", "/bt_navigator", "/behavior_server",
)


def say(text: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
#  ВЕБ-МОРДА РОВЕРА
# ═══════════════════════════════════════════════════════════════════════════


def topic(web: str, name: str, kind: str, timeout: float = 6.0) -> dict:
    """Снимок ROS-топика через rover_web.

    ВАЖНО: первый запрос только СОЗДАЁТ подписку — сообщений в нём нет никогда
    (latest_message=null, message_count=0). Проверено на живом ровере 2026-07-29:
    решать «топик молчит» по первому ответу — значит ошибиться на всех сразу.
    Поэтому спрашиваем дважды, между ними пауза.
    """
    try:
        http_json(f"{web}/api/ros/topic?name={name}&type={kind}", timeout=timeout)
        time.sleep(1.2)
        return http_json(f"{web}/api/ros/topic?name={name}&type={kind}", timeout=timeout)
    except RoverLinkError as exc:
        return {"error": str(exc)}


def alive(snap: dict) -> bool:
    """Топик не просто объявлен, а реально сыплет: есть сообщения и они свежие."""
    if snap.get("error") or not snap.get("publishers"):
        return False
    age = snap.get("age_sec")
    return bool(snap.get("message_count")) and age is not None and age < 2.0


def grab_frame(web: str, url_topic: str, kind: str, timeout: float = 12.0) -> bytes:
    """Один кадр из MJPEG-потока веб-морды: читаем поток до конца первой картинки."""
    url = f"{web}/api/camera/stream?topic={url_topic}&type={kind}&t={int(time.time())}"
    buf = b""
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            chunk = resp.read(4096)
            if not chunk:
                break
            buf += chunk
            start = buf.find(b"\xff\xd8")           # начало JPEG
            stop = buf.find(b"\xff\xd9", start + 2)  # конец JPEG
            if start >= 0 and stop > start:
                return buf[start:stop + 2]
    raise RoverLinkError("камера не отдала целый кадр")


# ═══════════════════════════════════════════════════════════════════════════
#  ПРОВЕРКА СИСТЕМ  («п»)
# ═══════════════════════════════════════════════════════════════════════════


def check_lidar(web: str) -> bool:
    """Лидар — глаза Nav2: без него ровер не поедет ни по какой карте.

    Смотрим не на «есть ли издатель», а на счётчик сообщений: 2026-07-29 у обоих
    топиков издатель был, а сообщений ноль — мотор дальномера не крутился (лечится
    командой «н»).

    Судим при этом ТОЛЬКО по сырому /scan. Отфильтрованный `/scan_filtered` через
    веб-морду не виден никогда: она подписывается так, что не получает топики с
    сенсорным QoS — ровно та же картина у `/map` и `/amcl_pose`, которые заведомо
    публикуются. Считать это «фильтр молчит» — ложная тревога; работает ли фильтр,
    видно по тому, поднялась ли костмапа, то есть по готовности Nav2.
    """
    ok = True
    for name, kind in (LIDAR_RAW, LIDAR_NAV):
        try:
            st = http_json(f"{web}/api/lidar/status?topic={name}&type={kind}", timeout=6.0)
        except RoverLinkError as exc:
            say(f"  лидар {name}: НЕТ ОТВЕТА ({exc})")
            ok = False
            continue
        count, age = st.get("message_count") or 0, st.get("age_sec")
        if not count or not st.get("frame_ready"):
            if name == LIDAR_NAV[0]:
                # Не тревога: этот топик веб-морда не показывает в принципе (см. докстринг).
                say(f"  лидар {name}: через веб не виден (сенсорный QoS) — "
                    "судить по готовности Nav2")
                continue
            say(f"  лидар {name}: МОЛЧИТ (сообщений {count}, кадр готов "
                f"{st.get('frame_ready')}) — мотор не крутится, поднимите командой «н»")
            ok = False
            continue
        pts = st.get("points") or []
        dist = [math.hypot(p[0], p[1]) if isinstance(p, (list, tuple)) else None for p in pts]
        dist = [d for d in dist if d]
        say(f"  лидар {name}: {st.get('valid_points')} годных из {st.get('total_ranges')} "
            f"лучей, свежесть {age:.2f} с"
            + (f", ближайшее препятствие {min(dist):.2f} м" if dist else ""))
        if not st.get("valid_points"):
            ok = False
    return ok


def check_nodes(web: str) -> list[str]:
    """Граф ROS: какие ключевые ноды живы. Возвращает список пропавших."""
    try:
        graph = http_json(f"{web}/api/ros/graph", timeout=8.0)
    except RoverLinkError as exc:
        say(f"  граф ROS: НЕТ ОТВЕТА ({exc})")
        return ["граф ROS недоступен"]
    names = {n if isinstance(n, str) else n.get("name", "") for n in graph.get("nodes") or []}
    names = {n.lstrip("/") for n in names}
    lost = [f"{node} — {what}" for node, what in KEY_NODES.items() if node not in names]
    say(f"  граф ROS: {len(names)} нод, топиков {len(graph.get('topics') or [])}")
    for line in lost:
        say(f"    НЕТ НОДЫ {line}")
    return lost


def check(rover, web: str, min_volt: float) -> None:
    """«п» — сводка по системам ровера и честный вывод, можно ли ехать."""
    say("проверяю ровер")
    beefs: list[str] = []

    # 1. Управление и навигация — то же чтение, что делает агент.
    snap = rover.read()
    if not snap["link"]:
        say("  rover_control_api :8767 НЕ ОТВЕЧАЕТ — ровер выключен или не в сети?")
        return say("ИТОГ: ехать нельзя, связи нет")
    say("  rover_control_api :8767: отвечает")
    if snap["pose"]:
        x, y, yaw = snap["pose"]
        say(f"  поза: x={x:.2f} y={y:.2f} курс={yaw:.0f}° во фрейме «{snap['frame_id']}»")
    else:
        say("  поза: НЕТ")
        beefs.append("ровер не знает, где он")
    if snap["nav_ready"]:
        say("  Nav2: готов")
    else:
        say("  Nav2: НЕ ПОДНЯТ (nav2_ready=false) — команда «о» работать не будет, "
            "ручная езда «е» будет")
        beefs.append("Nav2 не готов")
    if snap["frame_id"] and snap["frame_id"] != "map":
        beefs.append(f"поза во фрейме «{snap['frame_id']}», а не «map» — локализация не сошлась")

    # 2. Веб-морда: она же источник температуры, стопа, ленты и камеры.
    try:
        st = http_json(f"{web}/api/status", timeout=5.0)
        sysinfo, ident = st.get("system") or {}, st.get("identity") or {}
        say(f"  rover_web: отвечает ({ident.get('hostname')}, {ident.get('model')}, "
            f"версия {ident.get('software_version')})")
        say(f"  система: CPU {sysinfo.get('cpu_percent', 0):.0f}%, "
            f"температура {sysinfo.get('temperature_c')}°C, "
            f"аптайм {sysinfo.get('uptime_sec', 0) / 60:.0f} мин, "
            f"throttled={sysinfo.get('throttled')}")
    except RoverLinkError as exc:
        say(f"  rover_web: НЕ ОТВЕЧАЕТ ({exc}) — не будет ни ленты, ни стопа, ни камеры")
        beefs.append("rover_web не отвечает")

    # 3. Ноды и лидар.
    if check_nodes(web):
        beefs.append("в графе нет ключевых нод")
    if not check_lidar(web):
        beefs.append("лидар не даёт данных")

    # 4. Одометрия: ровно этим ловится упавший драйвер моторов — веб при этом
    #    выглядит здоровым, а колёса не крутятся.
    od = topic(web, *ODOM)
    if alive(od):
        pos = (((od.get("latest_message") or {}).get("pose") or {}).get("pose") or {}).get("position") or {}
        say(f"  одометрия /odom: идёт (x={pos.get('x', 0):.2f} y={pos.get('y', 0):.2f})")
    else:
        say(f"  одометрия /odom: МОЛЧИТ ({od.get('error') or 'нет сообщений'}) — "
            "похоже, упал base_driver_node, перезапустите bringup")
        beefs.append("нет одометрии")

    # 5. Камера.
    try:
        cam = http_json(f"{web}/api/camera/status?topic={CAMERA[0]}&type={CAMERA[1]}", timeout=6.0)
        if cam.get("message_count"):
            say(f"  камера {CAMERA[0]}: кадры идут ({cam.get('message_count')} шт)")
        else:
            say(f"  камера {CAMERA[0]}: кадров нет")
            beefs.append("камера молчит")
    except RoverLinkError as exc:
        say(f"  камера: нет ответа ({exc})")

    # 6. Карта, по которой Nav2 вообще может ехать.
    try:
        maps = (http_json(f"{web}/api/maps", timeout=5.0).get("maps") or [])
        if maps:
            m = maps[0]
            say(f"  карта: «{m.get('name')}» {m.get('width_m')}×{m.get('height_m')} м, "
                f"шаг {m.get('resolution')} м")
        else:
            say("  карта: НЕТ ни одной — Nav2 ехать не по чему")
            beefs.append("нет карты")
    except RoverLinkError:
        pass

    # 7. Батарея. Процентов ровер не даёт вовсе, только вольты; порог — наш ключ,
    #    а не паспорт, поэтому так и пишем.
    bat = topic(web, *BATTERY)
    volt = (bat.get("latest_message") or {}).get("data") if alive(bat) else None
    if volt is None:
        say("  батарея: напряжения нет (никто не публикует /battery_voltage)")
        beefs.append("напряжение АКБ неизвестно")
    elif volt < min_volt:
        say(f"  батарея: {volt:.2f} В — НИЖЕ порога {min_volt:g} В (порог из --min-volt, "
            "не паспортный: процентов ровер не публикует)")
        beefs.append(f"низкое напряжение {volt:.2f} В")
    else:
        say(f"  батарея: {volt:.2f} В")

    say("ИТОГ: все системы отвечают, можно ехать" if not beefs
        else "ИТОГ: с оговорками — " + "; ".join(beefs))


# ═══════════════════════════════════════════════════════════════════════════
#  ДВИЖЕНИЕ
# ═══════════════════════════════════════════════════════════════════════════


def move(rover, dx: float, dy: float, tol: float, timeout: float) -> None:
    """«о x y» — переезд через Nav2 на dx вперёд и dy влево от текущего места."""
    snap = rover.read(with_battery=False)
    if not snap["link"]:
        return say("ровер не отвечает")
    if not snap["pose"]:
        return say("ровер не знает своей позы — ехать некуда")
    x, y, yaw_deg = snap["pose"]
    yaw = math.radians(yaw_deg)
    # Поворот смещения из осей корпуса в оси карты: x вперёд, y влево.
    tx = x + dx * math.cos(yaw) - dy * math.sin(yaw)
    ty = y + dx * math.sin(yaw) + dy * math.cos(yaw)
    say(f"сдвиг на ({dx:+.2f}, {dy:+.2f}) м от себя: ({x:.2f}, {y:.2f}) -> "
        f"({tx:.2f}, {ty:.2f}) м карты, курс {yaw_deg:.0f}° оставляю")

    request_id = f"pult-{int(time.time())}"
    try:
        rover.goal(tx, ty, yaw_deg, request_id)  # он же проверит Nav2 и возьмёт лиз
    except RoverRefused as exc:
        return say(f"ОТКАЗ: {exc}\n           пока Nav2 лежит, двигайте ровер командой «е»")
    except RoverLinkError as exc:
        return say(f"НЕ ПРИНЯТО: {exc}")

    # Прибытие — по фактической позе, а не по слову «принято»: Nav2 умеет отдать
    # цель и не доехать, а на «отменено» уже стоять у цели (docs/openclaw/03).
    end = time.monotonic() + timeout
    try:
        while time.monotonic() < end:
            state = str(rover.nav_status().get("state", "")).lower()
            here = rover.read(with_battery=False)["pose"]
            if here and math.hypot(here[0] - tx, here[1] - ty) <= tol:
                return say(f"приехал: ({here[0]:.2f}, {here[1]:.2f}) м, курс {here[2]:.0f}°")
            if state not in ("sending", "accepted", "navigating", "executing", "active"):
                left = math.hypot(here[0] - tx, here[1] - ty) if here else float("nan")
                return say(f"Nav2 закончил в состоянии «{state}», до цели {left:.2f} м")
            time.sleep(0.3)
        say(f"не доехал за {timeout:g} с — отменяю цель")
    except KeyboardInterrupt:
        say("прервано с клавиатуры — отменяю цель и торможу")
        rover.hard_stop()
    finally:
        rover.cancel(request_id)  # он же отпускает лиз


def pose_of(rover) -> tuple[float, float, float] | None:
    """Поза из `/v1/state`. Это одометрия ровера, она есть и когда Nav2 лежит."""
    snap = rover.read(with_battery=False)
    return snap["pose"] if snap["link"] else None


def step(a: tuple, b: tuple, turning: bool) -> float:
    """Прибавка пути между двумя позами: метры, а при повороте на месте — радианы."""
    if turning:
        d = math.radians(b[2] - a[2])
        return abs(math.atan2(math.sin(d), math.cos(d)))  # переход через ±180° тоже верен
    return math.hypot(b[0] - a[0], b[1] - a[1])


def drive(rover, web: str, vx: float, vy: float, wz: float, target: float, limits: dict,
          max_dist: float) -> None:
    """«е x y w м» — ручная езда скоростями через веб-морду, без Nav2, на заданный путь.

    Едем не «столько-то секунд», а пока одометрия не покажет заданный путь: секунды
    врут (буксует колесо, просел АКБ, ковёр), метры — нет. Путь набирается кусками
    между соседними замерами позы, поэтому дуга (vx вместе с wz) считается по дуге.
    Если заданы только поворотные скорости, целью становится угол в радианах.

    Команда на борту живёт 0,25 с (`drive_command_timeout_sec` из /api/config),
    поэтому едем не одним запросом, а потоком по 10 Гц: оборвётся пульт или сеть —
    ровер встанет сам. Скорости режутся потолком пульта (--max-speed для линейных,
    предел морды для поворота) — что борт из этого реально отработает, решает он сам.
    """
    lim = lambda v, k: max(-limits.get(k, 0.35), min(limits.get(k, 0.35), v))  # noqa: E731
    vx, vy, wz = lim(vx, "linear_x"), lim(vy, "linear_y"), lim(wz, "angular_z")
    speed, spin = math.hypot(vx, vy), abs(wz)
    turning = speed < 0.02 and spin > 0.0  # с места не трогаемся — значит, меряем угол
    rate = spin if turning else speed
    if rate < 1e-3:
        return say("скорости нулевые — ехать некуда")
    unit = "рад" if turning else "м"
    target = min(abs(target), MAX_TURN if turning else max_dist)

    start = prev = pose_of(rover)
    if start is None:
        say(f"ПОЗЫ НЕТ ({rover.ctrl} молчит или одометрия стоит) — путь мерить нечем, "
            f"еду по расчёту времени. Сколько ровер проедет на самом деле, пульт не знает")
    say(f"еду вручную: вперёд {vx:+.2f} м/с, влево {vy:+.2f} м/с, "
        f"поворот {wz:+.2f} рад/с, пока не пройду {target:g} {unit}")

    gone, reason = 0.0, "дошёл до цели"
    began = time.monotonic()
    guard = began + target / rate * 3.0 + 2.0  # страховка: столько ехать уже некуда
    try:
        while True:
            http_json(f"{web}/api/drive/command",
                      {"linear_x": vx, "linear_y": vy, "angular_z": wz}, timeout=3.0)
            time.sleep(0.1)
            elapsed = time.monotonic() - began
            if start is None:
                gone = rate * elapsed  # позы нет: остаётся считать по скорости
            else:
                now = pose_of(rover)
                if now and prev:
                    gone += step(prev, now, turning)
                    prev = now
                # Одометрия идёт, а путь не растёт — самый частый отказ ровера:
                # веб-морда бодрая, а base_driver_node лежит и колёса стоят.
                if elapsed > 2.0 and gone < 0.15 * rate * elapsed:
                    reason = "ровер НЕ ЕДЕТ (путь не растёт) — проверьте base_driver_node"
                    break
            if gone >= target:
                break
            if time.monotonic() > guard:
                reason = f"страховка по времени, {elapsed:.1f} с"
                break
    except RoverLinkError as exc:
        reason = f"езда прервана: {exc}"
    except KeyboardInterrupt:
        reason = "прервано с клавиатуры"
    finally:
        try:
            http_json(f"{web}/api/drive/stop", {}, timeout=3.0)
        except RoverLinkError as exc:
            say(f"СТОП НЕ ПРОШЁЛ: {exc} — жмите аварийную кнопку")
        else:
            time.sleep(0.4)  # накат: колёса встают не мгновенно, добираем хвост пути
            last = pose_of(rover) if start else None
            if last and prev:
                gone += step(prev, last, turning)
            say(f"стою, прошёл {gone:.2f} {unit} из {target:g} — {reason}")


# ═══════════════════════════════════════════════════════════════════════════
#  ОСТАЛЬНЫЕ КОМАНДЫ ВЕБ-МОРДЫ
# ═══════════════════════════════════════════════════════════════════════════


def led(rover, mode: str, color: str, brightness: float, speed: float) -> None:
    effect = {"on": "fill", "blink": "blink", "off": "fill"}.get(mode)
    if effect is None:
        return say("режимы ленты: on, blink, off")
    try:
        rover.led(enabled=(mode != "off"), effect=effect, brightness=brightness,
                  speed=speed, primary=color, secondary="#000000")
    except RoverLinkError as exc:
        return say(f"лента не приняла команду: {exc}")
    say(f"лента: {mode}")


def shot(web: str, path: str) -> None:
    """«к» — кадр с камеры ровера в файл (та же картинка, что в веб-морде)."""
    try:
        data = grab_frame(web, *CAMERA)
        with open(path, "wb") as f:  # путь тоже внутри try: кривой путь не повод падать
            f.write(data)
    except (RoverLinkError, urllib.error.URLError, OSError) as exc:
        return say(f"кадр не снят: {exc}")
    say(f"кадр сохранён: {path} ({len(data) / 1024:.0f} КБ)")


def service(web: str, name: str, kind: str, request: dict | None = None,
            timeout: float = 25.0) -> dict:
    """Вызов ROS-сервиса через веб-морду — тем же путём, что делает её вкладка «ROS»."""
    return http_json(f"{web}/api/ros/service/call",
                     {"service": name, "type": kind, "request": request or {}}, timeout=timeout)


def lifecycle(web: str, node: str) -> str:
    """Состояние lifecycle-ноды: active / inactive / unconfigured."""
    try:
        resp = service(web, f"{node}/get_state", "lifecycle_msgs/srv/GetState", timeout=10.0)
    except RoverLinkError as exc:
        return f"нет ответа ({exc})"
    return ((resp.get("response") or {}).get("current_state") or {}).get("label", "?")


def activate(web: str, node: str) -> str:
    """Поднять одну ноду Nav2. Судим по состоянию ПОСЛЕ, а не по ответу сервиса.

    Проверено 2026-07-29: активация костмапы отвечает `success: false` (а по HTTP и
    вовсе 503 по таймауту), потому что переход длится дольше ответа, — и при этом
    нода оказывается `active`. Верить ответу здесь значит бросить работу на полпути.
    """
    was = lifecycle(web, node)
    if was == "active":
        return was
    try:
        if was == "unconfigured":
            service(web, f"{node}/change_state", "lifecycle_msgs/srv/ChangeState",
                    {"transition": {"id": 1, "label": "configure"}}, timeout=45.0)
            time.sleep(1.0)
        service(web, f"{node}/change_state", "lifecycle_msgs/srv/ChangeState",
                {"transition": {"id": 3, "label": "activate"}}, timeout=45.0)
    except RoverLinkError:
        pass  # 503/таймаут — не приговор, состояние скажет правду
    return lifecycle(web, node)


def set_pose(web: str, x: float, y: float, yaw_deg: float) -> bool:
    """Сказать AMCL, где ровер стоит. Без этого он не публикует map->odom.

    А без map->odom не поднимается global_costmap (она живёт во фрейме map), за ней
    planner_server, и Nav2 не готов. Это и есть корень «поза во фрейме odom».
    """
    yaw = math.radians(yaw_deg)
    cov = [0.0] * 36
    cov[0] = cov[7] = 0.25      # разброс по x и y, м²
    cov[35] = 0.0685            # разброс по курсу, рад²
    req = {"pose": {"header": {"frame_id": "map"},
                    "pose": {"pose": {"position": {"x": x, "y": y, "z": 0.0},
                                      "orientation": {"x": 0.0, "y": 0.0,
                                                      "z": math.sin(yaw / 2),
                                                      "w": math.cos(yaw / 2)}},
                             "covariance": cov}}}
    try:
        service(web, "/set_initial_pose", "nav2_msgs/srv/SetInitialPose", req, timeout=15.0)
    except RoverLinkError as exc:
        say(f"  начальную позу задать не удалось: {exc}")
        return False
    return True


def nav_up(rover, web: str, relocalize: bool, start: tuple | None = None) -> None:
    """«н» — поднять навигацию: лидар, ноды Nav2 и начальная поза AMCL.

    Порядок разобран на живом ровере 2026-07-29, из состояния «nav2_ready=false,
    поза во фрейме odom». Три причины, каждая из которых сама по себе валит Nav2:

    1. мотор лидара после включения борта не крутится — `/start_motor`;
    2. `lifecycle_manager` поднимает ноды пачкой и сдаётся целиком, если хоть одна
       не встала, поэтому оставшиеся приходится активировать поштучно;
    3. AMCL без начальной позы не публикует `map->odom`, а без этого фрейма не
       поднимается `global_costmap` (она живёт в map), за ней `planner_server` —
       и Nav2 не готов. Отсюда и «поза во фрейме odom»: это следствие, а не причина.

    Поэтому костмапа и планировщик поднимаются ПОСЛЕ задания позы, а не до.
    Повторять после каждой перезагрузки борта.
    """
    # Сначала связь: без неё вся команда — это полтора десятка таймаутов подряд,
    # четыре минуты молчания вместо одной внятной строки.
    try:
        http_json(f"{web}/api/status", timeout=5.0)
    except RoverLinkError as exc:
        return say(f"ровер не отвечает ({exc}) — поднимать нечего")

    say("1/5 завожу мотор лидара")
    try:
        service(web, "/start_motor", "std_srvs/srv/Empty")
    except RoverLinkError as exc:
        say(f"  /start_motor не прошёл: {exc}")
    time.sleep(3.0)

    # Смотрим только сырой /scan: отфильтрованный через веб-морду не виден никогда
    # (сенсорный QoS, см. check_lidar), и «молчит» про него — ложная тревога.
    say("2/5 смотрю скан")
    try:
        st = http_json(f"{web}/api/lidar/status?topic={LIDAR_RAW[0]}&type={LIDAR_RAW[1]}",
                       timeout=6.0)
        say(f"  {LIDAR_RAW[0]}: " + (
            f"идёт, годных {st.get('valid_points')}/{st.get('total_ranges')}"
            if st.get("message_count") and st.get("frame_ready") else
            "МОЛЧИТ даже после /start_motor — смотрите лидар, дальше Nav2 не поднимется"))
    except RoverLinkError as exc:
        say(f"  {LIDAR_RAW[0]}: нет ответа ({exc})")

    say("3/5 прошу менеджеры поднять Nav2")
    for manager in ("/lifecycle_manager_localization/manage_nodes",
                    "/lifecycle_manager_navigation/manage_nodes"):
        try:
            resp = service(web, manager, "nav2_msgs/srv/ManageLifecycleNodes", {"command": 0},
                           timeout=45.0)
            ok = (resp.get("response") or {}).get("success")
        except RoverLinkError as exc:
            ok = f"нет ответа ({exc})"
        say(f"  {manager.split('/')[1]}: {'поднят' if ok is True else f'не справился ({ok})'}")

    # Менеджер сдаётся весь целиком, если хоть одна нода не встала, поэтому дальше
    # поднимаем поштучно. Порядок важен: костмапа и планировщик идут последними —
    # им нужен фрейм map, то есть уже работающий AMCL.
    say("4/5 поднимаю ноды по одной")
    for node in ("/behavior_server", "/bt_navigator", "/waypoint_follower"):
        say(f"    {node:34} {activate(web, node)}")

    snap = rover.read(with_battery=False)
    if snap["link"] and snap["frame_id"] != "map":
        x, y, yaw = start if start else (0.0, 0.0, 0.0)
        if start:
            say(f"  говорю AMCL, что ровер стоит в ({x:g}, {y:g}) м карты, курс {yaw:g}°")
        else:
            say("  ВНИМАНИЕ: ставлю начальную позу (0, 0, 0°) — это НЕ настоящее место")
            say("    ровера, а лишь точка отсчёта, чтобы AMCL начал публиковать map->odom.")
            say("    Пока не уточните («н x y курс» или карта в веб-морде), Nav2 повезёт")
            say("    ровер не туда: он считает себя в начале карты.")
        set_pose(web, x, y, yaw)
        time.sleep(3.0)
    for node in ("/global_costmap/global_costmap", "/planner_server"):
        say(f"    {node:34} {activate(web, node)}")

    if relocalize:
        # Глобальная релокализация рассыпает частицы по всей карте: сошедшуюся позу
        # она СБИВАЕТ, поэтому только по явной просьбе — «н сброс».
        say("сбрасываю локализацию AMCL — дальше ровер надо немного покатать, чтобы сошлась")
        try:
            service(web, "/reinitialize_global_localization", "std_srvs/srv/Empty")
        except RoverLinkError as exc:
            say(f"  не прошло: {exc}")

    say("5/5 итог")
    snap = rover.read(with_battery=False)
    if not snap["link"]:
        return say("  rover_control_api молчит")
    if snap["nav_ready"] and snap["frame_id"] == "map":
        say(f"  Nav2 ГОТОВ, поза в карте: {[round(v, 2) for v in snap['pose']]} — «о» работает")
        return say("  но сверьте позу с реальным местом ровера, прежде чем ехать")
    say(f"  Nav2 готов: {snap['nav_ready']}, поза во фрейме «{snap['frame_id']}»")
    for node in NAV_NODES:
        label = lifecycle(web, node)
        if label != "active":
            say(f"    не поднялась: {node} ({label})")


def plans(web: str, name: str | None) -> None:
    """«м» — маршруты веб-морды: список, запуск, остановка."""
    if name in ("стоп", "stop"):
        try:
            http_json(f"{web}/api/motion/stop", {}, timeout=4.0)
        except RoverLinkError as exc:
            return say(f"маршрут не остановлен: {exc}")
        return say("маршрут остановлен")
    if not name:
        try:
            got = http_json(f"{web}/api/plans", timeout=5.0).get("plans") or []
        except RoverLinkError as exc:
            return say(f"список маршрутов не получен: {exc}")
        if not got:
            return say("сохранённых маршрутов нет (их рисуют в веб-морде)")
        say("маршруты: " + ", ".join(str(p.get("name")) for p in got))
        return say("запуск: «м <имя>», остановка: «м стоп»")
    try:
        resp = http_json(f"{web}/api/motion/start", {"kind": "plan", "name": name}, timeout=6.0)
    except RoverLinkError as exc:
        return say(f"маршрут не запущен: {exc}")
    say(f"маршрут «{name}» запущен: {(resp.get('motion') or {}).get('state', resp)}")


# ═══════════════════════════════════════════════════════════════════════════
#  ЦИКЛ ПУЛЬТА
# ═══════════════════════════════════════════════════════════════════════════


def run(rover, web: str, args, limits: dict) -> int:
    print(HELP)
    empty = 0
    while True:
        try:
            line = input("ровер> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            empty += 1
            if empty >= 2:
                break
            say("ещё раз Ctrl+C — выход (ровер при выходе тормозится)")
            continue
        empty = 0
        if not line:
            continue
        word, *rest = line.split()
        word = word.lower()
        try:
            if word in ("п", "p", "проверь", "проверить"):
                check(rover, web, args.min_volt)
            elif word in ("о", "o"):
                if len(rest) != 2:
                    say("нужно два числа: «о 0.5 0» — вперёд на 0,5 м")
                    continue
                move(rover, float(rest[0]), float(rest[1]), args.tol, args.timeout)
            elif word in ("е", "e", "ехать"):
                if len(rest) < 3:
                    say("нужно три скорости: «е 0.18 0 0 0.5» — вперёд 0,18 м/с на полметра")
                    continue
                drive(rover, web, float(rest[0]), float(rest[1]), float(rest[2]),
                      float(rest[3]) if len(rest) > 3 else 0.5, limits, args.max_dist)
            elif word in ("н", "n", "нав", "навигация"):
                reset = bool(rest) and rest[0].lower() in ("сброс", "reset")
                start = None
                if len(rest) >= 2 and not reset:
                    start = (float(rest[0]), float(rest[1]),
                             float(rest[2]) if len(rest) > 2 else 0.0)
                nav_up(rover, web, reset, start)
            elif word in ("л", "l", "лента"):
                led(rover, rest[0].lower() if rest else "", args.led_color,
                    args.led_brightness, args.led_speed)
            elif word in ("к", "k", "кадр"):
                shot(web, rest[0] if rest else f"rover-{time.strftime('%H%M%S')}.jpg")
            elif word in ("м", "m", "маршрут"):
                plans(web, rest[0] if rest else None)
            elif word in ("стоп", "stop", "с", "s"):
                rover.hard_stop()
                say("СТОП отправлен")
            elif word in ("?", "помощь", "h"):
                print(HELP)
            elif word in ("q", "выход", "quit"):
                break
            else:
                say(f"не понял «{word}», нажмите ? для подсказки")
        except ValueError:
            say("числа пишутся так: «о 0.5 -0.3»")
        except KeyboardInterrupt:
            print()
            say("прервано — торможу ровер")
            rover.hard_stop()

    rover.hard_stop()  # выходим только оставив ровер стоящим и без лиза
    say("пульт закрыт, ровер остановлен")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Ручной пульт ровера")
    p.add_argument("--ip", default="192.168.1.125", help="адрес ровера (DHCP: уточнить на месте)")
    p.add_argument("--ctrl-port", type=int, default=8767, help="порт rover_control_api")
    p.add_argument("--web-port", type=int, default=8765, help="порт rover_web (он же 80)")
    p.add_argument("--map-label", default="ofice2", help="метка SLAM-карты ровера")
    p.add_argument("--tol", type=float, default=0.15, help="считать приехавшим ближе этого, м")
    p.add_argument("--timeout", type=float, default=40.0, help="ждать переезд Nav2, с")
    p.add_argument("--max-dist", type=float, default=2.0,
                   help="предел одной ручной езды, м (поворот на месте — 6,3 рад)")
    p.add_argument("--max-speed", type=float, default=10.0,
                   help="потолок ручной езды, м/с; перебивает предел веб-морды")
    p.add_argument("--min-volt", type=float, default=11.0,
                   help="порог напряжения АКБ, В (наш, не паспортный)")
    p.add_argument("--led-color", default="#FF0000")
    p.add_argument("--led-brightness", type=float, default=0.35)
    p.add_argument("--led-speed", type=float, default=2.0, help="частота мигания, Гц")
    args = p.parse_args()

    rover = ControlApiBackend(args.ip, args.ctrl_port, args.web_port,
                              args.map_label, client_id="pult")
    web = f"http://{args.ip}:{args.web_port}"
    say(f"пульт ровера: {args.ip} (управление {args.ctrl_port}, веб {args.web_port})")

    # Пределы скоростей спрашиваем у самой морды — чтобы видеть, что ей разрешено.
    limits = {"linear_x": 0.35, "linear_y": 0.35, "angular_z": 1.5}
    try:
        limits = http_json(f"{web}/api/config", timeout=5.0).get("drive_limits") or limits
        say(f"пределы скоростей ровера: {limits}")
    except RoverLinkError as exc:
        say(f"настройки морды не прочитаны ({exc}) — беру пределы по умолчанию")

    # ...а линейный потолок ставим свой (--max-speed). Это планка ПУЛЬТА: он больше не
    # режет команду до 0,35 м/с. Борт при этом остаётся сам себе хозяин — его
    # twist_mux и драйвер моторов урежут всё, чего колёса не отработают.
    limits = dict(limits, linear_x=args.max_speed, linear_y=args.max_speed)
    say(f"потолок ручной езды пульта: {args.max_speed:g} м/с (--max-speed), "
        f"поворот {limits.get('angular_z', 1.5):g} рад/с")

    try:
        return run(rover, web, args, limits)
    finally:
        rover._release()  # лиз не должен пережить пульт: иначе ровер занят впустую


if __name__ == "__main__":
    raise SystemExit(main())
