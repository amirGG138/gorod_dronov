"""Пульт: одно окно вместо трёх.

    python3 -m city.pult

Сам делает всё, что раньше приходилось разводить по трём терминалам:
кладёт свежую бортовую программу на дрон, запускает её, показывает
сообщения борта и ждёт команд с клавиатуры. На выходе сажает дрон и
убирает за собой.

Это наземный инструмент оператора, а не часть зачётного решения: в попытке
командует диспетчер (`python3 -m city.run`), а пульт нужен, чтобы проверять
железо руками и быстро.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time

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
  кадр   (к)        снять фотографию и открыть её
  взлет  (в) [1.5]  подняться на высоту в метрах
  сесть  (п)        посадка
  стоп              аварийная посадка немедленно
  выход  (q)        посадить, всё выключить и выйти
"""

WARNING = """
  ─── ПЕРЕД ВЗЛЁТОМ ────────────────────────────────────
   • пропеллеры установлены
   • пульт включён и в руках у второго человека
   • в полётной зоне никого
   • заряд батареи не ниже 40 %
  ──────────────────────────────────────────────────────"""


def say(text: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
#  СВЯЗЬ С БОРТОМ
# ═══════════════════════════════════════════════════════════════════════════


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


def start_agent(host: str, args) -> tuple[str, subprocess.Popen]:
    """Остановить старую программу и запустить новую. Возвращает путь к логу и само соединение.

    Запуск идёт через Popen без ожидания: ssh не возвращает управление, пока на
    том конце жив запущенный процесс, а он живёт до конца полётов. Ждём не команду,
    а появление нужной строки в логе (wait_ready).
    """
    log = f"/tmp/agent-{args.name}.log"
    # Скобки не опечатка: без них pkill находит и убивает собственную же команду.
    ssh(host, 'pkill -9 -f "[d]rone_agent" || true')
    time.sleep(1.5)
    ssh(host, f"rm -f {log}")
    launch = (
        f"{REMOTE_DIR}/run_agent.sh"
        f" --name {args.name} --cell {args.cell} --port {args.port}"
        f" --watchdog {args.watchdog} --color {args.color}"
        f" </dev/null >{log} 2>&1"
    )
    proc = subprocess.Popen(
        ["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, launch],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return log, proc


def wait_ready(host: str, log: str, seconds: float = 40.0) -> None:
    """Дождаться строки «слушает порт». Пока её нет — борт ещё поднимает ROS."""
    deadline = time.monotonic() + seconds
    seen = ""
    while time.monotonic() < deadline:
        out = ssh(host, f"cat {log} 2>/dev/null").stdout
        if out != seen:
            for line in out[len(seen):].splitlines():
                if line.strip():
                    print(f"  борт | {line}", flush=True)
            seen = out
        if "слушает порт" in out:
            return
        if "УЖЕ ЗАНЯТ" in out or "Traceback" in out:
            raise RobotError("программа на борту не запустилась, смотрите строки выше")
        time.sleep(1.0)
    raise RobotError(f"борт не отозвался за {seconds:g} с — проверьте питание и сеть")


def tail_log(host: str, log: str, stop: threading.Event) -> None:
    """Показывать сообщения борта в этом же окне, пока пульт работает."""
    proc = subprocess.Popen(
        ["ssh", "-n", "-o", "BatchMode=yes", host, f"tail -n0 -f {log}"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            if stop.is_set():
                break
            if line.strip():
                print(f"\n  борт | {line.rstrip()}", flush=True)
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
    if st.get("last_error"):
        say(f"последняя ошибка борта: {st['last_error']}")
    return st


def take_shot(drone: HttpRobot, counter: list[int]) -> None:
    frame = drone.shot()
    os.makedirs(SHOTS, exist_ok=True)
    counter[0] += 1
    path = os.path.join(SHOTS, f"pult-{counter[0]:03d}.jpg")
    with open(path, "wb") as fh:
        fh.write(frame)
    say(f"кадр сохранён: {path} ({len(frame) // 1024} КБ)")
    if sys.platform == "darwin":
        subprocess.run(["open", path], capture_output=True)


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


def do_takeoff(drone: HttpRobot, alt: float, confirmed: list[bool]) -> None:
    if not confirmed[0]:
        print(WARNING)
        answer = input("  всё так? напечатайте «да» и Enter: ").strip().lower()
        if answer not in ("да", "da", "yes", "y"):
            say("взлёт отменён")
            return
        confirmed[0] = True
    say(f"команда на взлёт, высота {alt:g} м")
    drone.takeoff(alt)
    say("жду, пока встанет в воздухе…")
    if wait_state(drone, ("hover",), 25):
        say("дрон висит — можно снимать кадр")
    else:
        say("ВНИМАНИЕ: подъём не подтвердился, смотрите строки борта выше")


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


def loop(drone: HttpRobot, args) -> None:
    counter = [0]
    confirmed = [False]
    print(HELP)
    while True:
        try:
            line = input("команда> ").strip().lower()
        except EOFError:
            line = "выход"
        if not line:
            continue
        word, _, rest = line.partition(" ")
        try:
            if word in ("статус", "с", "s"):
                show_status(drone)
            elif word in ("кадр", "к", "k"):
                take_shot(drone, counter)
            elif word in ("взлет", "взлёт", "в", "v"):
                alt = float(rest) if rest.strip() else args.alt
                if alt > args.max_alt:
                    say(f"выше {args.max_alt:g} м нельзя (регламент: потолок 4 м)")
                    continue
                do_takeoff(drone, alt, confirmed)
            elif word in ("сесть", "посадка", "п", "l"):
                do_land(drone)
            elif word == "стоп":
                drone.stop()
                say("аварийная посадка")
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


def shutdown(drone, host: str, agent_proc, stop: threading.Event, keep: bool) -> None:
    say("завершаю работу")
    if drone is not None:
        try:
            if drone.status().get("state") in ("taking_off", "hover"):
                say("дрон в воздухе — сажаю перед выходом")
                do_land(drone)
        except RobotError as exc:
            # Молчать нельзя: мы выходим, а дрон, возможно, остался в воздухе.
            say(f"ВНИМАНИЕ: не удалось посадить дрон перед выходом ({exc}) — сажайте пультом")
    stop.set()
    if keep:
        say("программа на борту оставлена работать (--keep)")
        return
    ssh(host, 'pkill -9 -f "[d]rone_agent" || true')
    if agent_proc is not None:
        agent_proc.terminate()
    say("программа на борту остановлена")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="пульт: запустить дрон и командовать им в одном окне")
    p.add_argument("--ip", default=DRONE_IP, help=f"адрес дрона (по умолчанию {DRONE_IP})")
    p.add_argument("--user", default=USER)
    p.add_argument("--name", default="m1", help="имя борта")
    p.add_argument("--cell", default="1,1", help="на какой площадке стоит, col,row")
    p.add_argument("--port", type=int, default=AGENT_PORT,
                   help=f"порт внутри контейнера, его занимает бортовая программа (по умолчанию {AGENT_PORT})")
    p.add_argument("--net-port", type=int, default=NET_PORT,
                   help=f"порт, по которому дрон виден снаружи (по умолчанию {NET_PORT})")
    p.add_argument("--alt", type=float, default=1.5, help="высота по умолчанию, м")
    p.add_argument("--max-alt", type=float, default=3.5, help="выше не пускать, м")
    p.add_argument("--watchdog", type=float, default=8.0, help="сесть, если нет команд N с")
    p.add_argument("--color", choices=("bgr", "rgb"), default="bgr", help="порядок цветов камеры")
    p.add_argument("--no-upload", action="store_true", help="не обновлять программу на борту")
    p.add_argument("--no-restart", action="store_true", help="не перезапускать уже работающую")
    p.add_argument("--keep", action="store_true", help="на выходе оставить программу на борту")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    host = f"{args.user}@{args.ip}"
    url = f"http://{args.ip}:{args.net_port}"
    stop = threading.Event()
    agent_proc = None
    drone: HttpRobot | None = None

    try:
        say(f"дрон {args.ip}: проверяю связь")
        if ssh(host, "echo ok").stdout.strip() != "ok":
            say("нет входа по ssh. Один раз выполните:")
            say(f"  ssh-copy-id -i ~/.ssh/id_ed25519_1schedule.pub {host}     (пароль: sverk)")
            return 1

        if not args.no_upload:
            upload(host, args.quiet)

        if args.no_restart:
            log = f"/tmp/agent-{args.name}.log"
            say("программу на борту не трогаю (--no-restart)")
        else:
            say("запускаю программу на борту (ROS поднимается небыстро, это нормально)")
            log, agent_proc = start_agent(host, args)
            wait_ready(host, log)

        drone = HttpRobot(url, name=args.name)
        say(f"зову борт: {url}")
        try:
            st = wait_online(drone, seconds=15)
        except RobotError as exc:
            # Программа на борту запустилась (её строку мы видели выше), а снаружи её не
            # слышно — значит дело не в программе, а в пробросе порта. Говорим об этом
            # прямо: искать в железе дешевле, чем перезапускать агент по кругу.
            raise RobotError(
                f"{exc}\n"
                f"           борт работает, но снаружи не отвечает. Похоже, на этом дроне\n"
                f"           нет проброса {args.net_port} → {args.port} внутрь контейнера.\n"
                f"           Проверьте у того, кто настраивал дрон, или: "
                f"curl {url}/status"
            ) from exc
        if not st.get("camera"):
            say("КАМЕРА НЕ ГОТОВА — кадров не будет, взлетать не надо")

        threading.Thread(target=tail_log, args=(host, log, stop), daemon=True).start()
        say("готово. Дрон ждёт команд")
        show_status(drone)
        loop(drone, args)
        return 0

    except RobotError as exc:
        say(f"НЕ ПОЛУЧИЛОСЬ: {exc}")
        return 1
    except KeyboardInterrupt:
        print()
        return 0
    finally:
        shutdown(drone, host, agent_proc, stop, args.keep)


if __name__ == "__main__":
    raise SystemExit(main())
