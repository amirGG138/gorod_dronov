#!/usr/bin/env python3
"""Проверка агента ровера (этап 4) — простым списком запросов, без симуляций.

Скрипт стучится в HTTP-контракт onboard/rover_agent.py и печатает по строке на
каждую проверку: что спросили, что ждали, что пришло. Никакой логики миссии тут
нет — только «отвечает ли агент так, как обещано в PLAN.md, этап 4».

Три режима.

1. Сам себе стенд (по умолчанию) — скрипт запускает rover_agent.py --dry на
   свободном порту, гоняет ВСЕ проверки, включая переезд, и глушит агента:

       python3 rover_check/check_rover.py

2. По уже запущенному агенту — например по тому, что смотрит на живой ровер.
   Движение при этом НЕ выполняется (ровер поедет по-настоящему), пока не
   попросишь явно ключом --move:

       python3 rover_check/check_rover.py --url http://127.0.0.1:8010
       python3 rover_check/check_rover.py --url http://127.0.0.1:8010 --move

3. Плюс железо мимо агента — два GET прямо в родные API ровера, чтобы отделить
   «агент виноват» от «ровер молчит»:

       python3 rover_check/check_rover.py --url http://127.0.0.1:8010 --rover-ip 192.168.1.125

Код возврата: 0 — все проверки прошли, 1 — есть провалы. Нужна только стандартная
библиотека.
"""

import argparse
import json
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

# Кириллица в консоли Windows иначе падает на UnicodeEncodeError.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AGENT = pathlib.Path(__file__).resolve().parent.parent / "onboard" / "rover_agent.py"

results = []  # (имя, прошла ли, что пришло)


def req(method, url, body=None, timeout=8):
    """Один HTTP-запрос. Возвращает (код, разобранный JSON или {})."""
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:  # 403/404/409 — это ответ, а не беда
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": f"нет связи: {e}"}


def check(name, ok, detail=""):
    """Записать и напечатать результат одной проверки."""
    results.append((name, bool(ok), detail))
    print(f"  [{'ОК ' if ok else 'ПРОВАЛ'}] {name}" + (f"  — {detail}" if detail else ""))
    return bool(ok)


def wait_idle(url, seconds=40):
    """Дождаться, пока агент отработает команду (busy снимется). Вернуть статус."""
    end = time.monotonic() + seconds
    st = {}
    while time.monotonic() < end:
        _, st = req("GET", url + "/status")
        if not st.get("busy"):
            return st
        time.sleep(0.3)
    return st


# ═══════════════════════════════════════════════════════════════════════════
#  ПРОВЕРКИ КОНТРАКТА
# ═══════════════════════════════════════════════════════════════════════════

def check_contract(url, move):
    print("\n── Контракт агента ─────────────────────────────────────────")

    # 1. Статус: он же проверка связи и набора полей, которые ждёт диспетчер.
    code, st = req("GET", url + "/status")
    if not check("GET /status отвечает 200", code == 200, st.get("error", "")):
        return  # дальше проверять нечего
    need = ["ok", "role", "state", "cell", "since_move", "busy", "led"]
    missing = [k for k in need if k not in st]
    check("в /status есть все поля контракта", not missing,
          f"нет: {missing}" if missing else f"state={st['state']}, cell={st['cell']}, led={st['led']}")
    check("роль — rover", st.get("role") == "rover", f"role={st.get('role')}")
    check("клетка — пара целых", isinstance(st.get("cell"), list) and len(st["cell"]) == 2,
          f"cell={st.get('cell')}")
    print(f"       связь с ровером: link={st.get('link')}, Nav2 готов: {st.get('nav_ready')}"
          + (f", поза {st.get('pose')} во frame {st.get('frame_id')!r}" if st.get("pose") else "")
          + (f", АКБ {st['battery_v']} В" if "battery_v" in st else ", напряжения нет"))

    # 2. Несуществующий путь — 404, а не 500 и не молчание.
    code, _ = req("GET", url + "/nosuchpath")
    check("GET на чужой путь → 404", code == 404, f"код {code}")

    # 3. Лента: три наших режима подряд, каждый отражается в статусе.
    print("\n── Лента ───────────────────────────────────────────────────")
    for mode in ("blink", "on", "off"):
        code, ans = req("POST", url + "/led", {"mode": mode, "color": "#FF0000"})
        _, st = req("GET", url + "/status")
        check(f"POST /led {mode}", code == 200 and st.get("led") == mode,
              f"код {code}, в статусе led={st.get('led')}" + (
                  f", ошибка ленты: {ans['error']}" if ans.get("error") else ""))
        time.sleep(0.6 if mode != "off" else 0.2)  # чтобы глазами увидеть на живой ленте
    code, _ = req("POST", url + "/led", {"mode": "дискотека"})
    check("POST /led с неизвестным режимом → 403", code == 403, f"код {code}")

    # 4. Отказы движения: они приходят сразу, до старта, и это главная защита
    #    от «диспетчер решил срезать через полполя».
    print("\n── Отказы движения ─────────────────────────────────────────")
    _, st = req("GET", url + "/status")
    cell = st["cell"]
    far = [cell[0] + 2, cell[1]]
    code, ans = req("POST", url + "/drive", {"cell": far})
    check(f"/drive в несоседнюю {far} → 403", code == 403, ans.get("error", f"код {code}"))
    code, _ = req("POST", url + "/drive", {})
    check("/drive без поля cell → 400", code == 400, f"код {code}")

    # 5. Переезд в соседнюю клетку и обратно.
    print("\n── Движение ────────────────────────────────────────────────")
    if not move:
        print("       пропущено: живой ровер реально поедет (включить ключом --move)")
    elif not st.get("nav_ready") and not st.get("dry"):
        check("движение возможно", False, "Nav2 не поднят — агент честно откажет, это ожидаемо")
    else:
        near = [cell[0], cell[1] - 1] if cell[1] > 0 else [cell[0], cell[1] + 1]
        code, ans = req("POST", url + "/drive", {"cell": near, "command_id": "check-1"})
        if check(f"/drive в соседнюю {near} принят", code == 200 and ans.get("accepted"),
                 ans.get("error", f"код {code}")):
            st = wait_idle(url)
            check(f"доехал в {near}", st.get("cell") == near and st.get("state") == "idle",
                  f"state={st.get('state')}, cell={st.get('cell')}"
                  + (f", {st['last_error']}" if st.get("last_error") else ""))
            # Повтор той же команды с тем же command_id: борт обязан не ехать второй раз.
            _, ans = req("POST", url + "/drive", {"cell": near, "command_id": "check-1"})
            check("повтор команды с тем же command_id не исполняется",
                  ans.get("deduplicated") is True, f"ответ: {ans}")
            # Возвращаемся, чтобы стенд оставил ровер там же, где взял.
            req("POST", url + "/drive", {"cell": cell, "command_id": "check-2"})
            st = wait_idle(url)
            check(f"вернулся в {cell}", st.get("cell") == cell, f"cell={st.get('cell')}")

    # 6. Стоп — последняя проверка, чтобы оставить ровер заведомо стоящим.
    print("\n── Аварийная остановка ─────────────────────────────────────")
    code, _ = req("POST", url + "/stop")
    st = wait_idle(url, 10)
    check("POST /stop → state=stopped", code == 200 and st.get("state") == "stopped",
          f"код {code}, state={st.get('state')}")


# ═══════════════════════════════════════════════════════════════════════════
#  ЖЕЛЕЗО МИМО АГЕНТА
# ═══════════════════════════════════════════════════════════════════════════

def check_rover(ip, ctrl_port, web_port):
    """Два GET прямо в родные API: отделить «агент виноват» от «ровер молчит»."""
    print("\n── Ровер напрямую ──────────────────────────────────────────")
    code, st = req("GET", f"http://{ip}:{ctrl_port}/v1/state", timeout=5)
    if check(f"rover_control_api {ip}:{ctrl_port} отвечает", code == 200, st.get("error", f"код {code}")):
        pose = st.get("pose") or {}
        check("Nav2 поднят", bool(st.get("nav2_ready")),
              f"nav2_ready={st.get('nav2_ready')}, поза во frame {pose.get('frame_id')!r}"
              " (пока не map — агент откажется ехать)")
        print(f"       карта: {(st.get('map') or {}).get('label')!r}, "
              f"поза x={pose.get('x')}, y={pose.get('y')}, yaw={pose.get('yaw_deg')}")
    code, _ = req("GET", f"http://{ip}:{web_port}/api/status", timeout=5)
    check(f"rover_web {ip}:{web_port} отвечает (лента, стоп)", code == 200, f"код {code}")


# ═══════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="Прогон агента ровера по всем командам")
    p.add_argument("--url", help="адрес уже запущенного агента; без него поднимается свой --dry")
    p.add_argument("--move", action="store_true", help="разрешить реальный переезд при --url")
    p.add_argument("--rover-ip", help="заодно постучаться в железо мимо агента")
    p.add_argument("--ctrl-port", type=int, default=8767)
    p.add_argument("--web-port", type=int, default=8765)
    p.add_argument("--dry-port", type=int, default=8019, help="порт для своего --dry агента")
    args = p.parse_args()

    proc = None
    if args.url:
        url, move = args.url.rstrip("/"), args.move
        print(f"Проверяю агента по адресу {url}"
              + ("" if move else " (движение выключено, см. --move)"))
    else:
        url, move = f"http://127.0.0.1:{args.dry_port}", True
        print(f"Поднимаю свой rover_agent.py --dry на порту {args.dry_port}")
        proc = subprocess.Popen([sys.executable, str(AGENT), "--dry",
                                 "--port", str(args.dry_port), "--cell", "3,3"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        end = time.monotonic() + 10
        while time.monotonic() < end:
            if req("GET", url + "/status", timeout=1)[0] == 200:
                break
            time.sleep(0.3)
        else:
            print("  [ПРОВАЛ] агент не поднялся за 10 с")
            proc.kill()
            return 1

    try:
        check_contract(url, move)
        if args.rover_ip:
            check_rover(args.rover_ip, args.ctrl_port, args.web_port)
    finally:
        if proc is not None:
            proc.kill()

    bad = [name for name, ok, _ in results if not ok]
    print("\n" + "─" * 60)
    print(f"Проверок: {len(results)}, прошло: {len(results) - len(bad)}, провалов: {len(bad)}")
    for name in bad:
        print(f"  провал: {name}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
