"""Регламент как чистые функции: ни сети, ни ROS, ни логов.

Источник правил — docs/reglament/gorod_dronov_reglament.md §2.3.2.3:

* заряд ровера: на старте 0, секунда стоянки в зоне зарядки = одно перемещение
  в соседнюю клетку, на нуле движение блокируется;
* «Пожар»: число на маркере = сколько раз съездить за водой; на клетке башни
  ровно 3 с стоянки с мигающей лентой, пропуск аннулирует забор воды.

Миссия «Доставка» здесь не реализована сознательно: команда её не выполняет
(см. PLAN.md, раздел «Область работ»). Поэтому нет ни погрузки на 5 с, ни
эскорта ВУП, ни выбора порядка миссий — миссия попытки ровно одна.

Формулировки правил совпадают с разбором чужого решения в
docs/openclaw/02-regulyament-v-kode.md — потому что и там, и здесь они взяты из
одного регламента. Код при этом наш: лицензии у того репозитория нет, а
регламент запрещает обмен данными между командами.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Iterable, Sequence

from .field import Cell, Field, as_cell

EPS = 1e-9


class EnergyError(Exception):
    """Игровой заряд кончился — движение заблокировано."""


class RouteBlocked(Exception):
    """Маршрут не строится. Не ошибка исполнения, а сигнал планировщику."""


@dataclass(frozen=True)
class RuleSet:
    water_dwell: float = 3.0
    energy_reserve: int = 2
    max_alt: float = 4.0

    @classmethod
    def from_config(cls, cfg) -> "RuleSet":
        return cls(
            water_dwell=float(cfg.get("rules.water_dwell", 3.0)),
            energy_reserve=int(cfg.get("rules.energy_reserve", 2)),
            max_alt=float(cfg.get("rules.max_alt", 4.0)),
        )


DEFAULT_RULES = RuleSet()


# --- игровой заряд ------------------------------------------------------------


class EnergyLedger:
    """Старт 0; +1 за каждую подтверждённую секунду стоянки в зоне зарядки;
    -1 за переезд в соседнюю клетку; на нуле переезд запрещён."""

    def __init__(self) -> None:
        self.energy = 0
        self.charged = 0
        self.spent = 0

    def charge(self, seconds: float) -> int:
        """Начисляет только целые подтверждённые секунды: 2,9 с это 2 единицы."""
        units = int(seconds + EPS)
        if units < 0:
            raise ValueError("отрицательная зарядка")
        self.energy += units
        self.charged += units
        return units

    def can_move(self) -> bool:
        return self.energy > 0

    def spend_move(self) -> int:
        if not self.can_move():
            raise EnergyError("игровой заряд ровера равен нулю, движение заблокировано")
        self.energy -= 1
        self.spent += 1
        return self.energy


# --- валидаторы стоянок -------------------------------------------------------


def dwell_valid(
    seconds: float,
    required: float,
    *,
    moved: bool,
    in_zone: bool,
    led_on: bool,
) -> bool:
    """Стоянка засчитана, только если выполнены все четыре условия сразу."""
    return (not moved) and in_zone and led_on and seconds + EPS >= required


def water_dwell_valid(
    seconds: float, *, moved: bool, in_zone: bool, led_on: bool, rules: RuleSet = DEFAULT_RULES
) -> bool:
    return dwell_valid(seconds, rules.water_dwell, moved=moved, in_zone=in_zone, led_on=led_on)


# --- действия -----------------------------------------------------------------


@dataclass
class Action:
    """Атомарное действие плана вместе с тем, чем будет доказано исполнение."""

    id: str
    kind: str  # drive | dwell | led | note
    mission: str = ""
    cell: Cell | None = None
    path: list[Cell] = dc_field(default_factory=list)
    seconds: float = 0.0
    led: str | None = None
    dwell_kind: str = ""  # water
    event: str = ""  # какое событие пишем в лог для kind="note"
    reason: str = ""
    evidence: tuple[str, ...] = ()

    @property
    def moves(self) -> int:
        return max(0, len(self.path) - 1)


@dataclass
class Route:
    actions: list[Action]
    moves: int
    end: Cell


def _drive(
    field: Field,
    aid: str,
    mission: str,
    start: Cell,
    goal: Cell,
    blocked: Iterable[Sequence[int]],
    reason: str,
) -> Action:
    path = field.astar(start, goal, blocked)
    if path is None:
        raise RouteBlocked(f"нет маршрута {tuple(start)} -> {tuple(goal)}")
    return Action(
        id=aid,
        kind="drive",
        mission=mission,
        cell=as_cell(goal),
        path=path,
        reason=reason,
        evidence=("cell_reached",),
    )


# --- миссия «Пожар» -----------------------------------------------------------


def fire_route(
    field: Field,
    start: Sequence[int],
    fire: Sequence[int],
    level: int,
    tower: Sequence[int],
    rules: RuleSet = DEFAULT_RULES,
) -> Route:
    """Ровно `level` подтверждённых циклов «башня -> 3 с с лентой -> подъезд к пожару».

    В клетку пожара ровер не въезжает никогда: пожар горит в доме. Точка тушения —
    соседняя клетка-дорога, ближайшая к башне.
    """
    start, fire, tower = as_cell(start), as_cell(fire), as_cell(tower)
    if level < 1:
        raise RouteBlocked("уровень пожара меньше единицы — тушить нечего")
    spot = field.approach(fire, tower)
    if spot is None:
        raise RouteBlocked(f"к пожару {fire} не подъехать: все соседние клетки заняты")

    actions: list[Action] = []
    cur = start
    moves = 0
    for i in range(1, level + 1):
        to_tower = _drive(
            field, f"fire-{i}-to-tower", "fire", cur, tower, (),
            f"цикл {i}/{level}: едем за водой к башне {list(tower)}",
        )
        actions.append(to_tower)
        moves += to_tower.moves
        actions.append(
            Action(
                id=f"fire-{i}-water-dwell",
                kind="dwell",
                mission="fire",
                cell=tower,
                seconds=rules.water_dwell,
                led="blink",
                dwell_kind="water",
                reason=f"забор воды: стоянка {rules.water_dwell:g} с с мигающей лентой",
                evidence=("stationary", "led_on", "seconds"),
            )
        )
        to_fire = _drive(
            field, f"fire-{i}-to-fire", "fire", tower, spot, (),
            f"цикл {i}/{level}: подъезд к горящему дому {list(fire)} с клетки {list(spot)}",
        )
        actions.append(to_fire)
        moves += to_fire.moves
        actions.append(
            Action(
                id=f"fire-{i}-done",
                kind="note",
                mission="fire",
                cell=spot,
                event="FIRE_CYCLE",
                reason=f"цикл тушения {i} из {level} подтверждён",
            )
        )
        cur = spot
    actions.append(
        Action(
            id="fire-extinguished",
            kind="note",
            mission="fire",
            cell=fire,
            event="FIRE_EXTINGUISHED",
            reason=f"выполнено циклов подвоза воды: {level} — пожар потушен",
        )
    )
    return Route(actions, moves, cur)


# --- план попытки -------------------------------------------------------------


@dataclass
class Scenario:
    """То, что организаторы выставляют перед попыткой."""

    fire_cell: Cell
    fire_level: int
    tower: Cell
    charge: Cell
    rover_start: Cell
    person_cell: Cell | None = None
    person_window: str = ""

    @classmethod
    def from_config(cls, cfg) -> "Scenario":
        return cls(
            fire_cell=as_cell(cfg.scenario.fire.cell),
            fire_level=int(cfg.scenario.fire.level),
            tower=as_cell(cfg.cells.tower),
            charge=as_cell(cfg.cells.charge),
            rover_start=as_cell(cfg.cells.rover_start),
            person_cell=as_cell(cfg.get("scenario.person.cell", cfg.scenario.fire.cell)),
            person_window=str(cfg.get("scenario.person.window", "")),
        )


def plan_reasons(
    field: Field,
    sc: Scenario,
    rules: RuleSet = DEFAULT_RULES,
) -> list[str]:
    """Человекочитаемое обоснование плана — то, что уходит в лог решений.

    Выбирать между миссиями не приходится: «Доставку» команда не выполняет, так
    что вся попытка это «Пожар». Объяснить всё равно есть что — сколько циклов
    подвоза воды и с какой клетки подъезд к горящему дому.
    """
    spot = field.approach(sc.fire_cell, sc.tower)
    if spot is None:
        raise RouteBlocked(f"к пожару {list(sc.fire_cell)} не подъехать: соседние клетки заняты")
    return [
        "миссия попытки одна: «Пожар» — «Доставку» команда не выполняет (PLAN.md)",
        f"пожар в клетке {list(sc.fire_cell)}, уровень {sc.fire_level} — "
        f"столько же циклов подвоза воды от башни {list(sc.tower)}",
        f"тушим с клетки {list(spot)}: в клетку пожара не въезжаем, "
        "из соседних выбрана ближайшая к башне",
    ]


def compile_plan(
    field: Field,
    sc: Scenario,
    rules: RuleSet = DEFAULT_RULES,
) -> tuple[list[Action], int, Cell]:
    """Собрать список действий попытки с реальной стартовой клетки ровера."""
    route = fire_route(field, sc.rover_start, sc.fire_cell, sc.fire_level, sc.tower, rules)
    return route.actions, route.moves, route.end


def plan_total_energy(
    field: Field,
    sc: Scenario,
    plan_moves: int,
    end: Cell,
    rules: RuleSet = DEFAULT_RULES,
) -> tuple[int, str]:
    """Бюджет предзарядки на весь план и его объяснение для лога.

    К переездам плана добавляется возврат в зону зарядки: ровер не должен
    остаться с нулём вдали от станции, если попытку придётся продолжать.
    """
    back = field.astar(end, sc.charge)
    back_moves = Field.moves(back) if back else 0
    total = plan_moves + back_moves + rules.energy_reserve
    reason = (
        f"переездов по плану {plan_moves} + возврат к зарядке {back_moves} "
        f"+ резерв {rules.energy_reserve} = бюджет {total} ед., "
        f"это {total} с стоянки в зоне зарядки"
    )
    return total, reason
