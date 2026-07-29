#!/usr/bin/env python3
"""РОВЕР: строим карту лидаром, пока ровер катают руками, и ездим по этой карте.

    python3 rovMapControl.py --ip 192.168.1.125

Наземный инструмент оператора: работает на ноутбуке, на борт ничего не кладёт,
разговаривает с ровером только по HTTP (`rover_web` :8765). Карта строится У НАС,
а не на борту, поэтому роверу не нужны ни Nav2, ни slam_toolbox, ни `/scan_filtered`
— хватает живого сырого `/scan` и одометрии `/odom`.

Порядок работы (всё внутри одной сессии):

    к            начать сбор карты — дальше просто катайте ровер, карта растёт
    р            взять руль: WASD едет, QE крутит, пробел стоп, X выйти из руля
    п            показать карту в консоли и текущую позу
    с дом        сохранить карту в maps/дом.{json,pgm,yaml,png}
    з дом        загрузить сохранённую карту
    е 1.5 0.4    доехать до точки карты (метры): A* по костмапе + свои скорости
    стоп / q     остановить ровер / выйти

Почему не бортовой SLAM, хотя он есть. На выданном ровере `/scan_filtered` молчит
(нода-фильтр запущена, но не публикует), а именно его слушают и slam_toolbox, и
Nav2; сырой `/scan` при этом живой. Плюс slam_toolbox и AMCL нельзя поднимать
одновременно, то есть картирование на борту — это смена профиля bringup с борта
(шелл ttyd :7681) с риском не поднять навигацию обратно. Наша карта лежит на
ноутбуке и не зависит от того, что случится с бортом.

Что именно делает программа:

* **Скан.** `GET /api/lidar/status?topic=/scan` отдаёт уже декартовы точки во
  фрейме `lidar_link`. Лидар стоит НА 180° РАЗВЁРНУТЫМ (URDF: `lidar_joint`
  `xyz="0.0662 0 0.0837" rpy="0 0 3.14159"`), поэтому точки переводятся в оси
  корпуса поворотом на π и сдвигом на 6,6 см вперёд. Без этого карта строится
  зеркальной. Точки ближе `--min-range` выбрасываются: сырой скан видит сам
  корпус, а штатного `lidar_footprint_filter` у нас нет.
* **Поза.** Одометрия (`/odom`, это выход EKF: колёса + IMU) даёт предсказание,
  а сканматчинг по уже построенной карте — поправку. Так копящийся увод колёс не
  уезжает в карту. Поправка ограничена (`--max-fix`): лучше проехать по
  одометрии, чем принять ложное совпадение.
* **Карта.** Занятость в лог-шансах, клетка 5 см (как у Nav2 ровера), лучи
  размечаются Брезенхэмом: по пути свободно, в конце занято.
* **Езда.** A* по костмапе с раздутыми препятствиями, затем свой контроллер по
  10 Гц в `POST /api/drive/command`. Ровер мекано — умеет боком, поэтому едет
  вектором, а курс подравнивает попутно. Живой скан работает бампером.

Ограничения, о которых честно: глобальной релокализации нет — на загруженной
карте ровер считает себя там, где стоял в начале съёмки, пока не скажете `поза`.
Замыкания петель тоже нет: длинный круг по большому помещению сойдётся не идеально.
Для комнаты и для поля 4,8×4,8 м этого хватает.

**Сверено на живом ровере** `192.168.1.125` 2026-07-29, с движением: такт цикла
5 Гц (скан 500–600 точек, возраст 0,02–0,10 с), карта комнаты строится, поправка
сканматчинга даёт 140–230 баллов при пороге 25. Ручная езда вперёд-назад по 0,13 м
вернула ровер в стартовую точку с ошибкой 2 мм по нашей позе; автозаезд на 0,5 м и
обратно доехал за 7–9 с с ошибкой 0,10 м (это и есть `--tol`: ближе цели ровер уже
считает себя приехавшим). Планировщик отказался ехать, когда ровер стоял носом в
препятствие в 22 см, — «цель отрезана», а не попытка проехать сквозь. Не проверено
на живом: большая петля по помещению и сходимость карты на длинном круге.

Нужна только стандартная библиотека (numpy на этой машине нет).
"""

from __future__ import annotations

import argparse
import array
import base64
import heapq
import json
import math
import os
import struct
import sys
import threading
import time
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "onboard"))
from rover_agent import RoverLinkError, _http as http_json  # noqa: E402 — путь выше

if hasattr(sys.stdout, "reconfigure"):  # кириллица в консоли Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCAN_TYPE = "sensor_msgs/msg/LaserScan"
ODOM_TYPE = "nav_msgs/msg/Odometry"

# Куда и как повёрнут лидар относительно корпуса (URDF живого ровера, 2026-07-29).
LIDAR_DX, LIDAR_DY, LIDAR_YAW = 0.0662, 0.0, math.pi

HELP = """
Команды:
  к [выкл]           начать сбор карты (к выкл — приостановить)
  р                  руль: W/S вперёд-назад, A/D боком, Q/E поворот,
                     пробел стоп, +/- скорость, X вернуться в меню
  п                  показать карту и позу
  с <имя>            сохранить карту в maps/<имя>.{json,pgm,yaml,png}
  з <имя>            загрузить карту (сбор продолжится поверх неё)
  поза <x> <y> <курс>  сказать, где ровер стоит на загруженной карте
  е <x> <y>          доехать до точки карты (метры)
  стоп               немедленная остановка
  ?                  эта подсказка
  q                  остановить ровер и выйти
"""


def say(text: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


def wrap(a: float) -> float:
    """Угол в (-π, π] — чтобы разность курсов не прыгала на 2π через границу."""
    return math.atan2(math.sin(a), math.cos(a))


def clamp(v: float, lim: float) -> float:
    return max(-lim, min(lim, v))


# ═══════════════════════════════════════════════════════════════════════════
#  КАРТА: сетка занятости в лог-шансах
# ═══════════════════════════════════════════════════════════════════════════


def _kernel(res: float, radius_m: float = 0.15):
    """Пятно, которым занятая клетка помечается в поле правдоподобия.

    Сканматчинг ищет позу, максимизируя сумму этого поля под точками скана. По
    голой карте занятости он бы не сходился: попал точно в клетку — 1, промазал
    на сантиметр — 0, и градиента нет. Размытое пятно даёт «горку», по которой
    можно скатиться в правильную позу.
    """
    r = int(round(radius_m / res))
    out = []
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            d = math.hypot(dx, dy) * res
            if d <= radius_m:
                out.append((dx, dy, int(255 * (1.0 - d / radius_m) ** 2)))
    return out


class Grid:
    """Занятость: лог-шансы в array('b'), плюс поле правдоподобия для матчинга.

    Размер фиксированный и задаётся при старте: расти на ходу пришлось бы с
    перекладыванием обоих массивов, а комната или поле 4,8×4,8 м в 24 м влезают
    с большим запасом. Выезд за край не роняет программу — точки просто не
    ложатся, и об этом говорится вслух.
    """

    D_FREE, D_OCC = -2, 6      # прибавки за «луч прошёл» и «луч уткнулся»
    LO, HI = -40, 60           # потолки: без них карта «застывает» и не забывает
    OCC_T, FREE_T = 10, -6     # пороги «занято» / «свободно», между ними неизвестно

    def __init__(self, res: float = 0.05, size_m: float = 24.0,
                 ox: float | None = None, oy: float | None = None,
                 w: int | None = None, h: int | None = None) -> None:
        self.res = res
        self.w = w or int(round(size_m / res))
        self.h = h or int(round(size_m / res))
        self.ox = -self.w * res / 2 if ox is None else ox
        self.oy = -self.h * res / 2 if oy is None else oy
        self.odds = array.array("b", bytes(self.w * self.h))
        self.lf = bytearray(self.w * self.h)
        self.kernel = _kernel(res)
        self.hits = 0          # сколько клеток уже помечено занятыми
        self.lost = 0          # сколько точек не влезло в границы

    # --- координаты ---------------------------------------------------------

    def cell(self, x: float, y: float) -> tuple[int, int]:
        return (math.floor((x - self.ox) / self.res),
                math.floor((y - self.oy) / self.res))

    def world(self, ix: int, iy: int) -> tuple[float, float]:
        return (self.ox + (ix + 0.5) * self.res, self.oy + (iy + 0.5) * self.res)

    def inside(self, ix: int, iy: int) -> bool:
        return 0 <= ix < self.w and 0 <= iy < self.h

    # --- запись -------------------------------------------------------------

    def _free(self, i: int) -> None:
        v = self.odds[i] + self.D_FREE
        self.odds[i] = v if v > self.LO else self.LO

    def _occ(self, i: int, ix: int, iy: int) -> None:
        was = self.odds[i]
        v = was + self.D_OCC
        self.odds[i] = v if v < self.HI else self.HI
        if was < self.OCC_T <= self.odds[i]:   # клетка только что стала занятой
            self.hits += 1
            lf, w, h = self.lf, self.w, self.h
            for dx, dy, val in self.kernel:
                jx, jy = ix + dx, iy + dy
                if 0 <= jx < w and 0 <= jy < h:
                    j = jy * w + jx
                    if lf[j] < val:
                        lf[j] = val

    def _ray(self, x0: int, y0: int, x1: int, y1: int) -> None:
        """Брезенхэм: всё между роботом и точкой попадания — свободно."""
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        w, h = self.w, self.h
        while x0 != x1 or y0 != y1:
            if 0 <= x0 < w and 0 <= y0 < h:
                self._free(y0 * w + x0)
            e2 = err * 2
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def integrate(self, pose: tuple[float, float, float], pts) -> None:
        """Вписать один скан из позы pose (метры, радианы; точки в осях корпуса)."""
        x, y, th = pose
        c, s = math.cos(th), math.sin(th)
        x0, y0 = self.cell(x, y)
        if not self.inside(x0, y0):
            self.lost += len(pts)
            return
        for px, py in pts:
            ix, iy = self.cell(x + px * c - py * s, y + px * s + py * c)
            if not self.inside(ix, iy):
                self.lost += 1
                continue
            self._ray(x0, y0, ix, iy)
            self._occ(iy * self.w + ix, ix, iy)

    # --- чтение -------------------------------------------------------------

    def score(self, pose: tuple[float, float, float], pts) -> int:
        """Насколько скан ложится на карту из этой позы: сумма поля под точками."""
        x, y, th = pose
        c, s = math.cos(th), math.sin(th)
        ox, oy, res, w, h, lf = self.ox, self.oy, self.res, self.w, self.h, self.lf
        total = 0
        for px, py in pts:
            ix = int((x + px * c - py * s - ox) / res)
            iy = int((y + px * s + py * c - oy) / res)
            if 0 <= ix < w and 0 <= iy < h:
                total += lf[iy * w + ix]
        return total

    def match(self, guess: tuple[float, float, float], pts,
              max_shift: float, max_turn: float):
        """Подогнать позу под карту покоординатным спуском от грубого шага к мелкому.

        Возвращает (поза, средний балл на точку) или None, если карта ещё пустая
        либо поправка вышла за разрешённые пределы — тогда честнее ехать по
        одометрии, чем поверить в ложное совпадение (коридор к коридору).
        """
        if self.hits < 150 or len(pts) < 40:
            return None
        best, bs = guess, self.score(guess, pts)
        moves = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1),
                 (1, 1, 0), (1, -1, 0), (-1, 1, 0), (-1, -1, 0))
        for step, turn in ((0.08, 0.035), (0.04, 0.017), (0.02, 0.008), (0.01, 0.004)):
            for _ in range(14):
                improved = False
                for mx, my, mt in moves:
                    cand = (best[0] + mx * step, best[1] + my * step,
                            best[2] + mt * turn)
                    sc = self.score(cand, pts)
                    if sc > bs:
                        best, bs, improved = cand, sc, True
                if not improved:
                    break
        if math.hypot(best[0] - guess[0], best[1] - guess[1]) > max_shift:
            return None
        if abs(wrap(best[2] - guess[2])) > max_turn:
            return None
        return (best[0], best[1], wrap(best[2])), bs / len(pts)

    def bbox(self) -> tuple[int, int, int, int] | None:
        """Прямоугольник, где карта вообще что-то знает — для картинки и консоли."""
        odds, w, h = self.odds, self.w, self.h
        x0, y0, x1, y1 = w, h, -1, -1
        for iy in range(h):
            row = iy * w
            for ix in range(w):
                if odds[row + ix]:
                    if ix < x0:
                        x0 = ix
                    if ix > x1:
                        x1 = ix
                    if iy < y0:
                        y0 = iy
                    if iy > y1:
                        y1 = iy
        return None if x1 < 0 else (x0, y0, x1, y1)

    def pixels(self) -> list[bytes]:
        """Строки картинки сверху вниз в соглашении map_server: 0 занято, 254 свободно."""
        rows = []
        for iy in range(self.h - 1, -1, -1):
            row = bytearray(self.w)
            base = iy * self.w
            for ix in range(self.w):
                v = self.odds[base + ix]
                row[ix] = 0 if v >= self.OCC_T else (254 if v <= self.FREE_T else 205)
            rows.append(bytes(row))
        return rows

    def ascii_art(self, pose=None, goal=None, width: int = 78) -> str:
        """Карта в консоли: '#' стена, '·' проезжено, ' ' неизвестно, 'R' ровер."""
        box = self.bbox()
        if box is None:
            return "карта пустая"
        x0, y0, x1, y1 = box
        step = max(1, (x1 - x0 + 1) // width + 1)
        lines = []
        for iy in range(y1, y0 - 1, -step):
            line = []
            for ix in range(x0, x1 + 1, step):
                mark = " "
                for jy in range(iy, max(iy - step, y0) - 1, -1):     # берём худший
                    for jx in range(ix, min(ix + step, x1 + 1)):     # случай в блоке
                        v = self.odds[jy * self.w + jx]
                        if v >= self.OCC_T:
                            mark = "#"
                        elif v <= self.FREE_T and mark == " ":
                            mark = "·"
                line.append(mark)
            lines.append("".join(line))

        def put(px: float, py: float, ch: str) -> None:
            ix, iy = self.cell(px, py)
            r, c = (y1 - iy) // step, (ix - x0) // step
            if 0 <= r < len(lines) and 0 <= c < len(lines[r]):
                lines[r] = lines[r][:c] + ch + lines[r][c + 1:]

        if goal:
            put(goal[0], goal[1], "G")
        if pose:
            put(pose[0], pose[1], "R")
        head = (f"клетка {self.res * step * 100:.0f} см на символ, "
                f"занятых клеток {self.hits}")
        return head + "\n" + "\n".join(lines)

    # --- файлы --------------------------------------------------------------

    def to_json(self) -> dict:
        return {"kind": "rovMapControl-grid", "version": 1, "res": self.res,
                "w": self.w, "h": self.h, "ox": self.ox, "oy": self.oy,
                "hits": self.hits, "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "odds": base64.b64encode(self.odds.tobytes()).decode("ascii")}

    @classmethod
    def from_json(cls, d: dict) -> "Grid":
        g = cls(res=d["res"], ox=d["ox"], oy=d["oy"], w=d["w"], h=d["h"])
        g.odds = array.array("b", base64.b64decode(d["odds"]))
        # Поле правдоподобия не храним: пересобрать его дешевле, чем таскать в файле.
        for iy in range(g.h):
            for ix in range(g.w):
                i = iy * g.w + ix
                if g.odds[i] >= cls.OCC_T:
                    g.hits += 1
                    for dx, dy, val in g.kernel:
                        jx, jy = ix + dx, iy + dy
                        if 0 <= jx < g.w and 0 <= jy < g.h:
                            j = jy * g.w + jx
                            if g.lf[j] < val:
                                g.lf[j] = val
        return g


def png_gray(w: int, h: int, rows: list[bytes]) -> bytes:
    """8-битный серый PNG вручную: matplotlib на этой машине нет, а смотреть надо."""
    raw = b"".join(b"\x00" + r for r in rows)   # 0 — фильтр строки «как есть»

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b""))


def save_map(grid: Grid, path_base: str, pose=None) -> list[str]:
    """Карта на диск: json — наш формат, pgm+yaml — формат map_server, png — глазами."""
    os.makedirs(os.path.dirname(path_base) or ".", exist_ok=True)
    rows = grid.pixels()
    written = []

    with open(path_base + ".json", "w", encoding="utf-8") as f:
        payload = grid.to_json()
        if pose:
            payload["pose"] = [round(v, 4) for v in pose]
        json.dump(payload, f, ensure_ascii=False)
    written.append(path_base + ".json")

    with open(path_base + ".pgm", "wb") as f:
        f.write(b"P5\n# rovMapControl\n%d %d\n255\n" % (grid.w, grid.h))
        f.write(b"".join(rows))
    written.append(path_base + ".pgm")

    name = os.path.basename(path_base)
    with open(path_base + ".yaml", "w", encoding="utf-8") as f:
        f.write(f"image: {name}.pgm\nmode: trinary\nresolution: {grid.res:.3f}\n"
                f"origin: [{grid.ox:.3f}, {grid.oy:.3f}, 0.0]\nnegate: 0\n"
                f"occupied_thresh: 0.65\nfree_thresh: 0.196\n")
    written.append(path_base + ".yaml")

    with open(path_base + ".png", "wb") as f:
        f.write(png_gray(grid.w, grid.h, rows))
    written.append(path_base + ".png")
    return written


# ═══════════════════════════════════════════════════════════════════════════
#  РОВЕР ПО HTTP
# ═══════════════════════════════════════════════════════════════════════════


class Rover:
    """Только веб-морда :8765: скан, одометрия, скорости, стоп. Лиз не нужен —
    ручные скорости идут в `/cmd_vel_teleop` с приоритетом выше Nav2."""

    def __init__(self, ip: str, web_port: int, scan_topic: str,
                 min_range: float, max_range: float) -> None:
        self.web = f"http://{ip}:{web_port}"
        self.scan_topic = scan_topic
        self.min_range, self.max_range = min_range, max_range
        self.limits = {"linear_x": 0.35, "linear_y": 0.35, "angular_z": 1.5}

    def read_limits(self) -> dict:
        try:
            got = http_json(f"{self.web}/api/config", timeout=5.0).get("drive_limits")
        except RoverLinkError as exc:
            say(f"настройки морды не прочитаны ({exc}) — беру пределы по умолчанию")
            return self.limits
        if got:
            self.limits = got
        return self.limits

    def scan(self) -> tuple[list[tuple[float, float]], float]:
        """Точки скана в осях КОРПУСА и их возраст.

        Лидар развёрнут на 180°, поэтому поворачиваем и сдвигаем. Ближние точки —
        это сам корпус ровера: штатный фильтр молчит, режем сами.
        """
        d = http_json(f"{self.web}/api/lidar/status?topic={self.scan_topic}"
                      f"&type={SCAN_TYPE}", timeout=5.0)
        c, s = math.cos(LIDAR_YAW), math.sin(LIDAR_YAW)
        lo, hi, out = self.min_range, self.max_range, []
        for p in d.get("points") or []:
            x = p[0] * c - p[1] * s + LIDAR_DX
            y = p[0] * s + p[1] * c + LIDAR_DY
            r = math.hypot(x, y)
            if lo <= r <= hi:
                out.append((x, y))
        return out, d.get("age_sec") or 0.0

    def odom(self) -> tuple[float, float, float] | None:
        """Поза одометрии (x, y, курс). Это выход EKF: колёса плюс IMU по курсу."""
        d = http_json(f"{self.web}/api/ros/topic?name=/odom&type={ODOM_TYPE}",
                      timeout=5.0)
        msg = d.get("latest_message")
        if not msg:
            return None   # первый запрос только создаёт подписку — это нормально
        pose = ((msg.get("pose") or {}).get("pose") or {})
        pos, q = pose.get("position") or {}, pose.get("orientation") or {}
        yaw = math.atan2(2.0 * (q.get("w", 1.0) * q.get("z", 0.0)),
                         1.0 - 2.0 * q.get("z", 0.0) ** 2)
        return float(pos.get("x", 0.0)), float(pos.get("y", 0.0)), yaw

    def drive(self, vx: float, vy: float, wz: float) -> None:
        """Одна команда скоростей. На борту живёт 0,25 с — слать надо потоком."""
        http_json(f"{self.web}/api/drive/command",
                  {"linear_x": clamp(vx, self.limits.get("linear_x", 0.35)),
                   "linear_y": clamp(vy, self.limits.get("linear_y", 0.35)),
                   "angular_z": clamp(wz, self.limits.get("angular_z", 1.5))},
                  timeout=3.0)

    def stop(self, hard: bool = False) -> None:
        """Стоп. hard — ещё и общий стоп морды: им же гасится начатый маршрут."""
        urls = [f"{self.web}/api/drive/stop"]
        if hard:
            urls += [f"{self.web}/api/motion/stop", f"{self.web}/api/stop"]
        for url in urls:
            try:
                http_json(url, {}, timeout=3.0)
            except RoverLinkError as exc:
                say(f"СТОП не прошёл ({url}): {exc}")


# ═══════════════════════════════════════════════════════════════════════════
#  SLAM: поток, который держит карту и позу
# ═══════════════════════════════════════════════════════════════════════════


class Mapper(threading.Thread):
    """Фоновый цикл: скан + одометрия -> поправка сканматчингом -> запись в карту.

    Живёт всё время работы программы, потому что позу надо знать и когда карту
    не пишем (езда по готовой карте — это тот же цикл с выключенной записью).
    """

    daemon = True

    def __init__(self, rover: Rover, grid: Grid, args) -> None:
        super().__init__(name="mapper")
        self.rover, self.grid, self.args = rover, grid, args
        self.lock = threading.RLock()
        self.pose = (0.0, 0.0, 0.0)     # поза в осях НАШЕЙ карты
        self.odom_ref: tuple[float, float, float] | None = None
        self.points: list[tuple[float, float]] = []
        self.mapping = bool(args.start_mapping)
        self.stop_event = threading.Event()
        self.last_write = (0.0, 0.0, 0.0)
        self.seed_left = args.seed   # сколько сканов вписать, ещё никуда не поехав
        self.cycles = 0
        self.fixes = 0                  # сколько раз сканматчинг поправил одометрию
        self.quality = 0.0              # средний балл последнего совпадения
        self.error: str | None = None
        self.silent_since: float | None = None

    # --- то, что читают другие потоки --------------------------------------

    def snapshot(self):
        with self.lock:
            return self.pose, list(self.points)

    def set_pose(self, x: float, y: float, yaw: float) -> None:
        with self.lock:
            self.pose = (x, y, yaw)
            self.last_write = self.pose

    def set_mapping(self, on: bool) -> None:
        with self.lock:
            self.mapping = on
            if on:
                self.seed_left = self.args.seed   # включили сбор — сразу засеять карту

    def swap_grid(self, grid: Grid) -> None:
        with self.lock:
            self.grid = grid

    # --- сам цикл -----------------------------------------------------------

    def run(self) -> None:
        while not self.stop_event.is_set():
            began = time.monotonic()
            try:
                self.step()
                self.error, self.silent_since = None, None
            except RoverLinkError as exc:
                self.error = str(exc)
                if self.silent_since is None:
                    self.silent_since = time.monotonic()
                time.sleep(0.5)
            left = self.args.period - (time.monotonic() - began)
            if left > 0:
                self.stop_event.wait(left)

    def step(self) -> None:
        odom = self.rover.odom()
        pts, _age = self.rover.scan()
        if odom is None or not pts:
            return
        with self.lock:
            if self.odom_ref is None:      # первый круг: где стоим, там и начало карты
                self.odom_ref = odom
                self.grid.integrate(self.pose, pts)
                self.points = pts
                self.cycles += 1
                return

            guess = self.predict(odom)
            sub = pts[::max(1, len(pts) // self.args.match_points)]
            got = self.grid.match(guess, sub, self.args.max_fix,
                                  math.radians(self.args.max_fix_deg))
            if got and got[1] >= self.args.min_quality:
                self.pose, self.quality = got[0], got[1]
                self.fixes += 1
            else:
                self.pose = guess
                self.quality = got[1] if got else 0.0
            self.odom_ref = odom
            self.points = pts
            self.cycles += 1

            if self.mapping and (self.moved_enough() or self.seed_left > 0):
                if not self.moved_enough():
                    self.seed_left -= 1
                self.grid.integrate(self.pose, pts)
                self.last_write = self.pose

    def predict(self, odom) -> tuple[float, float, float]:
        """Перенести шаг одометрии в оси карты: сдвиг поворачивается на разницу курсов."""
        ox, oy, oth = self.odom_ref
        dx, dy, dth = odom[0] - ox, odom[1] - oy, wrap(odom[2] - oth)
        a = self.pose[2] - oth
        c, s = math.cos(a), math.sin(a)
        return (self.pose[0] + dx * c - dy * s,
                self.pose[1] + dx * s + dy * c,
                wrap(self.pose[2] + dth))

    def moved_enough(self) -> bool:
        """Писать скан на каждом такте незачем: стоящий ровер только выжигает карту.

        Исключение — первые `--seed` сканов после включения сбора: клетка считается
        занятой со второго попадания, поэтому по одному-единственному скану карта
        выглядит пустой, и сканматчингу не за что зацепиться.
        """
        px, py, pth = self.last_write
        return (math.hypot(self.pose[0] - px, self.pose[1] - py) > 0.04
                or abs(wrap(self.pose[2] - pth)) > math.radians(3.0))


# ═══════════════════════════════════════════════════════════════════════════
#  ПЛАНИРОВЩИК: костмапа и A*
# ═══════════════════════════════════════════════════════════════════════════


class Costmap:
    """Карта проходимости: 255 — нельзя, дальше цена тем выше, чем ближе стена.

    Радиус раздувания — половина корпуса плюс запас, как в Nav2 ровера
    (footprint 0.25×0.26 м, inflation 0.28). Неизвестные клетки по умолчанию
    считаются непроезжими: карта строится тем же лидаром, и «не видел» здесь
    почти всегда значит «не был», а не «свободно».
    """

    LETHAL = 255

    def __init__(self, grid: Grid, robot_r: float, inflation: float,
                 allow_unknown: bool = False) -> None:
        self.w, self.h, self.res = grid.w, grid.h, grid.res
        self.ox, self.oy = grid.ox, grid.oy
        self.cost = bytearray(self.w * self.h)
        hard = int(math.ceil(robot_r / self.res))
        soft = int(math.ceil((robot_r + inflation) / self.res))
        disc = []
        for dy in range(-soft, soft + 1):
            for dx in range(-soft, soft + 1):
                d = math.hypot(dx, dy)
                if d <= hard:
                    disc.append((dx, dy, self.LETHAL))
                elif d <= soft:
                    k = (d - hard) / max(1e-6, soft - hard)
                    disc.append((dx, dy, int(200 * (1.0 - k)) + 10))
        walls = []
        for i, v in enumerate(grid.odds):
            if v >= Grid.OCC_T:
                walls.append(i)
            elif not allow_unknown and v > Grid.FREE_T:
                self.cost[i] = self.LETHAL
        for i in walls:
            ix, iy = i % self.w, i // self.w
            for dx, dy, c in disc:
                jx, jy = ix + dx, iy + dy
                if 0 <= jx < self.w and 0 <= jy < self.h:
                    j = jy * self.w + jx
                    if self.cost[j] < c:
                        self.cost[j] = c

    def cell(self, x: float, y: float) -> tuple[int, int]:
        return (math.floor((x - self.ox) / self.res),
                math.floor((y - self.oy) / self.res))

    def world(self, ix: int, iy: int) -> tuple[float, float]:
        return (self.ox + (ix + 0.5) * self.res, self.oy + (iy + 0.5) * self.res)

    def free(self, ix: int, iy: int) -> bool:
        return (0 <= ix < self.w and 0 <= iy < self.h
                and self.cost[iy * self.w + ix] < self.LETHAL)

    def nearest_free(self, ix: int, iy: int, radius_m: float = 0.5):
        """Ближайшая проезжая клетка — цель могли ткнуть в стену или в неизвестное."""
        if self.free(ix, iy):
            return ix, iy
        r = int(radius_m / self.res)
        for ring in range(1, r + 1):
            best = None
            for dy in range(-ring, ring + 1):
                for dx in range(-ring, ring + 1):
                    if max(abs(dx), abs(dy)) != ring:
                        continue
                    if self.free(ix + dx, iy + dy):
                        d = dx * dx + dy * dy
                        if best is None or d < best[0]:
                            best = (d, ix + dx, iy + dy)
            if best:
                return best[1], best[2]
        return None

    def visible(self, a: tuple[float, float], b: tuple[float, float]) -> bool:
        """Прямая между точками не режет запретную зону — для спрямления пути."""
        steps = int(math.dist(a, b) / (self.res * 0.7)) + 1
        for k in range(steps + 1):
            t = k / steps
            ix, iy = self.cell(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            if not self.free(ix, iy):
                return False
        return True

    def plan(self, start, goal, budget: int = 400_000):
        """A* по восьми соседям. Цена шага растёт у стен — путь сам держится середины."""
        sx, sy = self.cell(*start)
        gx, gy = self.cell(*goal)
        near_start = self.nearest_free(sx, sy, 0.6)
        near_goal = self.nearest_free(gx, gy, 0.8)
        if near_start is None:
            return None, "ровер стоит в запретной зоне карты"
        if near_goal is None:
            return None, "к этой точке не подобраться: стена или неизвестное место"
        sx, sy = near_start
        gx, gy = near_goal
        w, cost = self.w, self.cost
        start_i, goal_i = sy * w + sx, gy * w + gx

        def hcost(i: int) -> float:
            dx, dy = abs(i % w - gx), abs(i // w - gy)
            return (dx + dy) + (math.sqrt(2) - 2) * min(dx, dy)

        open_q = [(hcost(start_i), start_i)]
        came: dict[int, int] = {}
        gscore = {start_i: 0.0}
        seen = 0
        while open_q:
            _, cur = heapq.heappop(open_q)
            if cur == goal_i:
                break
            seen += 1
            if seen > budget:
                return None, "путь не найден за отведённый перебор"
            cx, cy = cur % w, cur // w
            base = gscore[cur]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                           (1, 1), (1, -1), (-1, 1), (-1, -1)):
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < w and 0 <= ny < self.h):
                    continue
                n = ny * w + nx
                c = cost[n]
                if c >= self.LETHAL:
                    continue
                step = (1.41421 if dx and dy else 1.0) * (1.0 + c / 40.0)
                ng = base + step
                if ng < gscore.get(n, 1e18):
                    gscore[n] = ng
                    came[n] = cur
                    heapq.heappush(open_q, (ng + hcost(n), n))
        else:
            return None, "путь не найден: цель отрезана"

        path = [goal_i]
        while path[-1] != start_i:
            path.append(came[path[-1]])
        path.reverse()
        pts = [self.world(i % w, i // w) for i in path]
        return self.shorten(pts), None

    def shorten(self, pts):
        """Выкинуть промежуточные точки, пока прямая между соседями свободна."""
        if len(pts) < 3:
            return pts
        out, i = [pts[0]], 0
        while i < len(pts) - 1:
            j = len(pts) - 1
            while j > i + 1 and not self.visible(pts[i], pts[j]):
                j -= 1
            out.append(pts[j])
            i = j
        return out


# ═══════════════════════════════════════════════════════════════════════════
#  ЕЗДА ПО КАРТЕ
# ═══════════════════════════════════════════════════════════════════════════


def blocked_ahead(points, vx: float, vy: float, dist: float, half_width: float) -> bool:
    """Бампер: есть ли точка скана прямо по курсу движения ближе dist.

    Смотрим не «вперёд», а туда, куда реально едем: ровер мекано, он ходит боком.
    Точки берём в осях корпуса, поворачиваем в ось движения и смотрим коридор.
    """
    speed = math.hypot(vx, vy)
    if speed < 0.02:
        return False
    c, s = vx / speed, vy / speed
    for px, py in points:
        along = px * c + py * s
        across = -px * s + py * c
        if 0.0 < along < dist and abs(across) < half_width:
            return True
    return False


def go_to(mapper: Mapper, rover: Rover, gx: float, gy: float, args) -> None:
    """«е x y» — довезти ровер до точки карты: A* + свой контроллер по 10 Гц."""
    with mapper.lock:
        cm = Costmap(mapper.grid, args.robot_radius, args.inflation, args.through_unknown)
        pose = mapper.pose
    path, err = cm.plan((pose[0], pose[1]), (gx, gy))
    if path is None:
        return say(f"не поеду: {err}")
    say(f"путь построен: {len(path)} точек, {path_len(path):.2f} м, "
        f"еду со скоростью до {args.speed:.2f} м/с")

    deadline = time.monotonic() + args.drive_timeout
    replan_at = time.monotonic() + args.replan
    idx, stuck = 1, 0
    try:
        while time.monotonic() < deadline:
            pose, pts = mapper.snapshot()
            if mapper.error:
                say(f"связь с ровером пропала ({mapper.error}) — торможу")
                break
            if math.hypot(gx - pose[0], gy - pose[1]) <= args.tol:
                say(f"приехал: ({pose[0]:.2f}, {pose[1]:.2f}) м, "
                    f"курс {math.degrees(pose[2]):.0f}°")
                break

            # Точка прицеливания: ближайшая точка пути дальше упреждения.
            while idx < len(path) - 1 and math.dist(path[idx], (pose[0], pose[1])) < args.lookahead:
                idx += 1
            tx, ty = path[idx]

            dx, dy = tx - pose[0], ty - pose[1]
            dist = math.hypot(dx, dy)
            c, s = math.cos(-pose[2]), math.sin(-pose[2])
            bx, by = dx * c - dy * s, dx * s + dy * c     # цель в осях корпуса
            speed = min(args.speed, max(0.06, dist))
            norm = max(1e-6, math.hypot(bx, by))
            vx, vy = bx / norm * speed, by / norm * speed
            # Курс подравниваем к направлению движения, но не крутимся у самой цели:
            # ровер мекано, доехать он может и боком.
            turn = 0.0
            if math.hypot(gx - pose[0], gy - pose[1]) > args.lookahead:
                turn = clamp(1.2 * math.atan2(by, bx), args.turn_speed)

            if blocked_ahead(pts, vx, vy, args.brake, args.bumper):
                rover.drive(0.0, 0.0, 0.0)
                stuck += 1
                if stuck > 12:
                    say("впереди препятствие и объезда не нашлось — стою")
                    break
                say("препятствие по курсу — перестраиваю путь")
                time.sleep(0.3)
                replan_at = 0.0
            else:
                stuck = 0
                rover.drive(vx, vy, turn)

            if time.monotonic() >= replan_at:
                with mapper.lock:
                    cm = Costmap(mapper.grid, args.robot_radius, args.inflation,
                                 args.through_unknown)
                fresh, err = cm.plan((pose[0], pose[1]), (gx, gy))
                if fresh:
                    path, idx = fresh, 1
                elif stuck:
                    say(f"объезд не строится: {err}")
                    break
                replan_at = time.monotonic() + args.replan
            time.sleep(0.1)
        else:
            say(f"не доехал за {args.drive_timeout:g} с")
    except RoverLinkError as exc:
        say(f"езда прервана: {exc}")
    except KeyboardInterrupt:
        say("прервано с клавиатуры")
    finally:
        rover.stop()
        pose, _ = mapper.snapshot()
        say(f"стою в ({pose[0]:.2f}, {pose[1]:.2f}) м, "
            f"до цели {math.hypot(gx - pose[0], gy - pose[1]):.2f} м")


def path_len(path) -> float:
    return sum(math.dist(path[i], path[i + 1]) for i in range(len(path) - 1))


# ═══════════════════════════════════════════════════════════════════════════
#  РУЛЬ: ручное вождение с клавиатуры
# ═══════════════════════════════════════════════════════════════════════════

# Русская раскладка на тех же клавишах — чтобы не переключаться ради езды.
KEYMAP = {"w": "w", "s": "s", "a": "a", "d": "d", "q": "q", "e": "e", "x": "x",
          "ц": "w", "ы": "s", "ф": "a", "в": "d", "й": "q", "у": "e", "ч": "x"}


def _key_reader():
    """Неблокирующее чтение клавиш: msvcrt на Windows, termios на остальных."""
    try:
        import msvcrt

        def read():
            return msvcrt.getwch().lower() if msvcrt.kbhit() else None
        return read, None
    except ImportError:
        pass
    import select
    import termios
    import tty
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    def read():
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1).lower()
        return None

    return read, lambda: termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def teleop(rover: Rover, mapper: Mapper, args) -> None:
    """«р» — руль. Ровер едет, пока держите клавишу; карта в это время растёт."""
    say("руль: W/S вперёд-назад, A/D боком, Q/E поворот, пробел стоп, "
        "+/- скорость, X выход")
    read, restore = _key_reader()
    speed, turn = args.speed, args.turn_speed
    vx = vy = wz = 0.0
    hold = 0.0     # до какого момента держим последнюю команду
    try:
        while True:
            key = read()
            if key is not None:
                key = KEYMAP.get(key, key)
                if key == "x":
                    break
                elif key == "w":
                    vx, vy, wz = speed, 0.0, 0.0
                elif key == "s":
                    vx, vy, wz = -speed, 0.0, 0.0
                elif key == "a":
                    vx, vy, wz = 0.0, speed, 0.0
                elif key == "d":
                    vx, vy, wz = 0.0, -speed, 0.0
                elif key == "q":
                    vx, vy, wz = 0.0, 0.0, turn
                elif key == "e":
                    vx, vy, wz = 0.0, 0.0, -turn
                elif key in (" ", "\r", "\n"):
                    vx = vy = wz = 0.0
                elif key in ("+", "="):
                    speed = min(speed + 0.03, rover.limits.get("linear_x", 0.35))
                    turn = min(turn + 0.1, rover.limits.get("angular_z", 1.5))
                    say(f"скорость {speed:.2f} м/с, поворот {turn:.2f} рад/с")
                elif key in ("-", "_"):
                    speed, turn = max(0.05, speed - 0.03), max(0.1, turn - 0.1)
                    say(f"скорость {speed:.2f} м/с, поворот {turn:.2f} рад/с")
                if key in ("w", "s", "a", "d", "q", "e"):
                    hold = time.monotonic() + args.key_hold

            if hold and time.monotonic() > hold:   # клавишу отпустили — тормозим
                vx = vy = wz = 0.0
                hold = 0.0
            try:
                rover.drive(vx, vy, wz)
            except RoverLinkError as exc:
                say(f"команда не прошла: {exc}")
            time.sleep(0.08)
    except KeyboardInterrupt:
        pass
    finally:
        if restore:
            restore()
        rover.stop()
        pose, _ = mapper.snapshot()
        say(f"руль отпущен, ровер стоит в ({pose[0]:.2f}, {pose[1]:.2f}) м, "
            f"занятых клеток на карте {mapper.grid.hits}")


# ═══════════════════════════════════════════════════════════════════════════
#  ЦИКЛ ПРОГРАММЫ
# ═══════════════════════════════════════════════════════════════════════════


def status(mapper: Mapper, args) -> None:
    pose, pts = mapper.snapshot()
    grid = mapper.grid
    say(f"поза: x={pose[0]:.2f} y={pose[1]:.2f} курс={math.degrees(pose[2]):.0f}° "
        f"(наша карта, начало — где включили сбор)")
    say(f"сбор карты: {'ИДЁТ' if mapper.mapping else 'выключен'}, "
        f"тактов {mapper.cycles}, поправок сканматчинга {mapper.fixes}, "
        f"качество совпадения {mapper.quality:.0f} (порог {args.min_quality:g})")
    say(f"скан: {len(pts)} точек в работе; занятых клеток {grid.hits}"
        + (f", точек мимо карты {grid.lost} — карта мала, поднимите --size"
           if grid.lost else ""))
    if mapper.error:
        say(f"СВЯЗЬ: {mapper.error}")
    print(grid.ascii_art(pose))


def run(rover: Rover, mapper: Mapper, args) -> int:
    print(HELP)
    empty = 0
    while True:
        try:
            line = input("карта> ").strip()
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
            if word in ("к", "k", "карта"):
                on = not (rest and rest[0].lower() in ("выкл", "off", "стоп"))
                mapper.set_mapping(on)
                say("сбор карты идёт — катайте ровер" if on else "сбор карты приостановлен")
            elif word in ("р", "r", "руль"):
                teleop(rover, mapper, args)
            elif word in ("п", "p", "покажи"):
                status(mapper, args)
            elif word in ("с", "s", "сохр"):
                name = rest[0] if rest else time.strftime("map-%H%M%S")
                with mapper.lock:
                    files = save_map(mapper.grid, os.path.join(args.maps, name),
                                     mapper.pose)
                if mapper.grid.hits < 50:
                    say(f"карта почти пустая (занятых клеток {mapper.grid.hits}) — "
                        "сбор был выключен или лидар молчит; сохраняю как есть")
                say("сохранено: " + ", ".join(os.path.basename(f) for f in files))
                say(f"    папка {os.path.abspath(args.maps)}; картинку смотреть в {name}.png")
            elif word in ("з", "z", "загр"):
                if not rest:
                    say("нужно имя: «з дом»")
                    continue
                path = os.path.join(args.maps, rest[0] + ".json")
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                grid = Grid.from_json(data)
                mapper.swap_grid(grid)
                pose = data.get("pose")
                if pose:
                    mapper.set_pose(*pose)
                say(f"карта «{rest[0]}» загружена: {grid.w}×{grid.h} клеток по "
                    f"{grid.res * 100:.0f} см, занятых {grid.hits}")
                say("ВНИМАНИЕ: ровер считает себя там, где стоял при съёмке. Если он "
                    "стоит не там — скажите «поза x y курс», иначе поедет не туда")
            elif word == "поза":
                if len(rest) != 3:
                    say("нужно три числа: «поза 0 0 0» — x, y в метрах и курс в градусах")
                    continue
                mapper.set_pose(float(rest[0]), float(rest[1]),
                                math.radians(float(rest[2])))
                say("поза задана; сканматчинг подтянет её по карте на ходу")
            elif word in ("е", "e", "ехать"):
                if len(rest) != 2:
                    say("нужно две координаты: «е 1.5 0.4» — метры карты")
                    continue
                go_to(mapper, rover, float(rest[0]), float(rest[1]), args)
            elif word in ("стоп", "stop"):
                rover.stop(hard=True)
                say("СТОП отправлен")
            elif word in ("?", "помощь", "h"):
                print(HELP)
            elif word in ("q", "выход", "quit"):
                break
            else:
                say(f"не понял «{word}», нажмите ? для подсказки")
        except ValueError:
            say("числа пишутся так: «е 1.5 -0.4»")
        except OSError as exc:
            say(f"файл не прочитан: {exc}")
        except RoverLinkError as exc:
            say(f"ровер не ответил: {exc}")
        except KeyboardInterrupt:
            print()
            say("прервано — торможу ровер")
            rover.stop()

    rover.stop(hard=True)
    say("выход, ровер остановлен")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Своя карта ровера лидаром и езда по ней")
    p.add_argument("--ip", default="192.168.1.125", help="адрес ровера (DHCP: уточнить)")
    p.add_argument("--web-port", type=int, default=8765, help="порт rover_web")
    p.add_argument("--scan-topic", default="/scan",
                   help="топик лидара (/scan_filtered на выданном ровере молчит)")
    p.add_argument("--maps", default="maps", help="папка, куда класть карты")
    p.add_argument("--load", help="загрузить карту при старте (имя без расширения)")
    p.add_argument("--start-mapping", action="store_true",
                   help="сразу начать сбор карты, не дожидаясь команды «к»")

    g = p.add_argument_group("карта")
    g.add_argument("--res", type=float, default=0.05, help="клетка карты, м")
    g.add_argument("--size", type=float, default=24.0, help="сторона карты, м")
    g.add_argument("--min-range", type=float, default=0.22,
                   help="ближе этого точки скана — сам корпус ровера, м")
    g.add_argument("--max-range", type=float, default=8.0,
                   help="дальше этого лучам не верим, м")
    g.add_argument("--period", type=float, default=0.2, help="такт опроса ровера, с")
    g.add_argument("--seed", type=int, default=6,
                   help="сколько первых сканов вписать, пока ровер ещё стоит")

    g = p.add_argument_group("сканматчинг")
    g.add_argument("--match-points", type=int, default=160,
                   help="сколько точек скана брать на подгонку позы")
    g.add_argument("--max-fix", type=float, default=0.30,
                   help="предел поправки к одометрии за такт, м")
    g.add_argument("--max-fix-deg", type=float, default=15.0,
                   help="предел поправки курса за такт, градусы")
    g.add_argument("--min-quality", type=float, default=25.0,
                   help="ниже этого балла совпадение считаем случайным (0..255)")

    g = p.add_argument_group("движение")
    g.add_argument("--speed", type=float, default=0.15, help="скорость езды, м/с")
    g.add_argument("--turn-speed", type=float, default=0.6, help="скорость поворота, рад/с")
    g.add_argument("--key-hold", type=float, default=0.45,
                   help="сколько ехать после отпускания клавиши, с")
    g.add_argument("--tol", type=float, default=0.12, help="считать приехавшим ближе, м")
    g.add_argument("--lookahead", type=float, default=0.35, help="упреждение по пути, м")
    g.add_argument("--brake", type=float, default=0.35,
                   help="тормозить, если по курсу что-то ближе, м")
    g.add_argument("--bumper", type=float, default=0.14,
                   help="полуширина коридора бампера, м (корпус 0,199 м плюс запас)")
    g.add_argument("--robot-radius", type=float, default=0.20,
                   help="радиус корпуса для костмапы, м")
    g.add_argument("--inflation", type=float, default=0.20,
                   help="запас вокруг препятствий сверх радиуса, м")
    g.add_argument("--through-unknown", action="store_true",
                   help="разрешить путь через неразведанные клетки")
    g.add_argument("--replan", type=float, default=2.0, help="как часто перестраивать путь, с")
    g.add_argument("--drive-timeout", type=float, default=90.0,
                   help="предел на один переезд, с")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rover = Rover(args.ip, args.web_port, args.scan_topic, args.min_range, args.max_range)
    say(f"ровер {args.ip}: веб {args.web_port}, лидар {args.scan_topic}")
    say(f"пределы скоростей ровера: {rover.read_limits()}")

    grid = Grid(res=args.res, size_m=args.size)
    pose0 = None
    if args.load:
        with open(os.path.join(args.maps, args.load + ".json"), encoding="utf-8") as f:
            data = json.load(f)
        grid = Grid.from_json(data)
        pose0 = data.get("pose")
        say(f"загружена карта «{args.load}»: занятых клеток {grid.hits}")

    mapper = Mapper(rover, grid, args)
    if pose0:
        mapper.set_pose(*pose0)

    # Первый круг делаем в открытую: если лидар не крутится или одометрия стоит,
    # об этом надо узнать сейчас, а не через десять минут пустой карты.
    try:
        pts, age = rover.scan()
        odom = rover.odom()
        say(f"лидар: {len(pts)} точек в работе (возраст {age:.2f} с); "
            f"одометрия: {'есть' if odom else 'НЕТ'}")
        if not pts:
            say("ЛИДАР МОЛЧИТ — мотор не крутится. Заведите его: в rovPult.py команда «н», "
                "или POST /api/ros/service/call {\"service\":\"/start_motor\","
                "\"type\":\"std_srvs/srv/Empty\"}")
        if odom is None:
            say("ОДОМЕТРИИ НЕТ — первый запрос только создаёт подписку, "
                "проверю ещё раз в цикле; если не появится, упал base_driver_node")
    except RoverLinkError as exc:
        say(f"ровер не отвечает ({exc}) — проверьте адрес и питание")

    mapper.start()
    if args.start_mapping:
        say("сбор карты идёт — катайте ровер")
    try:
        return run(rover, mapper, args)
    finally:
        mapper.stop_event.set()


if __name__ == "__main__":
    raise SystemExit(main())
