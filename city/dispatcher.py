"""Агент-диспетчер: разведка -> порядок миссий -> план -> исполнение с доказательствами.

Цикл линейный и читается сверху вниз. Никаких фазовых машин и очередей: на
15-минутную попытку из двух миссий их незачем заводить, а отлаживать в поле
проще то, что видно целиком.
"""

from __future__ import annotations

import os
from typing import Any, Sequence

from .field import Cell, Field, as_cell
from .log import Log
from .robots.base import RobotError
from .rules import (
    EnergyError,
    EnergyLedger,
    RouteBlocked,
    RuleSet,
    Scenario,
    compile_plan,
    dwell_valid,
    escort_lag_ok,
    load_dwell_valid,
    mission_order,
    plan_total_energy,
    water_dwell_valid,
)

MONITOR_ALT = 1.5  # рабочая высота дрона-монитора, м (потолок 4 м, регламент 2.6)
VUP_ALT = 0.7  # рабочая высота ВУП, м
MOVE_TOLERANCE = 0.25  # допуск на дрожание сети при проверке «не двигался», с
CONNECT_WAIT = 10.0  # сколько ждать ответа борта при старте, с (ROS поднимается небыстро)
DRIVE_TIMEOUT = 30.0  # сколько ждать переезда ровера в соседнюю клетку, с


class MissionFailed(Exception):
    """Миссия сорвана. Остальные миссии попытки продолжаются."""


class Dispatcher:
    def __init__(self, cfg, field: Field, log: Log, clock, fleet) -> None:
        self.cfg = cfg
        self.field = field
        self.log = log
        self.clock = clock
        self.fleet = fleet
        self.rules = RuleSet.from_config(cfg)
        self.sc = Scenario.from_config(cfg)
        self.energy = EnergyLedger()
        self.fire_done = False
        self.done_missions: list[str] = []
        self.poll = float(cfg.get("sim.poll", 0.2))

    # --- шаги попытки -------------------------------------------------------

    def run(self) -> int:
        self.log.ev(
            "RUN_START",
            clock=self.clock.name,
            field=[self.field.cols, self.field.rows],
            cell=self.field.cell,
            flags={
                "use_drones": bool(self.cfg.get("flags.use_drones", False)),
                "use_vup": bool(self.cfg.get("flags.use_vup", False)),
                "use_llm": bool(self.cfg.get("flags.use_llm", False)),
            },
            reason="начало зачётной попытки",
        )
        try:
            self.connect()
            self.survey()
            order, reasons = mission_order(
                self.field, self.sc, self._dangers(), self.rules
            )
            self.log.ev(
                "MISSION_ORDER",
                order=order,
                reasons=reasons,
                reason="; ".join(reasons),
            )

            actions, moves, end = compile_plan(self.field, self.sc, order, self.rules)
            budget, budget_reason = plan_total_energy(
                self.field, self.sc, moves, end, self.rules
            )
            self.log.ev(
                "PLAN",
                actions=len(actions),
                moves=moves,
                end=list(end),
                reason=f"скомпилировано {len(actions)} действий на {moves} переездов",
            )

            self.precharge(budget, budget_reason)
            self.execute(actions, order)
        except (RouteBlocked, EnergyError, MissionFailed) as exc:
            self.log.ev("ERROR", error=type(exc).__name__, reason=str(exc))
            self.fleet.stop_all()
            return 1
        except RobotError as exc:
            self.log.ev("ERROR", error="RobotError", reason=str(exc))
            self.log.ev("SAFETY", action="stop_all", reason="отказ борта — глушим все аппараты")
            self.fleet.stop_all()
            return 1

        ok = len(self.done_missions) == 2
        self.log.ev(
            "DONE",
            missions=self.done_missions,
            energy_spent=self.energy.spent,
            energy_left=self.energy.energy,
            reason="попытка завершена" if ok else "попытка завершена не полностью",
        )
        return 0 if ok else 1

    def connect(self) -> None:
        """Перекличка бортов до старта: кто ответил, где стоит и не заглушка ли он."""
        wait = CONNECT_WAIT if self.fleet.transport == "http" else 0.0
        report = self.fleet.connect(wait=wait)
        for entry in report:
            if entry.get("error"):
                reason = f"борт не вышел на связь: {entry['error']}"
            elif entry.get("dry"):
                reason = (
                    "ВНИМАНИЕ: на том конце программа-заглушка. Она отвечает как аппарат, "
                    "но ничего не делает — этот прогон не считается за проверку железа"
                )
            else:
                reason = f"борт на связи, состояние «{entry.get('state')}»"
            self.log.ev("ROBOT", **entry, reason=reason)

        # Без ровера обе миссии невыполнимы: тратить время на планирование и
        # зарядку, чтобы упасть на первом же переезде, — худший способ узнать это.
        rover = next((e for e in report if e["role"] == "rover"), None)
        if rover and rover.get("error"):
            raise RobotError(f"ровер не на связи, попытка не начинается: {rover['error']}")

    def survey(self) -> None:
        """Откуда берётся картина поля. С этапа 3 сюда встанут кадры мониторов."""
        if self.cfg.get("flags.use_drones", False) and self.fleet.monitors:
            self._survey_by_drones()
        else:
            self.log.ev(
                "SURVEY",
                source="config",
                fire=list(self.sc.fire_cell),
                fire_level=self.sc.fire_level,
                pickup=list(self.sc.pickup),
                dropoff=list(self.sc.dropoff),
                reason="дроны-мониторы выключены, сцена взята из config.yaml",
            )

    def _survey_by_drones(self) -> None:
        """Взлёт-кадр-посадка по всем мониторам. Разбор кадров — этап 3."""
        paths: list[str] = []
        for name, drone in self.fleet.monitors.items():
            try:
                drone.takeoff(MONITOR_ALT)
                self._wait_state(drone, ("hover",), timeout=20.0)
                frame = drone.shot()
                paths.append(self.save_shot(name, frame))
                drone.land()
                self._wait_state(drone, ("landed", "idle"), timeout=25.0)
            except RobotError as exc:
                self.log.ev(
                    "ERROR",
                    error="RobotError",
                    drone=name,
                    reason=f"монитор {name} не отдал кадр: {exc}",
                )
        self.log.ev(
            "SURVEY",
            source="drones",
            shots=len(paths),
            files=paths,
            fire=list(self.sc.fire_cell),
            fire_level=self.sc.fire_level,
            reason=(
                f"снято кадров: {len(paths)}; разбор кадров появится на этапе 3, "
                "пока сцена всё ещё из config.yaml"
            ),
        )

    def save_shot(self, name: str, frame: bytes) -> str:
        """Кадр на диск: это и материал техзащиты, и способ увидеть, что снял дрон."""
        folder = os.path.join(os.path.dirname(self.log.path), "shots")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{name}-{self.clock.now():07.1f}.jpg")
        with open(path, "wb") as fh:
            fh.write(frame)
        return path

    def _wait_cell(self, robot, cell: Cell, timeout: float) -> bool:
        """Дождаться, пока аппарат реально приедет в клетку.

        Команда принимается мгновенно, а едет ровер секунды: считать переезд
        выполненным по факту принятия команды нельзя — тогда и заряд, и стоянки
        считались бы по несуществующим событиям.
        """
        t0 = self.clock.now()
        while self.clock.now() - t0 < timeout:
            st = robot.status()
            if as_cell(st["cell"]) == cell and not st.get("busy"):
                return True
            self.clock.sleep(self.poll)
        raise RobotError(
            f"{getattr(robot, 'name', '?')}: за {timeout:g} с не доехал до {list(cell)}"
        )

    def _wait_state(self, robot, states: tuple[str, ...], timeout: float) -> bool:
        """Дождаться состояния борта. Команда принимается сразу, исполняется в фоне."""
        t0 = self.clock.now()
        while self.clock.now() - t0 < timeout:
            if robot.status().get("state") in states:
                return True
            self.clock.sleep(self.poll)
        raise RobotError(
            f"{getattr(robot, 'name', '?')}: за {timeout:g} с не дождались "
            f"состояния {'/'.join(states)}"
        )

    def precharge(self, budget: int, reason: str) -> None:
        """Зарядка на весь план сразу: 1 секунда стоянки = 1 переезд."""
        rover = self.fleet.rover
        cell = as_cell(rover.status()["cell"])
        if cell != self.sc.charge:
            raise RouteBlocked(
                f"ровер стоит в {list(cell)}, а зона зарядки {list(self.sc.charge)}: "
                "на старте заряд нулевой, доехать до станции нечем"
            )
        measured, moved, in_zone, _ = self._hold(rover, self.sc.charge, float(budget))
        if not dwell_valid(measured, float(budget), moved=moved, in_zone=in_zone, led_on=True):
            raise MissionFailed("зарядка не засчитана: ровер двигался или вышел из зоны")
        units = self.energy.charge(measured)
        self.log.ev(
            "CHARGED",
            units=units,
            seconds=round(measured, 2),
            cell=list(self.sc.charge),
            energy=self.energy.energy,
            reason=reason,
        )

    def execute(self, actions: Sequence[Any], order: Sequence[str]) -> None:
        for mission in order:
            mission_actions = [a for a in actions if a.mission == mission]
            try:
                self._start_mission(mission)
                for action in mission_actions:
                    self._do(action)
                self.done_missions.append(mission)
            except MissionFailed as exc:
                self.log.ev(
                    "ERROR",
                    error="MissionFailed",
                    mission=mission,
                    reason=str(exc),
                )
            except EnergyError as exc:
                self.log.ev(
                    "ENERGY_BLOCK",
                    mission=mission,
                    energy=self.energy.energy,
                    reason=str(exc),
                )
            finally:
                self._end_mission(mission)

    # --- исполнение действий ------------------------------------------------

    def _do(self, action) -> None:
        if action.kind == "drive":
            self._do_drive(action)
        elif action.kind == "dwell":
            self._do_dwell(action)
        elif action.kind == "led":
            self.fleet.rover.led(action.led)
            self.log.ev("LED", mode=action.led, action=action.id, reason=action.reason)
        elif action.kind == "note":
            self._do_note(action)
        else:
            raise MissionFailed(f"неизвестный вид действия {action.kind!r}")

    def _do_drive(self, action) -> None:
        rover = self.fleet.rover
        for i, nxt in enumerate(action.path[1:]):
            prev = as_cell(rover.status()["cell"])
            if not self.energy.can_move():
                raise EnergyError(
                    f"игровой заряд кончился на пути в {list(action.cell)}, "
                    "движение ровера заблокировано"
                )
            rover.drive(nxt)
            self._wait_cell(rover, as_cell(nxt), timeout=DRIVE_TIMEOUT)
            self.energy.spend_move()
            fields = {
                "action": action.id,
                "from": list(prev),
                "cell": list(as_cell(nxt)),
                "energy": self.energy.energy,
            }
            if i == 0:  # причина у первого переезда участка, дальше она бы повторялась
                fields["reason"] = action.reason
            self.log.ev("MOVE", **fields)
            self._escort_step(prev, action)

    def _do_dwell(self, action) -> None:
        rover = self.fleet.rover
        if action.led:
            rover.led(action.led)
        measured, moved, in_zone, led_on = self._hold(rover, action.cell, action.seconds)
        check = water_dwell_valid if action.dwell_kind == "water" else load_dwell_valid
        counted = check(measured, moved=moved, in_zone=in_zone, led_on=led_on, rules=self.rules)
        self.log.ev(
            "DWELL",
            action=action.id,
            kind=action.dwell_kind,
            cell=list(action.cell),
            seconds=round(measured, 2),
            led=rover.status().get("led"),
            moved=moved,
            counted=counted,
            reason=action.reason,
        )
        if not counted:
            raise MissionFailed(
                f"стоянка {action.id} не засчитана "
                f"(секунд={measured:.2f} движение={moved} в_клетке={in_zone} лента={led_on}) — "
                "по регламенту результат этого шага аннулируется"
            )

    def _do_note(self, action) -> None:
        if action.event == "FIRE_EXTINGUISHED":
            self.fire_done = True
        self.log.ev(
            action.event,
            action=action.id,
            cell=list(action.cell) if action.cell else None,
            reason=action.reason,
        )

    def _hold(self, rover, cell: Cell | None, seconds: float) -> tuple[float, bool, bool, bool]:
        """Простоять `seconds` и вернуть доказательства: сколько, двигался ли, где, лента.

        Время меряется по часам системы, а не по факту вызова sleep: на железе
        сюда встанет опрос /status, и стоянка будет подтверждаться телеметрией.
        """
        t0 = self.clock.now()
        target = as_cell(cell) if cell is not None else as_cell(rover.status()["cell"])
        while True:
            left = seconds - (self.clock.now() - t0)
            if left <= 1e-9:
                break
            self.clock.sleep(min(self.poll, left))
            rover.status()  # опрос вслепую: борт должен отвечать всю стоянку
        st = rover.status()
        measured = self.clock.now() - t0
        # Аппарат сообщает, сколько секунд назад он двигался. Если это меньше, чем
        # длилась стоянка, — он дёрнулся посреди неё, и по регламенту шаг не засчитан.
        moved = st.get("since_move", 0.0) + MOVE_TOLERANCE < measured
        in_zone = as_cell(st["cell"]) == target
        led_on = st.get("led") in ("on", "blink")
        return measured, moved, in_zone, led_on

    # --- ВУП ----------------------------------------------------------------

    def _start_mission(self, mission: str) -> None:
        if mission == "fire":
            self._vup_person_search()
        elif mission == "delivery":
            if not self.fleet.vup:
                self.log.ev(
                    "VUP_ABSENT",
                    mission="delivery",
                    missing=["delivery_escort"],
                    reason=(
                        "воздушного эскорта не будет: микродрона нет, компенсировать "
                        "его нечем — пункт задания остаётся незакрытым"
                    ),
                )
                return
            self.fleet.vup.takeoff(VUP_ALT)
            self._wait_state(self.fleet.vup, ("hover",), timeout=20.0)
            self.log.ev(
                "ESCORT",
                state="launched",
                alt=VUP_ALT,
                reason="ВУП поднят на эскорт доставки, идёт строго сзади ровера",
            )

    def _end_mission(self, mission: str) -> None:
        if mission == "delivery" and self.fleet.vup:
            try:
                self.fleet.vup.land()
                self._wait_state(self.fleet.vup, ("landed", "idle"), timeout=25.0)
                self.log.ev("ESCORT", state="landed", reason="доставка завершена, ВУП сел")
            except RobotError as exc:
                self.log.ev("ERROR", error="RobotError", reason=f"ВУП не сел: {exc}")

    def _vup_person_search(self) -> None:
        """Поиск человека в окне горящего здания. Без аппарата — честный отказ."""
        if not self.fleet.vup:
            self.log.ev(
                "VUP_ABSENT",
                mission="fire",
                missing=["person_detection_in_window"],
                reason=(
                    "человека в окне искать нечем: ВУП отсутствует, а разбор кадра "
                    "монитора появится на этапах 3 и 8"
                ),
            )
            return
        vup = self.fleet.vup
        vup.takeoff(VUP_ALT)
        self._wait_state(vup, ("hover",), timeout=20.0)
        vup.goto(self.sc.fire_cell, VUP_ALT)
        self._wait_state(vup, ("hover",), timeout=30.0)
        self.save_shot("vup", vup.shot())
        vup.land()
        self._wait_state(vup, ("landed", "idle"), timeout=25.0)
        self.log.ev(
            "PERSON_FOUND",
            found=None,
            source="vup",
            cell=list(self.sc.fire_cell),
            reason=(
                "кадр окна снят, но детектора ещё нет (этапы 3 и 8): "
                "результат не выдумываем"
            ),
        )

    def _escort_step(self, prev_cell: Cell, action) -> None:
        """Эскорт встаёт на предыдущую клетку ровера, отставание считаем манхэттенски."""
        vup = self.fleet.vup
        if not vup or action.mission != "delivery":
            return
        vup.goto(prev_cell, VUP_ALT)
        # Ждём, пока эскорт долетит: иначе отставание считалось бы по клетке,
        # в которую дрон только собирается прибыть.
        self._wait_state(vup, ("hover",), timeout=30.0)
        rover_cell = as_cell(self.fleet.rover.status()["cell"])
        vup_cell = as_cell(vup.status()["cell"])
        ok = escort_lag_ok(rover_cell, vup_cell, self.rules)
        lag = abs(rover_cell[0] - vup_cell[0]) + abs(rover_cell[1] - vup_cell[1])
        self.log.ev(
            "ESCORT",
            state="follow" if ok else "violation",
            rover=list(rover_cell),
            vup=list(vup_cell),
            lag=lag,
            reason=(
                f"отставание эскорта {lag} при пределе {self.rules.escort_max_lag}"
                if ok
                else f"отставание эскорта {lag} превысило предел {self.rules.escort_max_lag}"
            ),
        )

    def _dangers(self) -> dict[str, int]:
        return {
            "fire": int(self.cfg.get("missions.fire.danger", 3)),
            "delivery": int(self.cfg.get("missions.delivery.danger", 1)),
        }
