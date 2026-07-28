"""Агент-диспетчер: разведка -> план -> исполнение с доказательствами.

Цикл линейный и читается сверху вниз. Никаких фазовых машин и очередей: на
15-минутную попытку их незачем заводить, а отлаживать в поле проще то, что
видно целиком.

Миссия попытки одна — «Пожар»: «Доставку» команда не выполняет (PLAN.md).
"""

from __future__ import annotations

import math
import os
import sys
from typing import Any, Sequence

from . import vision
from .brain import Brain
from .field import Cell, Field, as_cell
from .log import Log
from .robots.base import RobotError
from .rules import (
    EnergyError,
    EnergyLedger,
    RouteBlocked,
    RuleSet,
    Scenario,
    approach_options,
    budget_for,
    check_proposal,
    compile_plan,
    dwell_valid,
    plan_reasons,
    plan_total_energy,
    water_dwell_valid,
)

MONITOR_ALT = 1.5  # рабочая высота дрона-монитора, м (потолок 4 м, регламент 2.6)
VUP_ALT = 0.7  # рабочая высота ВУП, м
# Состояния борта, означающие «дрон не в воздухе». landed_unverified — посадка, за
# которую борт не поручился (onboard/drone_agent.py): ждать её надо как посадки, а
# писать в лог — как неподтверждённую.
ON_GROUND = ("landed", "landed_unverified", "idle")
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
        # Разведка: куда лететь и как разбирать кадры. Настройки читаются один раз,
        # чтобы на площадке правился только config.yaml, а не код.
        self.pads = vision.pads_from_config(cfg)
        self.vision_settings = vision.settings(cfg)
        self.survey_alt = float(cfg.get("survey.alt", MONITOR_ALT))
        # Мониторы, чья посадка не подтвердилась: попадают в лог разведки, чтобы
        # «сел» на пульте не расходилось с тем, что видно глазами над полем.
        self.unverified: list[str] = []
        # Модель. Создаётся всегда, работает только при flags.use_llm и никогда не
        # находится в цепи управления: её предложения проходят через rules.py.
        self.brain = Brain(cfg)
        # Кадр, на котором лучше всего видно очаг: его же показываем VLM.
        self.fire_shot: str = ""

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
            reasons = plan_reasons(self.field, self.sc, self.rules)
            advice = self.advise_plan()
            spot = advice.spot if advice else None
            fields: dict[str, Any] = {"reasons": reasons, "reason": "; ".join(reasons)}
            llm_reason = self.explain(
                "выбор плана тушения",
                {
                    "fire": list(self.sc.fire_cell),
                    "level": self.sc.fire_level,
                    "tower": list(self.sc.tower),
                    "approach": list(spot) if spot else None,
                    "правила": reasons,
                },
            )
            if llm_reason:
                fields["llm_reason"] = llm_reason
            self.log.ev("PLAN_CHOSEN", mission="fire", **fields)

            actions, moves, end = compile_plan(self.field, self.sc, self.rules, spot=spot)
            budget, budget_reason = plan_total_energy(
                self.field, self.sc, moves, end, self.rules
            )
            if advice and advice.budget > budget:
                # Модель вправе взять запас БОЛЬШЕ расчётного — это её единственная
                # свобода в бюджете, и она уже ограничена сверху в check_proposal.
                budget_reason += (
                    f"; по предложению модели бюджет поднят до {advice.budget} ед."
                )
                budget = advice.budget
            self.log.ev(
                "PLAN",
                actions=len(actions),
                moves=moves,
                end=list(end),
                reason=f"скомпилировано {len(actions)} действий на {moves} переездов",
            )

            self.precharge(budget, budget_reason)
            self.execute(actions)
        except KeyboardInterrupt:
            # Ctrl+C посреди попытки — это человек, а не сбой; аппараты об этом не
            # знают и продолжают лететь и ехать, пока им не сказали обратное.
            self.log.ev("ERROR", error="KeyboardInterrupt", reason="попытку прервали с клавиатуры")
            self.emergency_stop("попытку прервал оператор")
            return 1
        except (RouteBlocked, EnergyError, MissionFailed) as exc:
            self.log.ev("ERROR", error=type(exc).__name__, reason=str(exc))
            self.emergency_stop("план сорвался — глушим все аппараты")
            return 1
        except RobotError as exc:
            self.log.ev("ERROR", error="RobotError", reason=str(exc))
            self.emergency_stop("отказ борта — глушим все аппараты")
            return 1
        except Exception as exc:  # noqa: BLE001 — сбой диспетчера не повод бросать аппараты
            self.log.ev(
                "ERROR",
                error=type(exc).__name__,
                reason=f"непредвиденный сбой диспетчера: {exc}",
            )
            self.emergency_stop("непредвиденный сбой диспетчера")
            raise  # трассировка нужна: это наша ошибка, и её надо увидеть целиком

        ok = "fire" in self.done_missions
        done: dict[str, Any] = {
            "missions": self.done_missions,
            "energy_spent": self.energy.spent,
            "energy_left": self.energy.energy,
            "reason": "попытка завершена" if ok else "попытка завершена не полностью",
        }
        summary = self.explain(
            "итог попытки",
            {
                "missions": self.done_missions,
                "fire_done": self.fire_done,
                "energy_spent": self.energy.spent,
                "energy_left": self.energy.energy,
            },
        )
        if summary:
            done["llm_reason"] = summary
        self.log.ev("DONE", **done)
        return 0 if ok else 1

    def emergency_stop(self, why: str) -> list[dict[str, Any]]:
        """Остановить всё и записать, кого остановить не удалось.

        Раньше отказ на «стоп» глушился молча, и лог аварии выглядел так же, как
        лог успешной остановки. Аппарат, не принявший команду, — единственный повод
        жать KILL SWITCH руками, поэтому он попадает и в лог, и на экран: сообщение
        идёт в stderr, чтобы его было видно даже при запуске с --quiet.
        """
        report = self.fleet.stop_all()
        failed = [e["name"] for e in report if not e["stopped"]]
        self.log.ev(
            "SAFETY",
            action="stop_all",
            robots=report,
            failed=failed,
            reason=(
                f"{why}; не остановлены: {', '.join(failed)}"
                if failed
                else f"{why}; остановлены все ({len(report)})"
            ),
        )
        if failed:
            print(
                "\n!!! НЕ ОСТАНОВЛЕНЫ: " + ", ".join(failed) + "\n"
                "!!! ЖМИТЕ KILL SWITCH РУКАМИ — команда до аппарата не дошла\n",
                file=sys.stderr,
                flush=True,
            )
        return report

    # --- модель --------------------------------------------------------------

    def _llm(self, ans, accepted: bool | None = None, reason: str = "") -> None:
        """Записать обращение к модели. Пишется и удача, и отказ, и отклонённый ответ.

        Без этой записи нельзя ответить судье на вопрос «а работала ли у вас модель
        в этом прогоне» — и нельзя отличить рабочий шлюз от молчащего, который
        подменяется детерминированным путём (та самая ловушка «демо есть, LLM нет»).
        """
        if not reason:
            reason = (ans.text or "модель ответила") if ans.ok else ans.error
        self.log.ev(
            "LLM",
            use=ans.use,
            model=ans.model,
            ok=ans.ok,
            ms=ans.ms,
            accepted=accepted,
            answer=ans.data or None,
            reason=reason,
        )

    def advise_plan(self):
        """Спросить модель про план и пропустить ответ через правила.

        Возвращает приговор `rules.check_proposal`, если он положительный, иначе
        None — и тогда план строится детерминированно, как без модели вовсе.
        """
        if not self.brain.wants("plan"):
            return None
        options = approach_options(self.field, self.sc)
        base, base_reason = budget_for(
            self.field, self.sc, options[0] if options else None, self.rules
        )
        facts = {
            "field": [self.field.cols, self.field.rows],
            "fire": list(self.sc.fire_cell),
            "level": self.sc.fire_level,
            "tower": list(self.sc.tower),
            "charge": list(self.sc.charge),
            "rover_start": list(self.sc.rover_start),
            "candidates": [list(c) for c in options],
            "base_budget": base,
            "base_budget_reason": base_reason,
        }
        ans = self.brain.advise_plan(facts)
        if not ans.ok:
            self._llm(ans)
            return None
        verdict = check_proposal(self.field, self.sc, ans.data, self.rules)
        self._llm(
            ans,
            accepted=verdict.ok,
            reason=(
                f"{verdict.reason}. Модель объясняет так: {ans.text}"
                if verdict.ok
                else f"{verdict.reason}. Работаем по детерминированному плану"
            ),
        )
        return verdict if verdict.ok else None

    def explain(self, topic: str, facts: dict) -> str:
        """Объяснение решения по-русски для лога. Пусто — значит модель промолчала."""
        if not self.brain.wants("explain"):
            return ""
        ans = self.brain.explain(topic, facts)
        self._llm(ans)
        return ans.text if ans.ok else ""

    def _look_with_vlm(self, what: str):
        """Показать модели лучший кадр разведки. None — показывать нечего или нечем."""
        if not self.brain.wants("see") or not self.fire_shot:
            return None
        try:
            with open(self.fire_shot, "rb") as fh:
                frame = fh.read()
        except OSError as exc:
            self.log.ev("ERROR", error="OSError", reason=f"кадр {self.fire_shot} не прочитать: {exc}")
            return None
        return (
            self.brain.see_person(frame, self.sc.fire_cell)
            if what == "person"
            else self.brain.see_fire(frame)
        )

    def confirm_fire(self, scene) -> None:
        """Спросить VLM, виден ли очаг, когда зрение не уверено.

        Ответ НЕ переопределяет клетку: её считает vision.py по геометрии кадра, а
        модель геометрию не знает. Это второе мнение в лог, а не источник истины.
        """
        if not self.brain.confirm_fire or not self.brain.wants("see"):
            return
        if scene.found and scene.votes > 1:
            return  # два и больше согласных кадров — спрашивать не о чем
        ans = self._look_with_vlm("fire")
        if ans is None:
            return
        agree = bool(ans.data.get("fire")) if ans.ok else None
        self._llm(
            ans,
            accepted=agree,
            reason=(
                f"второе мнение по кадру: очаг {'подтверждён' if agree else 'не подтверждён'} "
                f"(уверенность {ans.data.get('confidence')}). Клетку всё равно считает "
                f"зрение по геометрии кадра: {ans.data.get('note') or '—'}"
                if ans.ok
                else ans.error
            ),
        )

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

        # Без ровера миссия невыполнима: тратить время на планирование и
        # зарядку, чтобы упасть на первом же переезде, — худший способ узнать это.
        rover = next((e for e in report if e["role"] == "rover"), None)
        if rover and rover.get("error"):
            raise RobotError(f"ровер не на связи, попытка не начинается: {rover['error']}")

    def survey(self) -> None:
        """Откуда берётся картина поля: с кадров мониторов или из config.yaml."""
        if self.cfg.get("flags.use_drones", False) and self.fleet.monitors:
            self._survey_by_drones()
        else:
            self.log.ev(
                "SURVEY",
                source="config",
                scenario_source="config",
                fire=list(self.sc.fire_cell),
                fire_level=self.sc.fire_level,
                reason="дроны-мониторы выключены, сцена взята из config.yaml",
            )

    # --- разведка мониторами -------------------------------------------------

    def _survey_by_drones(self) -> None:
        """Два прохода: сначала кадр с площадки, потом, если надо, облёт.

        Порядок не случаен. Кадр с площадки бесплатен по времени — дрон и так
        взлетает. Облёт стоит минуты 15-минутной попытки, поэтому включается только
        когда с площадок очага не видно, и прекращается сразу, как только он найден.
        """
        seen: list[vision.Observation] = []
        self.unverified = []
        for name, drone in self.fleet.monitors.items():
            self._scan_drone(name, drone, seen, offsets=())
            if vision.merge(seen).found and self._stop_when_found():
                break
        scene = vision.merge(seen)

        if not scene.found and self.cfg.get("survey.second_pass", True):
            self.log.ev(
                "SURVEY",
                source="drones",
                shots=len(seen),
                stage="pass-2",
                reason=(
                    "с площадок очаг не виден: на рабочей высоте кадр уже́е угла поля. "
                    "Идём облётом точек обзора с возвратом на метку"
                ),
            )
            for name, drone in self.fleet.monitors.items():
                self._scan_drone(name, drone, seen, offsets=self._offsets(name))
                if vision.merge(seen).found and self._stop_when_found():
                    break
            scene = vision.merge(seen)

        self.fire_shot = self._best_shot(seen, scene)
        self._apply_scene(scene, len(seen))
        self.confirm_fire(scene)

    def _best_shot(self, seen: Sequence[vision.Observation], scene) -> str:
        """Кадр для VLM: тот, где очаг виден крупнее всего.

        Крупнее — значит снят ближе, и человека в окне на нём тоже видно лучше.
        Если очага не нашли вовсе, берётся последний снятый кадр: показать модели
        нечего более осмысленного, а второе мнение по нему всё равно полезно.
        """
        useful = [o for o in seen if o.shot]
        if not useful:
            return ""
        if scene.found:
            same = [o for o in useful if o.found and as_cell(o.fire_cell) == scene.fire_cell]
            if same:
                return max(same, key=lambda o: o.area).shot
        return useful[-1].shot

    def _stop_when_found(self) -> bool:
        return bool(self.cfg.get("survey.stop_when_found", True))

    def _scan_drone(self, name: str, drone, seen: list, offsets: Sequence) -> None:
        """Взлёт -> кадр с метки -> точки обзора с возвратом на метку -> посадка."""
        pad = as_cell(self.cfg.robots.monitors[name].pad)
        pad_xy = self.field.cell_to_m(pad)
        try:
            drone.takeoff(self.survey_alt)
            self._wait_state(drone, ("hover",), timeout=20.0)
            if not offsets:
                self._look_and_see(name, drone, pad_xy, seen, home=None)
            for point in offsets:
                self._look_and_see(name, drone, point, seen, home=pad_xy)
                if seen and seen[-1].found and self._stop_when_found():
                    break
        except RobotError as exc:
            self.log.ev(
                "ERROR",
                error="RobotError",
                drone=name,
                reason=f"монитор {name} сорвал разведку: {exc}",
            )
        finally:
            # Посадка обязательна, чем бы ни кончилась съёмка: сорвавшийся кадр
            # оставлял монитор висеть над полем до срабатывания сторожа борта.
            if self._park(drone, name) == "landed_unverified":
                self.unverified.append(name)

    def _look_and_see(self, name: str, drone, point, seen: list, home) -> None:
        """Слетать в точку обзора, снять кадр, разобрать его и вернуться на метку.

        Возврат на метку обязателен и делается ДО разбора кадра: висеть над полем,
        пока ноутбук считает картинку, незачем, а над меткой борт стоит устойчивее —
        там работает локализация по ArUco.
        """
        if home is not None:
            drone.look(point, self.survey_alt)
            self._wait_state(drone, ("hover",), timeout=25.0)
        frame = drone.shot()
        if home is not None:
            drone.look(home, self.survey_alt)
            self._wait_state(drone, ("hover",), timeout=25.0)
        seen.append(self._see(name, frame, point))

    def _see(self, name: str, frame: bytes, point) -> vision.Observation:
        """Разобрать один кадр и записать увиденное в лог — даже если не увидели ничего."""
        path = self.save_shot(name, frame)
        try:
            picture = vision.decode(frame)
            obs = vision.look(
                picture,
                self.field,
                self.pads,
                drone=name,
                pose=point,
                alt=self.survey_alt,
                **self.vision_settings,
            )
            if obs.found:
                self._save_marked(picture, obs, path)
        except vision.VisionError as exc:
            obs = vision.Observation(drone=name, note=str(exc))
        obs.shot = path
        self.log.ev(
            "SCAN",
            drone=name,
            xy=[round(float(point[0]), 2), round(float(point[1]), 2)],
            fire_cell=list(obs.fire_cell) if obs.fire_cell else None,
            anchor=obs.anchor,
            markers=obs.markers_seen,
            area=round(obs.area, 1),
            shot=path,
            reason=(
                f"очаг в клетке {list(obs.fire_cell)}, привязка кадра «{obs.anchor}»"
                if obs.found
                else f"очага на кадре нет: {obs.note or 'пятен нужного цвета не найдено'}"
            ),
        )
        return obs

    def _save_marked(self, picture, obs, path: str) -> None:
        """Кадр с разметкой рядом с исходным: доказательство для техзащиты."""
        try:
            vision.draw(picture, obs, self.field, self.pads, path[:-4] + "-mark.jpg")
        except Exception:  # noqa: BLE001 — разметка полезна, но не обязательна
            pass

    def _offsets(self, name: str) -> list[tuple[float, float]]:
        """Точки обзора вокруг площадки монитора, в метрах поля.

        В конфиге смещения записаны так, что ПЛЮС значит «в сторону центра поля».
        Знаки разворачиваются по тому, в каком углу стоит этот дрон, поэтому один и
        тот же список годится всем четырём.
        """
        pad = as_cell(self.cfg.robots.monitors[name].pad)
        px, py = self.field.cell_to_m(pad)
        sx = 1.0 if px <= self.field.x0 else -1.0
        sy = 1.0 if py <= self.field.y0 else -1.0
        half_x = self.field.cols * self.field.cell / 2.0 - self.field.cell / 4.0
        half_y = self.field.rows * self.field.cell / 2.0 - self.field.cell / 4.0
        points = []
        for offset in self.cfg.get("survey.offsets", []) or []:
            x = px + sx * float(offset[0])
            y = py + sy * float(offset[1])
            # Точка обзора не должна уводить дрон за поле: там ему делать нечего,
            # а полётная зона кончается.
            x = max(self.field.x0 - half_x, min(self.field.x0 + half_x, x))
            y = max(self.field.y0 - half_y, min(self.field.y0 + half_y, y))
            points.append((round(x, 3), round(y, 3)))
        return points

    def _apply_scene(self, scene: vision.Scene, shots: int) -> None:
        """Итог разведки. Не нашли — так и пишем, а не подставляем тихо конфиг."""
        if not scene.found:
            self.log.ev(
                "SURVEY",
                source="config",
                shots=shots,
                fire=list(self.sc.fire_cell),
                fire_level=self.sc.fire_level,
                landing_unverified=self.unverified,
                reason=(
                    f"кадров снято {shots}, очаг ни на одном не распознан — "
                    f"работаем по клетке из config.yaml {list(self.sc.fire_cell)}. "
                    "Проверьте пороги цвета: python3 -m city.vision <кадр> --debug"
                    + (
                        f"; посадку не подтвердили: {', '.join(self.unverified)}"
                        if self.unverified
                        else ""
                    )
                ),
            )
            return

        was = self.sc.fire_cell
        self.sc.fire_cell = scene.fire_cell
        # Человек по заданию — в окне ГОРЯЩЕГО здания, поэтому ВУП летит туда же.
        self.sc.person_cell = scene.fire_cell
        self.log.ev(
            "FIRE_SPOTTED",
            cell=list(scene.fire_cell),
            votes=scene.votes,
            total=scene.total,
            by_cell=scene.by_cell,
            drones=scene.drones,
            level=self.sc.fire_level,
            level_source="config",
            reason=(
                f"очаг найден по кадрам: {scene.votes} из {scene.total} за клетку "
                f"{list(scene.fire_cell)} (дроны: {', '.join(scene.drones)}). "
                "Уровень пожара картинкой не определяется — «огонёк» числа не несёт, "
                f"берём заданный организаторами: {self.sc.fire_level}"
            ),
        )
        self.log.ev(
            "SURVEY",
            source="drones",
            shots=shots,
            fire=list(scene.fire_cell),
            fire_level=self.sc.fire_level,
            landing_unverified=self.unverified,
            reason=(
                f"сцена построена по кадрам мониторов"
                + (
                    f"; в config.yaml стояла клетка {list(was)}, побеждает найденная"
                    if as_cell(was) != scene.fire_cell
                    else "; совпало с config.yaml"
                )
                + (
                    f"; посадку не подтвердили: {', '.join(self.unverified)}"
                    if self.unverified
                    else ""
                )
            ),
        )

    def _park(self, drone, name: str) -> str:
        """Посадить монитор и вернуть состояние, в котором он остался."""
        try:
            state = drone.status().get("state")
            if state in ON_GROUND:
                return state
            drone.land()
            self._wait_state(drone, ON_GROUND, timeout=25.0)
            return drone.status().get("state")
        except RobotError as exc:
            self.log.ev(
                "SAFETY",
                action="land",
                drone=name,
                reason=f"монитор {name} остался в воздухе: {exc}",
            )
            return "unknown"

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
        """Дождаться состояния борта. Команда принимается сразу, исполняется в фоне.

        Проверяется и признак busy: борт поднимает его в тот же миг, когда принимает
        команду, поэтому «состояние ещё прежнее» не будет принято за «уже долетел».
        """
        t0 = self.clock.now()
        while self.clock.now() - t0 < timeout:
            st = robot.status()
            if st.get("state") in states and not st.get("busy"):
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

    def execute(self, actions: Sequence[Any]) -> None:
        # Миссия сейчас одна, но список строится по самому плану: если завтра
        # добавится вторая, здесь ничего менять не придётся.
        order: list[str] = []
        for action in actions:
            if action.mission and action.mission not in order:
                order.append(action.mission)
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

    def _do_dwell(self, action) -> None:
        rover = self.fleet.rover
        if action.led:
            rover.led(action.led)
        measured, moved, in_zone, led_on = self._hold(rover, action.cell, action.seconds)
        counted = water_dwell_valid(
            measured, moved=moved, in_zone=in_zone, led_on=led_on, rules=self.rules
        )
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

    def _vup_person_search(self) -> None:
        """Поиск человека в окне горящего здания. Без аппарата — честный отказ."""
        if not self.fleet.vup:
            self.log.ev(
                "VUP_ABSENT",
                mission="fire",
                missing=["person_detection_in_window"],
                reason=(
                    "человека в окне искать нечем: ВУП отсутствует. Пробуем частичную "
                    "замену — разбор кадра дрона-монитора моделью VLM (PLAN.md, "
                    "«Чего у нас нет на руках»)"
                ),
            )
            self._person_by_monitor()
            return
        vup = self.fleet.vup
        vup.takeoff(VUP_ALT)
        self._wait_state(vup, ("hover",), timeout=20.0)
        vup.goto(self.sc.fire_cell, VUP_ALT)
        self._wait_state(vup, ("hover",), timeout=30.0)
        try:
            self.save_shot("vup", vup.shot())
        finally:
            self._park(vup, "vup")
        self.log.ev(
            "PERSON_FOUND",
            found=None,
            source="vup",
            cell=list(self.sc.fire_cell),
            reason=(
                "кадр окна снят, но детектора ещё нет (этапы 3 и 7): "
                "результат не выдумываем"
            ),
        )

    def _person_by_monitor(self) -> None:
        """Частичная замена ВУП: спросить VLM про человека на кадре монитора.

        Надёжность заведомо ниже, чем у ВУП: окно вертикальное, а монитор снимает
        сверху. Поэтому источник и модель пишутся в лог прямо — судья должен видеть,
        чем именно получена детекция, а не только её результат.
        """
        ans = self._look_with_vlm("person")
        if ans is None:
            return
        found = bool(ans.data.get("person")) if ans.ok else None
        self._llm(ans, accepted=found)
        self.log.ev(
            "PERSON_FOUND",
            found=found,
            source="monitor",
            model=ans.model,
            confidence=ans.data.get("confidence") if ans.ok else None,
            cell=list(self.sc.fire_cell),
            shot=self.fire_shot,
            reason=(
                (
                    f"на кадре монитора {'виден человек' if found else 'человека не видно'} "
                    f"(уверенность {ans.data.get('confidence')}): {ans.data.get('note') or '—'}. "
                    "Съёмка сверху, окно вертикальное — надёжность ниже, чем у ВУП"
                )
                if ans.ok
                else f"модель кадр не разобрала: {ans.error}. Результат не выдумываем"
            ),
        )
