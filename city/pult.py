"""Пульт: одно окно вместо трёх.

    python3 -m city.pult              один дрон
    python3 -m city.pult --all        все четыре монитора разом

Сам делает всё, что раньше приходилось разводить по трём терминалам:
кладёт свежую бортовую программу на дрон, запускает её, показывает
сообщения борта и ждёт команд с клавиатуры. На выходе сажает дрон и
убирает за собой.

С `--all` то же самое делается сразу с четырьмя бортами: адреса, площадки и
номера меток берутся из `city/config.yaml`, команда без имени идёт всем, с
именем — одному (`m2 кадр`). Один борт — частный случай списка из одного.

Это наземный инструмент оператора, а не часть зачётного решения: в попытке
командует диспетчер (`python3 -m city.run`), а пульт нужен, чтобы проверять
железо руками и быстро.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import sys
import threading
import time
import urllib.parse

from .robots.base import RobotError
from .robots.http_robot import HttpRobot, wait_online

DRONE_IP = "192.168.1.105"  # борт, на котором всё проверялось 2026-07-28
USER = "sverk"
REMOTE_DIR = "~/gorod_dronov/onboard"
SHOTS = "logs/shots"

# Бортовая программа живёт внутри контейнера и слушает AGENT_PORT. Снаружи контейнер
# виден по NET_PORT: на дроне настроен постоянный проброс 2200 → 8020. Раньше на его
# месте был ssh-туннель — он больше не нужен.
AGENT_PORT = 8020
NET_PORT = 2200

HELP = """
Команды (можно первой буквой):
  статус (с)        спросить, что с дроном
  кадр   (к)        снять фотографию, открыть её и разобрать: где метки и очаг
  огонь  (о)        спросить борт, что он видит: клетка очага и число огоньков
  взлет  (в) [2.0]  подняться на высоту в метрах и висеть над своей меткой
  сдвиг  10 8       дрон висит мимо метки: на 10 см вперёд и 8 см вправо.
                    Назад и влево — с минусом. Подтягивает прямо в полёте
  сесть  (п)        посадка
  стоп              аварийная посадка немедленно
  выход  (q)        посадить, всё выключить и выйти

  Когда бортов несколько, команда без имени идёт ВСЕМ, а с именем — одному:
  «m2 кадр», «m3 сдвиг 10 8». Взлёт и посадка уходят всем одновременно.

  Ctrl+C            отменить то, чего ждём сейчас (дрон остаётся как есть);
                    на пустой строке дважды подряд — выход
"""

WARNING = """
  ─── ПЕРЕД ВЗЛЁТОМ ────────────────────────────────────
   • пропеллеры установлены
   • пульт включён и в руках у второго человека
   • в полётной зоне никого
   • заряд батареи не ниже 40 %
  ──────────────────────────────────────────────────────"""


# Чьи это строки. Когда бортов четыре и они отвечают одновременно, без имени
# отчёт превращается в кашу: «сел» без имени не говорит ничего.
_who = threading.local()


def say(text: str) -> None:
    who = getattr(_who, "name", "")
    print(f"[{time.strftime('%H:%M:%S')}] {who + ' ' if who else ''}{text}", flush=True)


@contextlib.contextmanager
def speaking_for(name: str):
    """Внутри этого блока все строки пульта подписаны именем борта."""
    was = getattr(_who, "name", "")
    _who.name = name
    try:
        yield
    finally:
        _who.name = was


class Board:
    """Один борт под пультом: адрес, имя, своя площадка и своя метка.

    Одиночный запуск — это список из одного борта, поэтому отдельной ветки
    «один дрон» в пульте нет и разойтись этим двум путям негде.
    """

    def __init__(self, name: str, ip: str, user: str, url: str, cell: str, marker: int | None):
        self.name = name
        self.ip = ip
        self.host = f"{user}@{ip}"
        self.url = url
        self.cell = cell
        self.marker = marker
        self.drone: HttpRobot | None = None
        self.log = f"/tmp/agent-{name}.log"
        self.proc: subprocess.Popen | None = None
        self.ready = False
        self.counter = [0]  # номера сохранённых кадров, свои у каждого борта

    def __repr__(self) -> str:
        return f"Board({self.name} @ {self.ip})"


# ═══════════════════════════════════════════════════════════════════════════
#  СВЯЗЬ С БОРТОМ
# ═══════════════════════════════════════════════════════════════════════════


def markers_by_pad(cfg) -> dict[tuple[int, int], int]:
    """Клетка площадки -> номер её метки. Обратная сторона aruco.pads из конфига."""
    out = {}
    for mid, cell in (cfg.get("aruco.pads", {}) or {}).items():
        out[(int(cell[0]), int(cell[1]))] = int(mid)
    return out


def build_boards(args) -> list[Board]:
    """Какими бортами командуем.

    Без `--all` — один борт из ключей командной строки, как было всегда.
    С `--all` — все мониторы из config.yaml: там же лежат их адреса, площадки и
    (через aruco.pads) номера меток. Смысл в том, чтобы на площадке эти четыре
    адреса правились в одном месте и одном файле — том самом, который читает
    диспетчер. Список адресов через запятую перекрывает конфиг, не трогая его.
    """
    if args.all is None:
        marker = args.marker
        return [
            Board(
                args.name, args.ip, args.user,
                f"http://{args.ip}:{args.net_port}", args.cell, marker,
            )
        ]

    from . import config as config_mod

    cfg = config_mod.load(args.config) if args.config else config_mod.load()
    markers = markers_by_pad(cfg)
    names = list(cfg.robots.monitors)
    given = [ip.strip() for ip in args.all.split(",") if ip.strip()] if args.all else []
    if len(given) > len(names):
        raise RobotError(
            f"адресов {len(given)}, а мониторов в config.yaml всего {len(names)}: "
            f"{', '.join(names)}"
        )
    boards = []
    for i, name in enumerate(names):
        mon = cfg.robots.monitors[name]
        if given:
            if i >= len(given):
                break
            ip, url = given[i], f"http://{given[i]}:{args.net_port}"
        else:
            url = str(mon.url)
            ip = urllib.parse.urlsplit(url).hostname or ""
        pad = (int(mon.pad[0]), int(mon.pad[1]))
        # Номер метки у каждого борта свой, поэтому общий ключ --marker здесь не
        # применяется: он бы отправил все четыре дрона держаться за одну метку.
        boards.append(Board(name, ip, args.user, url, f"{pad[0]},{pad[1]}", markers.get(pad)))
    if not boards:
        raise RobotError("в config.yaml нет ни одного дрона-монитора")
    return boards


def ssh(host: str, command: str, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, command],
        capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
    )


def upload(host: str, quiet: bool) -> None:
    """Класть свежие файлы каждый раз: иначе борт незаметно отстаёт от ноутбука."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    files = [os.path.join(root, "onboard", n) for n in ("drone_agent.py", "run_agent.sh")]
    ssh(host, f"mkdir -p {REMOTE_DIR}")
    done = subprocess.run(
        ["scp", "-q", "-o", "BatchMode=yes", *files, f"{host}:{REMOTE_DIR}/"],
        capture_output=True, text=True, timeout=60,
    )
    if done.returncode:
        raise RobotError(f"не удалось скопировать программу на дрон: {done.stderr.strip()}")
    ssh(host, f"chmod +x {REMOTE_DIR}/run_agent.sh")
    if not quiet:
        say("программа на борту обновлена")


def start_agent(board: Board, args) -> subprocess.Popen:
    """Остановить старую программу и запустить новую. Возвращает само соединение.

    Запуск идёт через Popen без ожидания: ssh не возвращает управление, пока на
    том конце жив запущенный процесс, а он живёт до конца полётов. Ждём не команду,
    а появление нужной строки в логе (wait_ready).
    """
    host = board.host
    # Скобки не опечатка: без них pkill находит и убивает собственную же команду.
    ssh(host, 'pkill -9 -f "[d]rone_agent" || true')
    time.sleep(1.5)
    ssh(host, f"rm -f {board.log}")
    launch = (
        f"{REMOTE_DIR}/run_agent.sh"
        f" --name {board.name} --cell {board.cell} --port {args.port}"
        f" --watchdog {args.watchdog} --color {args.color} --alt {args.alt}"
        + (f" --marker {board.marker}" if board.marker is not None else "")
        + (" --no-yaw-hold" if args.no_yaw_hold else "")
        + (" --no-hold" if args.no_hold else "")
        + (f" --fov-deg {args.fov_deg}" if args.fov_deg is not None else "")
        + f" </dev/null >{board.log} 2>&1"
    )
    proc = subprocess.Popen(
        ["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, launch],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return proc


def wait_ready(host: str, log: str, seconds: float = 40.0) -> None:
    """Дождаться строки «слушает порт». Пока её нет — борт ещё поднимает ROS."""
    deadline = time.monotonic() + seconds
    seen = ""
    while time.monotonic() < deadline:
        out = ssh(host, f"cat {log} 2>/dev/null").stdout
        if out != seen:
            for line in out[len(seen):].splitlines():
                if line.strip():
                    print(f"  {getattr(_who, 'name', '') or 'борт'} | {line}", flush=True)
            seen = out
        if "слушает порт" in out:
            return
        if "УЖЕ ЗАНЯТ" in out or "Traceback" in out:
            raise RobotError("программа на борту не запустилась, смотрите строки выше")
        time.sleep(1.0)
    raise RobotError(f"борт не отозвался за {seconds:g} с — проверьте питание и сеть")


def tail_log(board: Board, stop: threading.Event) -> None:
    """Показывать сообщения борта в этом же окне, пока пульт работает."""
    proc = subprocess.Popen(
        ["ssh", "-n", "-o", "BatchMode=yes", board.host, f"tail -n0 -f {board.log}"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            if stop.is_set():
                break
            if line.strip():
                print(f"\n  {board.name} | {line.rstrip()}", flush=True)
    finally:
        proc.terminate()


# ═══════════════════════════════════════════════════════════════════════════
#  КОМАНДЫ С КЛАВИАТУРЫ
# ═══════════════════════════════════════════════════════════════════════════


def show_status(drone: HttpRobot) -> dict:
    st = drone.status()
    words = {"idle": "стоит на земле", "taking_off": "взлетает", "hover": "висит",
             "landing": "садится", "landed": "сел (подтверждено)",
             "landed_unverified": "сел, но борт не поручился — посмотрите глазами",
             "land_failed": "ПОСАДКА НЕ ПРИНЯТА БОРТОМ", "error": "ОШИБКА"}
    say(f"{words.get(st.get('state'), st.get('state'))}, "
        f"высота {st.get('alt', 0):.1f} м, клетка {st.get('cell')}, "
        f"камера {'готова' if st.get('camera') else 'НЕ ГОТОВА'}")
    if "yaw_ref" in st:
        # Курс борт держит по метке своей площадки. «Нечем» — метки под дроном не
        # видно: перелёты в это время идут без поправки, и увод копится.
        if st.get("yaw_ref") is None:
            say("курс: держать нечем — метки под дроном не видно")
        else:
            drift = st.get("yaw_drift")
            say(f"курс: увод {drift:+d}°" if drift is not None else "курс: увод ещё не мерян")
    if "marker" in st:
        # Дрон держится за свою метку: и место, и высота считаются по ней одной.
        # alt_seen = null означает «метку не вижу», а не «высота ноль».
        if st.get("marker_lost"):
            say(f"метку {st['marker']} ПОТЕРЯЛ ({st.get('blind', 0)} кадров подряд) — "
                f"ищу: поднялся на {st.get('above', 0.0):.2f} м, отходы по сторонам")
        elif st.get("alt_seen") is None:
            # Либо метки в кадре нет, либо эталон высоты ещё не снят: до него борт
            # высоту не правит вовсе, и это надо различать — иначе «не вижу метку»
            # прочтётся как поломка там, где дрон просто ещё успокаивается.
            if st.get("side_ref") is None and st.get("blind", 0) == 0:
                say(f"метка {st['marker']} в кадре, эталон высоты ещё снимается")
            else:
                say(f"метки {st['marker']} в этом кадре не видно "
                    f"(подряд: {st.get('blind', 0)})")
        else:
            # «отрабатываю поправку» — это не зависший борт: такт намеренно молчит,
            # пока прошлый сдвиг доезжает, иначе замер снимался бы с накренённого
            # дрона. Без пометки застывший промах читался бы как поломка.
            doing = " (отрабатываю поправку)" if st.get("settling") else ""
            say(f"держусь за метку {st['marker']}: промах {st.get('miss', 0):.2f} м, "
                f"высота по метке {st['alt_seen']:.2f} м "
                f"(сторона {st.get('side_px')} точек){doing}")
        aim = st.get("aim")
        if aim and any(aim):
            # Промах в кадре и расстояние до метки глазами — разные величины: если
            # прицел сдвинут, «промах 0.00» означает «дрон там, куда его целили».
            say(f"прицел сдвинут: вперёд {aim[0] * 100:+.0f} см, влево {aim[1] * 100:+.0f} см "
                f"(меняется командой «сдвиг»)")
    if st.get("fire"):
        fire = st["fire"]
        if fire.get("found"):
            say(f"последний ответ про огонь: клетка {fire['cell']}, "
                f"огоньков {fire['count']}")
        else:
            say(f"последний ответ про огонь: не вижу ({fire.get('note', '')})")
    if st.get("last_error"):
        say(f"последняя ошибка борта: {st['last_error']}")
    return st


def take_shot(drone: HttpRobot, counter: list[int], open_it: bool = True) -> None:
    frame = drone.shot()
    os.makedirs(SHOTS, exist_ok=True)
    counter[0] += 1
    path = os.path.join(SHOTS, f"pult-{counter[0]:03d}.jpg")
    with open(path, "wb") as fh:
        fh.write(frame)
    say(f"кадр сохранён: {path} ({len(frame) // 1024} КБ)")
    marked = explain_shot(frame, path, drone)
    # open_it=False на облёте: восемь кадров подряд открыли бы восемь окон поверх
    # пульта — как раз тогда, когда дрон в воздухе и на него надо смотреть.
    if open_it and sys.platform == "darwin":
        subprocess.run(["open", marked or path], capture_output=True)


def explain_shot(frame: bytes, path: str, drone: HttpRobot) -> str:
    """Разобрать кадр тем же зрением, что и диспетчер, и сказать результат словами.

    Это и есть способ настроить зрение на площадке: сняли кадр — сразу видно, нашлись
    ли метки, взялась ли привязка и распознан ли «огонёк». Пороги правятся в
    city/config.yaml, раздел vision.
    """
    try:
        from . import config as config_mod
        from . import vision
        from .field import Field

        cfg = config_mod.load()
        picture = vision.decode(frame)
        pose = drone.status().get("xy")
        obs = vision.look(
            picture, Field.from_config(cfg), vision.pads_from_config(cfg),
            drone="пульт", pose=pose, alt=float(drone.status().get("alt") or 1.5),
            **vision.settings(cfg),
        )
    except Exception as exc:  # noqa: BLE001 — пульт не должен падать из-за разбора кадра
        say(f"разобрать кадр не вышло: {exc}")
        return ""
    say(f"метки на кадре: {obs.markers_seen or 'нет'}; привязка: {obs.anchor}")
    if obs.found:
        say(
            f"ОЧАГ виден в клетке {list(obs.fire_cell)}: огоньков {obs.fire_count} "
            f"= столько же поездок за водой (счёт по «{obs.count_source}», "
            f"кучка {obs.spread_m:.2f} м, пятна {int(obs.area)} пикселей)"
        )
        if obs.note:
            say(f"оговорка: {obs.note}")
    else:
        say(f"очага не видно: {obs.note}")
    marked = path[:-4] + "-mark.jpg"
    try:
        from . import vision as _v

        return _v.draw(picture, obs, Field.from_config(cfg), _v.pads_from_config(cfg), marked)
    except Exception:  # noqa: BLE001
        return ""


def do_fire(drone: HttpRobot) -> None:
    """«огонь» — спросить борт, что он видит прямо сейчас.

    Разбор идёт на самом дроне: он висит над своей меткой, знает её номер и место на
    поле, поэтому масштаб и поворот кадра у него точнее, чем у ноутбука. Пульт только
    пересказывает ответ словами.
    """
    try:
        answer = drone.fire()
    except RobotError as exc:
        say(f"борт не ответил про огонь: {exc}")
        return
    if not answer.get("found"):
        say(f"очага не вижу: {answer.get('note') or 'пятен нужного цвета нет'}")
        return
    say(f"ОЧАГ в клетке {answer['cell']}: огоньков {answer['count']} "
        f"= столько же поездок за водой (счёт по «{answer['count_source']}», "
        f"кучка {answer.get('spread_m', 0):.2f} м, привязка «{answer['anchor']}»)")
    if answer.get("note"):
        say(f"оговорка: {answer['note']}")


def wait_state(drone: HttpRobot, want: tuple[str, ...], seconds: float) -> str:
    """Дождаться одного из состояний. Возвращает какое; пустая строка — не дождались."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            state = drone.status().get("state", "")
            if state in want:
                return state
        except RobotError:
            pass
        time.sleep(0.5)
    return ""


def wait_done(drone: HttpRobot, seconds: float) -> bool:
    """Дождаться, пока борт закончит текущую команду (busy снимается в конце)."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if not drone.status().get("busy", False):
                return True
        except RobotError:
            pass
        time.sleep(0.5)
    return False


def ask_takeoff(confirmed: list[bool], count: int = 1) -> bool:
    """Спросить оператора один раз за сеанс — и один раз на все борта сразу."""
    if confirmed[0]:
        return True
    print(WARNING)
    if count > 1:
        print(f"   ВЗЛЕТАЮТ СРАЗУ {count} ДРОНА — проверьте зону под каждым")
    answer = input("  всё так? напечатайте «да» и Enter: ").strip().lower()
    if answer not in ("да", "da", "yes", "y"):
        say("взлёт отменён")
        return False
    confirmed[0] = True
    return True


def do_takeoff(drone: HttpRobot, alt: float) -> None:
    say(f"команда на взлёт, высота {alt:g} м")
    drone.takeoff(alt)
    say("жду, пока встанет в воздухе…")
    if wait_state(drone, ("hover",), 25):
        say("дрон висит — можно снимать кадр")
    else:
        say("ВНИМАНИЕ: подъём не подтвердился, смотрите строки борта выше")


def do_trim(drone: HttpRobot, rest: str) -> None:
    """«сдвиг 10 8» — дрон висит на 10 см вперёд и 8 см вправо от своей метки.

    Числа в САНТИМЕТРАХ и с точки зрения дрона (нос — «вперёд»): назад и влево —
    со знаком минус. Борт прибавит их к прицелу прямо в полёте, и следующий такт
    удержания уже подтянет дрон на метку.
    """
    parts = rest.replace(",", ".").split()
    if not parts or len(parts) > 2:
        say("нужно: сдвиг <вперёд см> [<вправо см>], например «сдвиг 10 8»")
        say("назад и влево — с минусом: «сдвиг -5 -12»")
        return
    try:
        fwd_cm = float(parts[0])
        right_cm = float(parts[1]) if len(parts) > 1 else 0.0
    except ValueError:
        say("сантиметры числом: «сдвиг 10 8»")
        return
    if max(abs(fwd_cm), abs(right_cm)) > 50.0:
        say("больше полуметра за раз не даю: это уже не подстройка, а промах в замере")
        return
    # «Вправо» человеку понятнее, чем «влево −8», а борт считает влево.
    answer = drone.trim(fwd_cm / 100.0, -right_cm / 100.0)
    aim = answer.get("aim") or [0.0, 0.0]
    say(f"прицел борта теперь: вперёд {aim[0] * 100:+.0f} см, влево {aim[1] * 100:+.0f} см")
    say("посмотрите на дрон снова: осталось смещение — повторите «сдвиг» на остаток")


def do_stop(drone: HttpRobot) -> None:
    drone.stop()
    say("аварийная посадка")


def do_land(drone: HttpRobot) -> None:
    say("команда на посадку")
    drone.land()
    # «landed» борт пишет только при доказанной посадке (дизарм по телеметрии),
    # «landed_unverified» — когда команда принята, а доказательств нет. Врать
    # оператору «дрон сел» во втором случае нельзя: он на это смотреть не пойдёт.
    state = wait_state(drone, ("landed", "landed_unverified"), 25)
    if state == "landed":
        say("дрон сел — посадка подтверждена бортом")
    elif state == "landed_unverified":
        say("борт отработал посадку, но подтвердить её нечем — ПОСМОТРИТЕ НА ДРОН")
    else:
        say("ПОСАДКА НЕ ПОДТВЕРЖДЕНА — сажайте пультом, команд больше не давайте")


# ═══════════════════════════════════════════════════════════════════════════


def for_each(boards: list[Board], action, together: bool = False) -> None:
    """Сделать одно и то же на каждом борту. Отказ одного не отменяет остальных.

    `together=True` — команды уходят одновременно (взлёт, посадка, «стоп»): ждать
    посадки четырёх дронов по очереди значит держать три из них в воздухе лишние
    полминуты. Всё остальное идёт по очереди, чтобы отчёт читался сверху вниз.
    """
    def run(board: Board) -> None:
        with speaking_for(board.name if len(boards) > 1 else ""):
            try:
                action(board)
            except RobotError as exc:
                say(f"борт отказал: {exc}")

    if len(boards) == 1 or not together:
        for board in boards:
            run(board)
        return
    threads = [threading.Thread(target=run, args=(b,), daemon=True) for b in boards]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def pick(boards: list[Board], word: str) -> list[Board] | None:
    """Разобрать имя борта в начале строки: «m2 кадр» — только этому."""
    chosen = [b for b in boards if b.name.lower() == word]
    return chosen or None


def loop(boards: list[Board], args) -> None:
    confirmed = [False]
    print(HELP)
    if len(boards) > 1:
        say("команда без имени идёт всем бортам: " + ", ".join(b.name for b in boards))
    asked_to_quit = False
    while True:
        try:
            line = input("команда> ").strip().lower()
        except EOFError:
            line = "выход"
        except KeyboardInterrupt:
            # Ctrl+C на пустом приглашении: выходить с первого раза опасно — выход
            # сажает дрон, а прервать посадку нечаянным вторым Ctrl+C тем более.
            print()
            if asked_to_quit:
                return
            asked_to_quit = True
            say("отмена. Для выхода — команда «выход» или ещё раз Ctrl+C")
            continue
        asked_to_quit = False
        if not line:
            continue
        word, _, rest = line.partition(" ")
        # Имя борта в начале строки: «m2 кадр» — команда одному, без имени — всем.
        here = boards
        named = pick(boards, word)
        if named is not None:
            here = named
            word, _, rest = rest.strip().partition(" ")
            if not word:
                say(f"что сделать борту {here[0].name}? например: {here[0].name} кадр")
                continue
        try:
            if word in ("статус", "с", "s"):
                for_each(here, lambda b: show_status(b.drone))
            elif word in ("кадр", "к", "k"):
                # Открывать картинку сразу — только когда борт один: четыре окна
                # поверх пульта появятся ровно тогда, когда дроны в воздухе.
                for_each(here, lambda b: take_shot(b.drone, b.counter, open_it=len(here) == 1))
            elif word in ("взлет", "взлёт", "в", "v"):
                alt = float(rest) if rest.strip() else args.alt
                if alt > args.max_alt:
                    say(f"выше {args.max_alt:g} м нельзя (регламент: потолок 4 м)")
                    continue
                if ask_takeoff(confirmed, len(here)):
                    for_each(here, lambda b: do_takeoff(b.drone, alt), together=True)
            elif word in ("огонь", "о", "o"):
                for_each(here, lambda b: do_fire(b.drone))
            elif word in ("сдвиг", "прицел"):
                if len(here) > 1:
                    say("сдвиг задаётся одному борту: «m2 сдвиг 10 8» — уводы у них разные")
                    continue
                do_trim(here[0].drone, rest)
            elif word in ("сесть", "посадка", "п", "l"):
                for_each(here, lambda b: do_land(b.drone), together=True)
            elif word == "стоп":
                for_each(here, lambda b: do_stop(b.drone), together=True)
            elif word in ("выход", "q", "exit"):
                return
            elif word in ("помощь", "?", "h"):
                print(HELP)
            else:
                say(f"не знаю команду «{word}»")
                print(HELP)
        except RobotError as exc:
            say(f"борт отказал: {exc}")
        except ValueError:
            say("высота пишется числом, например: взлет 1.2")
        except KeyboardInterrupt:
            # Прервано только наше ожидание: борт команду уже получил и продолжает
            # её выполнять. Поэтому не «отменено», а «перестал ждать».
            print()
            say("перестал ждать. Дрон делает то, что ему уже сказано — "
                "проверьте командой «статус»")


def shutdown_one(board: Board, keep: bool) -> None:
    """Выход по одному борту. Ctrl+C здесь не роняет пульт: посадка важнее завершения."""
    landing_broken = False
    if board.drone is not None:
        try:
            if board.drone.status().get("state") in ("taking_off", "hover"):
                say("дрон в воздухе — сажаю перед выходом")
                do_land(board.drone)
        except RobotError as exc:
            # Молчать нельзя: мы выходим, а дрон, возможно, остался в воздухе.
            landing_broken = True
            say(f"ВНИМАНИЕ: не удалось посадить дрон перед выходом ({exc}) — сажайте пультом")
        except KeyboardInterrupt:
            print()
            landing_broken = True
            say("посадку прервали на середине")
    if keep:
        say("программа на борту оставлена работать (--keep)")
        return
    if landing_broken:
        # Убить агент сейчас — снять с борта единственную страховку: без команд
        # он садится сам по сторожевому таймеру. Пусть доработает.
        say("программу на борту НЕ трогаю: без команд она посадит дрон сама")
        say("если дрон всё же висит — сажайте пультом")
        return
    try:
        ssh(board.host, 'pkill -9 -f "[d]rone_agent" || true')
        if board.proc is not None:
            board.proc.terminate()
        say("программа на борту остановлена")
    except KeyboardInterrupt:
        print()
        say("не успел остановить программу на борту — она останется работать")


def shutdown(boards: list[Board], stop: threading.Event, keep: bool) -> None:
    """Выход: посадить и погасить все борта. Отказ одного не отменяет остальных."""
    say("завершаю работу")
    # Посадка идёт одновременно по той же причине, что и в полёте: пока сажаешь
    # первого по очереди, остальные три висят.
    for_each(boards, lambda b: shutdown_one(b, keep), together=True)
    stop.set()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="пульт: запустить дрон и командовать им в одном окне")
    p.add_argument("--ip", default=DRONE_IP, help=f"адрес дрона (по умолчанию {DRONE_IP})")
    p.add_argument(
        "--all", nargs="?", const="", default=None, metavar="АДРЕСА",
        help="работать сразу со всеми мониторами из config.yaml (адреса, площадки и "
             "номера меток берутся оттуда). Через запятую можно задать адреса свои: "
             "--all 192.168.1.105,192.168.1.106,192.168.1.107,192.168.1.108",
    )
    p.add_argument("--config", default=None, help="путь к config.yaml (по умолчанию свой)")
    p.add_argument("--user", default=USER)
    p.add_argument("--name", default="m1", help="имя борта")
    p.add_argument("--cell", default="1,1", help="на какой площадке стоит, col,row")
    p.add_argument("--port", type=int, default=AGENT_PORT,
                   help=f"порт внутри контейнера, его занимает бортовая программа (по умолчанию {AGENT_PORT})")
    p.add_argument("--net-port", type=int, default=NET_PORT,
                   help=f"порт, по которому дрон виден снаружи (по умолчанию {NET_PORT})")
    p.add_argument("--alt", type=float, default=2.0, help="высота зависания, м")
    p.add_argument("--max-alt", type=float, default=3.0, help="выше не пускать, м")
    p.add_argument("--marker", type=int, default=None,
                   help="номер своей метки; без ключа борт берёт его из карты поля по клетке")
    p.add_argument("--watchdog", type=float, default=120.0, help="сесть, если нет команд N с")
    p.add_argument("--color", choices=("bgr", "rgb"), default="bgr", help="порядок цветов камеры")
    p.add_argument(
        "--no-yaw-hold", action="store_true",
        help="не держать курс дрона по метке площадки (по умолчанию борт его держит)",
    )
    p.add_argument(
        "--no-hold", action="store_true",
        help="не держаться за метку вовсе: высота и положение остаются на автопилоте",
    )
    p.add_argument(
        "--fov-deg", type=float, default=None,
        help="угол обзора камеры, град: по нему борт переводит сторону метки в высоту. "
             "Дрон висит не на той высоте, что просили, — калибровать этим ключом",
    )
    p.add_argument("--no-upload", action="store_true", help="не обновлять программу на борту")
    p.add_argument("--no-restart", action="store_true", help="не перезапускать уже работающую")
    p.add_argument("--keep", action="store_true", help="на выходе оставить программу на борту")
    p.add_argument("--quiet", action="store_true")
    return p


def bring_up(board: Board, args, stop: threading.Event) -> None:
    """Поднять один борт: связь -> свежая программа -> запуск -> ответ по сети.

    Ошибка не глушится, а поднимается наверх: решает, что делать дальше, тот, кто
    знает, сколько бортов ещё живо.
    """
    say(f"{board.ip}: проверяю связь")
    if ssh(board.host, "echo ok").stdout.strip() != "ok":
        raise RobotError(
            "нет входа по ssh. Один раз выполните:\n"
            f"           ssh-copy-id -i ~/.ssh/id_ed25519_1schedule.pub {board.host}"
            "     (пароль: sverk)"
        )

    if not args.no_upload:
        upload(board.host, args.quiet)

    if args.no_restart:
        say("программу на борту не трогаю (--no-restart)")
    else:
        say("запускаю программу на борту (ROS поднимается небыстро, это нормально)")
        board.proc = start_agent(board, args)
        wait_ready(board.host, board.log)

    board.drone = HttpRobot(board.url, name=board.name)
    say(f"зову борт: {board.url}")
    try:
        st = wait_online(board.drone, seconds=15)
    except RobotError as exc:
        # Программа на борту запустилась (её строку мы видели выше), а снаружи её не
        # слышно — значит дело не в программе, а в пробросе порта. Говорим об этом
        # прямо: искать в железе дешевле, чем перезапускать агент по кругу.
        raise RobotError(
            f"{exc}\n"
            f"           борт работает, но снаружи не отвечает. Похоже, на этом дроне\n"
            f"           нет проброса {args.net_port} → {args.port} внутрь контейнера.\n"
            f"           Проверьте у того, кто настраивал дрон, или: "
            f"curl {board.url}/status"
        ) from exc
    if not st.get("camera"):
        say("КАМЕРА НЕ ГОТОВА — кадров не будет, взлетать не надо")
    board.ready = True
    threading.Thread(target=tail_log, args=(board, stop), daemon=True).start()
    say(f"готово, метка {board.marker if board.marker is not None else 'из карты поля'}, "
        f"площадка {board.cell}")


def start_board(board: Board, args, stop: threading.Event) -> None:
    """Поднять борт и не уронить пульт, если этот борт не поднялся."""
    try:
        bring_up(board, args, stop)
    except RobotError as exc:
        say(f"НЕ ПОДНЯЛСЯ: {exc}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    stop = threading.Event()
    boards: list[Board] = []

    try:
        boards = build_boards(args)
        if args.marker is not None and args.all is not None:
            say("ключ --marker со списком бортов не применяется: у каждого метка своя, "
                "они берутся из config.yaml")
        # Борта поднимаются одновременно: четыре ROS по очереди — это четыре минуты
        # ожидания там, где хватает одной.
        for_each(boards, lambda b: start_board(b, args, stop), together=True)

        live = [b for b in boards if b.ready]
        if not live:
            say("НЕ ПОЛУЧИЛОСЬ: ни один борт не поднялся")
            return 1
        if len(live) < len(boards):
            dead = ", ".join(b.name for b in boards if not b.ready)
            say(f"ВНИМАНИЕ: не поднялись борта {dead} — работаю остальными. "
                "В попытке их четверти поля останутся неснятыми")
        say(f"бортов под пультом: {', '.join(b.name for b in live)}")
        for_each(live, lambda b: show_status(b.drone))
        loop(live, args)
        return 0

    except RobotError as exc:
        say(f"НЕ ПОЛУЧИЛОСЬ: {exc}")
        return 1
    except KeyboardInterrupt:
        print()
        say("прервано с клавиатуры")
        return 0
    finally:
        try:
            shutdown([b for b in boards if b.drone is not None or b.proc is not None],
                     stop, args.keep)
        except KeyboardInterrupt:
            print()
            say("выход прерван — программа на борту могла остаться работать")


if __name__ == "__main__":
    raise SystemExit(main())
