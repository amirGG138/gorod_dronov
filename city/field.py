"""Модель игрового поля: клетка <-> метры, соседи, A*.

Поле 6x6 клеток по 0,8 м (регламент 2.3.2.2). Клетка всюду — кортеж
(col, row), 0-based: col вдоль оси X карты, row вдоль оси Y.

Привязка к метрам взята из нашей карты маркеров (docs/field-map/README.md):
начало координат map совпадает с центром поля, поэтому
x = (col - 2.5) * 0.8, y = (row - 2.5) * 0.8. Якорь (x0, y0, yaw) оставлен на
случай, если на площадке карта окажется сдвинутой или повёрнутой.
"""

from __future__ import annotations

import heapq
import math
from typing import Iterable, Sequence

Cell = tuple[int, int]

# Порядок соседей фиксирован: при равной стоимости A* всегда даёт один и тот же
# маршрут, иначе таймлайн демо «плавает» от прогона к прогону.
_STEPS = ((0, 1), (1, 0), (0, -1), (-1, 0))


def as_cell(value: Sequence[int]) -> Cell:
    col, row = value
    return (int(col), int(row))


class Field:
    def __init__(
        self,
        size: Sequence[int] = (6, 6),
        cell: float = 0.8,
        buildings: Iterable[Sequence[int]] = (),
        origin: Sequence[float] = (0.0, 0.0, 0.0),
    ) -> None:
        self.cols, self.rows = int(size[0]), int(size[1])
        self.cell = float(cell)
        self.buildings: frozenset[Cell] = frozenset(as_cell(c) for c in buildings)
        self.x0, self.y0, self.yaw = (float(v) for v in origin)

    @classmethod
    def from_config(cls, cfg) -> "Field":
        return cls(
            size=cfg.field.size,
            cell=cfg.field.cell,
            buildings=cfg.get("cells.buildings", []),
            origin=(
                cfg.get("field.origin.x0", 0.0),
                cfg.get("field.origin.y0", 0.0),
                cfg.get("field.origin.yaw", 0.0),
            ),
        )

    # --- геометрия ----------------------------------------------------------

    def cell_to_m(self, cell: Sequence[int]) -> tuple[float, float]:
        col, row = as_cell(cell)
        lx = (col - (self.cols - 1) / 2.0) * self.cell
        ly = (row - (self.rows - 1) / 2.0) * self.cell
        cos_a, sin_a = math.cos(self.yaw), math.sin(self.yaw)
        return (self.x0 + lx * cos_a - ly * sin_a, self.y0 + lx * sin_a + ly * cos_a)

    def m_to_cell(self, x: float, y: float) -> Cell:
        dx, dy = x - self.x0, y - self.y0
        cos_a, sin_a = math.cos(-self.yaw), math.sin(-self.yaw)
        lx, ly = dx * cos_a - dy * sin_a, dx * sin_a + dy * cos_a
        col = round(lx / self.cell + (self.cols - 1) / 2.0)
        row = round(ly / self.cell + (self.rows - 1) / 2.0)
        return (int(col), int(row))

    # --- четверти поля ------------------------------------------------------

    def quadrant(self, cell: Sequence[int]) -> Cell:
        """В какой четверти поля лежит клетка: (0|1, 0|1) по осям col и row.

        Четверть — это доля поля, за которую отвечает один дрон-монитор (этап 8).
        Деление ровно пополам по каждой оси: на поле 6x6 четверть выходит блоком
        3x3, и площадки [1,1] [4,1] [1,4] [4,4] оказываются в их центрах — то есть
        дрон, висящий над своей меткой, снимает середину своей четверти.
        """
        col, row = as_cell(cell)
        return (0 if col * 2 < self.cols else 1, 0 if row * 2 < self.rows else 1)

    def quadrant_cells(self, quad: Sequence[int]) -> list[Cell]:
        """Все клетки четверти, слева направо и снизу вверх."""
        qx, qy = as_cell(quad)
        return [
            (col, row)
            for row in range(self.rows)
            for col in range(self.cols)
            if self.quadrant((col, row)) == (qx, qy)
        ]

    def quadrant_name(self, quad: Sequence[int]) -> str:
        """Название четверти по-русски: так её видит человек в логе и на техзащите."""
        qx, qy = as_cell(quad)
        return f"{'дальняя' if qy else 'ближняя'} {'правая' if qx else 'левая'}"

    def cells(self) -> list[Cell]:
        """Все клетки поля, слева направо и снизу вверх."""
        return [(col, row) for row in range(self.rows) for col in range(self.cols)]

    # --- связность ----------------------------------------------------------

    def in_bounds(self, cell: Sequence[int]) -> bool:
        col, row = as_cell(cell)
        return 0 <= col < self.cols and 0 <= row < self.rows

    def is_road(self, cell: Sequence[int]) -> bool:
        return self.in_bounds(cell) and as_cell(cell) not in self.buildings

    def neighbors(self, cell: Sequence[int], blocked: Iterable[Sequence[int]] = ()) -> list[Cell]:
        col, row = as_cell(cell)
        stop = {as_cell(c) for c in blocked}
        out = []
        for dcol, drow in _STEPS:
            nxt = (col + dcol, row + drow)
            if self.is_road(nxt) and nxt not in stop:
                out.append(nxt)
        return out

    def astar(
        self,
        start: Sequence[int],
        goal: Sequence[int],
        blocked: Iterable[Sequence[int]] = (),
    ) -> list[Cell] | None:
        """Кратчайший путь по клеткам-дорогам или None, если его нет."""
        start, goal = as_cell(start), as_cell(goal)
        stop = {as_cell(c) for c in blocked}
        if not self.is_road(goal) or goal in stop or not self.in_bounds(start):
            return None
        if start == goal:
            return [start]

        def h(c: Cell) -> int:
            return abs(c[0] - goal[0]) + abs(c[1] - goal[1])

        seq = 0
        heap = [(h(start), 0, seq, start)]
        best = {start: 0}
        came: dict[Cell, Cell] = {}
        while heap:
            _, cost, _, cur = heapq.heappop(heap)
            if cur == goal:
                path = [cur]
                while cur in came:
                    cur = came[cur]
                    path.append(cur)
                return path[::-1]
            if cost > best.get(cur, cost):
                continue
            for nxt in self.neighbors(cur, stop):
                new = cost + 1
                if new < best.get(nxt, 1 << 30):
                    best[nxt] = new
                    came[nxt] = cur
                    seq += 1
                    heapq.heappush(heap, (new + h(nxt), new, seq, nxt))
        return None

    def approach(
        self,
        target: Sequence[int],
        prefer: Sequence[int],
        blocked: Iterable[Sequence[int]] = (),
    ) -> Cell | None:
        """Клетка-дорога рядом с target, ближайшая по пути к prefer.

        Так выбирается место, откуда ровер тушит горящий дом: въезжать в клетку
        пожара нельзя, а подъезжать выгоднее со стороны водонапорной башни —
        цикл «башня -> пожар» получается короче.
        """
        target = as_cell(target)
        stop = {as_cell(c) for c in blocked}
        best: tuple[int, Cell] | None = None
        for dcol, drow in _STEPS:
            cand = (target[0] + dcol, target[1] + drow)
            if not self.is_road(cand) or cand in stop:
                continue
            path = self.astar(prefer, cand, stop)
            if path is None:
                continue
            key = (len(path) - 1, cand)
            if best is None or key < best:
                best = key
        return None if best is None else best[1]

    @staticmethod
    def moves(path: Sequence[Cell] | None) -> int:
        """Число переездов в пути = его стоимость в единицах игрового заряда."""
        return 0 if not path else len(path) - 1
