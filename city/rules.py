"""Регламент как чистые функции: ни сети, ни ROS, ни логов.

Источник правил — docs/reglament/gorod_dronov_reglament.md §2.3.2.3:

* заряд ровера: на старте 0, секунда стоянки в зоне зарядки = одно перемещение
  в соседнюю клетку, на нуле движение блокируется;
* «Пожар»: число на маркере = сколько раз съездить за водой; на клетке башни
  ровно 3 с стоянки с мигающей лентой, пропуск аннулирует забор воды;
* «Доставка»: ровно 5 с погрузки со светодиодом, мигалка включена всю миссию,
  пока пожар не потушен — ехать через горящую клетку нельзя;
* ВУП: эскорт строго сзади, отставание не более двух клеток.

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
    load_dwell: float = 5.0
    escort_max_lag: int = 2
    energy_reserve: int = 2
    max_alt: float = 4.0

    @classmethod
    def from_config(cls, cfg) -> "RuleSet":
        return cls(
            water_dwell=float(cfg.get("rules.water_dwell", 3.0)),
            load_dwell=float(cfg.get("rules.load_dwell", 5.0)),
            escort_max_lag=int(cfg.get("rules.escort_max_lag", 2)),
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


def load_dwell_valid(
    seconds: float, *, moved: bool, in_zone: bool, led_on: bool, rules: RuleSet = DEFAULT_RULES
) -> bool:
    return dwell_valid(seconds, rules.load_dwell, moved=moved, in_zone=in_zone, led_on=led_on)


def escort_lag_ok(rover: Sequence[int], vup: Sequence[int], rules: RuleSet = DEFAULT_RULES) -> bool:
    """Отставание эскорта считается манхэттенски (регламент: не более 2 клеток)."""
    (rc, rr), (vc, vr) = as_cell(rover), as_cell(vup)
    return abs(rc - vc) + abs(rr - vr) <= rules.escort_max_lag


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
    dwell_kind: str = ""  # water | load
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


# --- миссия «Доставка» --------------------------------------------------------


def delivery_route(
    field: Field,
    start: Sequence[int],
    pickup: Sequence[int],
    dropoff: Sequence[int],
    rules: RuleSet = DEFAULT_RULES,
    blocked: Iterable[Sequence[int]] = (),
) -> Route:
    """Мигалка на всю миссию, 5 с погрузки со светодиодом, финиш в обход пожара."""
    start, pickup, dropoff = as_cell(start), as_cell(pickup), as_cell(dropoff)
    actions: list[Action] = [
        Action(
            id="delivery-beacon-on",
            kind="led",
            mission="delivery",
            led="blink",
            reason="мигалка включается на всю миссию доставки (регламент, п. 6)",
        )
    ]
    to_pickup = _drive(
        field, "delivery-to-pickup", "delivery", start, pickup, blocked,
        f"едем на старт доставки {list(pickup)}",
    )
    actions.append(to_pickup)
    actions.append(
        Action(
            id="delivery-load-dwell",
            kind="dwell",
            mission="delivery",
            cell=pickup,
            seconds=rules.load_dwell,
            led="blink",
            dwell_kind="load",
            reason=f"погрузка: стоянка {rules.load_dwell:g} с со светодиодом",
            evidence=("stationary", "led_on", "seconds"),
        )
    )
    to_dropoff = _drive(
        field, "delivery-to-dropoff", "delivery", pickup, dropoff, blocked,
        f"везём груз на финиш {list(dropoff)}",
    )
    actions.append(to_dropoff)
    actions.append(
        Action(
            id="delivery-done",
            kind="note",
            mission="delivery",
            cell=dropoff,
            event="DELIVERY_DONE",
            reason="груз доставлен на финишную клетку",
        )
    )
    actions.append(
        Action(
            id="delivery-beacon-off",
            kind="led",
            mission="delivery",
            led="off",
            reason="миссия завершена, мигалку можно выключить",
        )
    )
    return Route(actions, to_pickup.moves + to_dropoff.moves, dropoff)


# --- порядок миссий -----------------------------------------------------------


@dataclass
class Scenario:
    """То, что организаторы выставляют перед попыткой."""

    fire_cell: Cell
    fire_level: int
    pickup: Cell
    dropoff: Cell
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
            pickup=as_cell(cfg.scenario.delivery.pickup),
            dropoff=as_cell(cfg.scenario.delivery.dropoff),
            tower=as_cell(cfg.cells.tower),
            charge=as_cell(cfg.cells.charge),
            rover_start=as_cell(cfg.cells.rover_start),
            person_cell=as_cell(cfg.get("scenario.person.cell", cfg.scenario.fire.cell)),
            person_window=str(cfg.get("scenario.person.window", "")),
        )


def mission_order(
    field: Field,
    sc: Scenario,
    dangers: dict[str, int],
    rules: RuleSet = DEFAULT_RULES,
) -> tuple[list[str], list[str]]:
    """Порядок миссий и человекочитаемые причины выбора.

    score = danger * 10 - стоимость в переездах; плюс жёсткий предшественник:
    если доставка не объезжает непотушенный пожар, «Пожар» ставится первым.
    Стоимости здесь оценочные — обе миссии считаются от зоны зарядки; итоговый
    план всё равно пересчитывается compile_plan от фактических клеток.
    """
    reasons: list[str] = []
    costs: dict[str, int] = {}

    fire = fire_route(field, sc.charge, sc.fire_cell, sc.fire_level, sc.tower, rules)
    costs["fire"] = fire.moves

    delivery_needs_fire = False
    try:
        delivery = delivery_route(
            field, sc.charge, sc.pickup, sc.dropoff, rules, blocked=[sc.fire_cell]
        )
        costs["delivery"] = delivery.moves
    except RouteBlocked:
        delivery_needs_fire = True
        delivery = delivery_route(field, sc.charge, sc.pickup, sc.dropoff, rules)
        costs["delivery"] = delivery.moves

    scores = {m: dangers.get(m, 0) * 10 - costs[m] for m in ("fire", "delivery")}
    order = sorted(scores, key=lambda m: (-scores[m], m))
    for m in order:
        reasons.append(
            f"{m}: опасность {dangers.get(m, 0)} x10 - {costs[m]} переездов = {scores[m]}"
        )

    if delivery_needs_fire and order[0] != "fire":
        order = ["fire"] + [m for m in order if m != "fire"]
        reasons.append("доставка не проходит мимо пожара — сначала тушим")
    elif delivery_needs_fire:
        reasons.append("доставка объезжает пожар только после тушения — порядок сохранён")
    return order, reasons


def compile_plan(
    field: Field,
    sc: Scenario,
    order: Sequence[str],
    rules: RuleSet = DEFAULT_RULES,
) -> tuple[list[Action], int, Cell]:
    """Собрать единый список действий по обеим миссиям с реальных позиций ровера."""
    actions: list[Action] = []
    cur: Cell = sc.rover_start
    moves = 0
    fire_done = False
    for mission in order:
        if mission == "fire":
            route = fire_route(field, cur, sc.fire_cell, sc.fire_level, sc.tower, rules)
            fire_done = True
        elif mission == "delivery":
            blocked = () if fire_done else [sc.fire_cell]
            route = delivery_route(field, cur, sc.pickup, sc.dropoff, rules, blocked=blocked)
        else:
            raise RouteBlocked(f"неизвестная миссия {mission!r}")
        actions.extend(route.actions)
        moves += route.moves
        cur = route.end
    return actions, moves, cur


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
