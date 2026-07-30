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
import threading
import time
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
# Сколько ждать одновременную разведку всех мониторов, с. Внутри у каждого свои
# сроки (взлёт 20 с, посадка 25 с) — этот срок общий и нужен на случай, когда борт
# завис, не ответив ни отказом, ни успехом: попытка идёт дальше без него.
SCAN_TIMEOUT = 90.0
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
        self.max_fire_count = vision.max_count(cfg)
        self.survey_alt = float(cfg.get("survey.alt", MONITOR_ALT))
        # Взлетать всем мониторам разом или по очереди (этап 8). По очереди —
        # страховка на первый прогон на площадке, ключ --survey-serial.
        self.survey_serial = bool(cfg.get("survey.serial", False))
        # Мониторы, чья посадка не подтвердилась: попадают в лог разведки, чтобы
        # «сел» на пульте не расходилось с тем, что видно глазами над полем.
        self.unverified: list[str] = []
        # Мониторы, не ответившие на перекличке: их не зовут в разведку вовсе.
        self.offline: list[str] = []
        # Кто сорвал разведку и почему: причина попадает в отчёт о покрытии поля.
        self.problems: dict[str, str] = {}
        # Итог покрытия: какие четверти поля никто не снял (заполняется разведкой).
        self.coverage: dict[str, Any] = {}
        # Бортовые вердикты про огонь: имя монитора -> {verdict|error, obs}. Второй,
        # независимый от city/vision.py источник — но роскошь, а не звено управления:
        # каждый его отказ переносится молча, попытка идёт как без него.
        self.onboard: dict[str, dict[str, Any]] = {}
        self.ask_onboard = bool(cfg.get("flags.ask_onboard_fire", True))
        # Двойной предел на опрос бортов. Дело не только в 15-минутной попытке:
        # бортовой разбор — это OpenCV на OrangePi ОДНОВРЕМЕННО с удержанием метки
        # под камерой. Начнёт борт от этого терять метку — выключается флагом.
        self.onboard_budget = float(cfg.get("survey.onboard_budget", 10.0))
        self.onboard_spent = 0.0
        self._budget_said = False
        # Квадрат огня роверу. tell_fire_on выключает обмен целиком, _fire_sent
        # помнит отправленное (чтобы не повторяться и чтобы заметить, что ровер его
        # забыл), rover_knows_fire гаснет, если агент ровера про /fire не знает.
        self.tell_fire_on = bool(cfg.get("flags.tell_rover_fire", True))
        self._fire_sent: dict[str, Any] | None = None
        self.rover_knows_fire = True
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
                "ask_onboard_fire": self.ask_onboard,
                "tell_rover_fire": self.tell_fire_on,
            },
            layout=self._layout(),
            reason="начало зачётной попытки",
        )
        try:
            self.connect()
            self.survey()
            # Ровер узнаёт цель сразу после разведки, а не перед первым переездом:
            # если план дальше сорвётся (RouteBlocked, заряд), в логе всё равно
            # останется, что квадрат до него дошёл. Клетку подъезда пошлём отдельно —
            # её считает компиляция плана ниже.
            self.tell_rover_fire()
            # Сначала спрашиваем модель, потом объясняем план: обоснование обязано
            # называть ту клетку, на которую план и построен, иначе лог решений
            # расходится с делом.
            advice = self.advise_plan()
            spot = advice.spot if advice else None
            reasons = plan_reasons(self.field, self.sc, self.rules, spot=spot)
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
            # Теперь известна клетка подъезда — дополняем квадрат ею. Ровер по ней
            # пока не едет сам, но данные для будущей маршрутизации «башня <-> очаг»
            # лежат у него, а не только в плане диспетчера. Считается тем же
            # выражением, что в rules.fire_route: полагаться на «end совпадает с
            # подъездом» нельзя — это совпадение, а не контракт.
            self.tell_rover_fire(
                spot=spot or self.field.approach(self.sc.fire_cell, self.sc.tower)
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

    def _layout(self) -> dict[str, Any]:
        """Раскладка поля в самом журнале: по нему видно, на каком поле это снято.

        Дашборд (city/viz.py) предпочитает её текущему config.yaml, и это важнее
        удобства: раскладку на площадке правят каждый день, а вчерашний прогон надо
        показывать таким, каким он был.
        """
        return {
            "size": [self.field.cols, self.field.rows],
            "cell": self.field.cell,
            "buildings": [list(c) for c in sorted(self.field.buildings)],
            "tower": list(self.sc.tower),
            "charge": list(self.sc.charge),
            "rover_start": list(self.sc.rover_start),
            # Площадки: {id метки: клетка}. В JSON ключи станут строками — так и надо.
            "pads": {str(mid): list(cell) for mid, cell in sorted(self.pads.items())},
            # Мониторы попытки: {имя: клетка своей площадки}. Отдельно от pads, потому
            # что дроны на площадке могут быть не все (ключ --monitors).
            "monitors": {
                name: list(as_cell(self.cfg.robots.monitors[name].pad))
                for name in sorted(self.fleet.monitors)
            },
        }

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

        # Монитор, не вышедший на связь, попытку не отменяет: летим оставшимися, а
        # его четверть поля честно помечается «никто не смотрел» (этап 8). Звать его
        # в разведку незачем — это только потерянные секунды на таймаутах.
        self.offline = [
            entry["name"]
            for entry in report
            if entry.get("error") and entry["name"] in self.fleet.monitors
        ]

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
        когда с площадок разведка не удалась, и прекращается, как только удалась.

        «Удалась» — это не только «очаг найден». Кадр, на котором кучка огоньков
        упёрлась в край, показывает клетку, но занижает число жетонов, то есть
        степень пожара. Останавливаться на таком кадре значит недовезти воду,
        поэтому облёт продолжается, пока кучку не увидят целиком.
        """
        seen: list[vision.Observation] = []
        self.unverified = []
        self.problems = {}
        self._scan_pass(seen, use_offsets=False)
        scene = vision.merge(seen, self.max_fire_count)

        if not scene.sure and self.cfg.get("survey.second_pass", True):
            self.log.ev(
                "SURVEY",
                source="drones",
                shots=len(seen),
                stage="pass-2",
                reason=(
                    (
                        "с площадок очаг не виден: на рабочей высоте кадр уже́е угла поля. "
                        if not scene.found
                        else "очаг виден только краем кадра, по такому огоньки не сосчитать. "
                    )
                    + "Идём облётом точек обзора с возвратом на метку"
                ),
            )
            self._scan_pass(seen, use_offsets=True)
            scene = vision.merge(seen, self.max_fire_count)

        self.fire_shot = self._best_shot(seen, scene)
        self._log_coverage(seen)
        self._apply_scene(scene, len(seen))
        self.confirm_fire(scene)

    # --- кто летит: все разом или по очереди ---------------------------------

    def _scan_pass(self, seen: list, use_offsets: bool) -> None:
        """Один проход разведки по всем мониторам, что вышли на связь."""
        names = [name for name in self.fleet.monitors if name not in self.offline]
        if self._together(names):
            self._scan_together(names, seen, use_offsets)
            return
        for name in names:
            offsets = self._offsets(name) if use_offsets else ()
            error = self._scan_drone(
                name, self.fleet.monitors[name], seen, offsets, self.unverified
            )
            if error:
                self.problems[name] = error
            # По очереди есть смысл останавливаться досрочно: каждый следующий взлёт
            # стоит времени попытки. Одновременный взлёт этого выбора не оставляет —
            # там дроны уже в воздухе, и полное покрытие поля дороже.
            if self._enough(seen):
                break

    def _together(self, names: Sequence[str]) -> bool:
        """Можно ли поднять мониторы одновременно.

        Одновременный взлёт безопасен ровно потому, что монитор никуда не летит:
        каждый висит над своей меткой в своём углу поля, пересекающихся маршрутов
        нет. Появятся точки обзора (`survey.offsets`) — дроны снова поедут по полю,
        и тогда только по очереди.

        В моках (`transport: fake`) параллелить нечего и нельзя: аппараты живут в
        общей памяти диспетчера и на виртуальных часах, которые из двух потоков
        считать нельзя.
        """
        if self.survey_serial or len(names) < 2:
            return False
        if self.fleet.transport != "http":
            return False
        return not (self.cfg.get("survey.offsets", []) or [])

    def _scan_together(self, names: Sequence[str], seen: list, use_offsets: bool) -> None:
        """Все мониторы взлетают, снимают и садятся одновременно, каждый в своём потоке.

        Наблюдения собираются в отдельные списки и сводятся в порядке из конфига:
        иначе и лог, и голосование зависели бы от того, кто ответил первым, а
        воспроизводимость прогона дороже пары строк кода.
        """
        mine: dict[str, list] = {name: [] for name in names}
        landed: dict[str, list] = {name: [] for name in names}

        def scan_one(name: str) -> None:
            offsets = self._offsets(name) if use_offsets else ()
            error = self._scan_drone(
                name, self.fleet.monitors[name], mine[name], offsets, landed[name]
            )
            if error:
                self.problems[name] = error

        threads = [
            threading.Thread(target=scan_one, args=(name,), daemon=True, name=f"survey-{name}")
            for name in names
        ]
        for t in threads:
            t.start()
        # Срок общий на всех: взлетели вместе — значит и ждём их вместе, а не по
        # SCAN_TIMEOUT на каждого по очереди.
        deadline = time.monotonic() + SCAN_TIMEOUT
        for t in threads:
            t.join(max(0.0, deadline - time.monotonic()))
        for name, t in zip(names, threads):
            if t.is_alive():
                self.problems.setdefault(
                    name, f"не отчитался за {SCAN_TIMEOUT:g} с — разведку ждать перестали"
                )
                self.log.ev(
                    "ERROR",
                    error="Timeout",
                    drone=name,
                    reason=(
                        f"монитор {name} не закончил разведку за {SCAN_TIMEOUT:g} с. "
                        "Прогон идёт дальше, но этот дрон может остаться в воздухе — "
                        "смотрите глазами и при необходимости жмите KILL SWITCH"
                    ),
                )
            seen.extend(mine[name])
            self.unverified.extend(landed[name])

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

    def _enough(self, seen: list) -> bool:
        """Можно ли прекращать облёт: очаг найден и огоньки сосчитаны по целой кучке."""
        return self._stop_when_found() and vision.merge(seen, self.max_fire_count).sure

    def _scan_drone(
        self, name: str, drone, seen: list, offsets: Sequence, unverified: list[str]
    ) -> str:
        """Взлёт -> кадр с метки -> точки обзора с возвратом на метку -> посадка.

        Возвращает причину срыва по-русски или пустую строку. Причина нужна не для
        управления, а для отчёта: без неё «этот угол поля не снят» неотличимо от
        «на этом углу ничего не лежит».
        """
        pad = as_cell(self.cfg.robots.monitors[name].pad)
        pad_xy = self.field.cell_to_m(pad)
        error = ""
        try:
            drone.takeoff(self.survey_alt)
            # Ждать дольше самого взлёта: борт уходит вслепую только на первые 0,7 м,
            # а остаток добирает шагами по метке и говорит «висит» в конце набора.
            # Кадр до этого момента снят с промежуточной высоты — покрытие по нему
            # посчиталось бы мимо.
            self._wait_state(drone, ("hover",), timeout=45.0)
            if not offsets:
                self._look_and_see(name, drone, pad_xy, seen, home=None)
            for point in offsets:
                self._look_and_see(name, drone, point, seen, home=pad_xy)
                if self._enough(seen):
                    break
        except RobotError as exc:
            error = str(exc)
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
                unverified.append(name)
        return error

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
        # Вердикт борта спрашивается ЗДЕСЬ и только здесь. На GET /fire борт снимает
        # СВЕЖИЙ кадр, значит спрашивать можно, пока он ещё висит над меткой: после
        # посадки пришёл бы вердикт по полу, а принять такой за «огня нет» опаснее,
        # чем не спрашивать вовсе. Садится монитор в _scan_drone, в finally.
        asked = self._ask_onboard(name, drone)
        if home is not None:
            drone.look(home, self.survey_alt)
            self._wait_state(drone, ("hover",), timeout=25.0)
        obs = self._see(name, frame, point)
        seen.append(obs)
        if asked is not None:
            # Оба разбора ОДНОГО зависания кладутся рядом: сверять имеет смысл
            # только их, а не бортовой вердикт с чужим кадром.
            self.onboard[name] = {**asked, "obs": obs}

    def _ask_onboard(self, name: str, drone) -> dict[str, Any] | None:
        """Спросить борт, что он видит. None — не спрашивали вовсе.

        Отказ в любой форме (404 у старой прошивки, 503 без кадра, таймаут) — это
        ОТСУТСТВИЕ ВЕРДИКТА, а не отсутствие огня, и он всё равно возвращается: тогда
        про молчащий борт напишется FIRE_CHECK, и в логе будет видно, спрашивали или
        нет. Разведка от этого не зависит ни в одной ветке.
        """
        if not self.ask_onboard:
            return None
        if not hasattr(drone, "fire"):
            # Клиент борта, который про /fire не знает вовсе. Это то же самое
            # ОТСУТСТВИЕ ВЕРДИКТА, что и 404 от старой прошивки, и разведку оно
            # обрывать не вправе — иначе роскошь стала бы звеном управления.
            return None
        if self.onboard[name]["ok"] if name in self.onboard else False:
            # Второй проход разведки снимает кадр с той же площадки (survey.offsets
            # пуст намеренно), так что спрашивать борт заново незачем: вердикт был бы
            # тот же, а стоил бы ещё до 4 с из бюджета попытки. После ОТКАЗА
            # спрашиваем повторно — он мог быть случайным.
            return None
        if self.onboard_spent >= self.onboard_budget:
            if not self._budget_said:
                self._budget_said = True
                self.log.ev(
                    "SURVEY",
                    source="drones",
                    stage="onboard-budget",
                    spent=round(self.onboard_spent, 1),
                    reason=(
                        f"бюджет на бортовые вердикты исчерпан "
                        f"({self.onboard_budget:g} с) — остальные мониторы не "
                        "спрашиваем, разбор кадров у диспетчера свой"
                    ),
                )
            return None
        started = self.clock.now()
        try:
            verdict = drone.fire()
        except RobotError as exc:
            asked: dict[str, Any] = {"ok": False, "error": str(exc)}
        else:
            asked = {"ok": True, "verdict": verdict}
        self.onboard_spent += max(0.0, self.clock.now() - started)
        return asked

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
            cells=len(obs.seen_cells),
            area=round(obs.area, 1),
            fire_count=obs.fire_count,
            count_source=obs.count_source,
            clipped=obs.clipped,
            shot=path,
            reason=(
                f"очаг в клетке {list(obs.fire_cell)}: огоньков {obs.fire_count} "
                f"(счёт по «{obs.count_source}», кучка {obs.spread_m:.2f} м), "
                f"привязка кадра «{obs.anchor}»"
                + (f"; {obs.note}" if obs.note else "")
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

    def _check_onboard(self, scene: vision.Scene) -> dict[str, Any]:
        """Сверить свой разбор кадров с бортовыми вердиктами. Пишет FIRE_CHECK.

        Сверяется ОДНО И ТО ЖЕ зависание в двух разборах: диспетчер разбирает JPEG,
        снятый с /shot, борт — свой кадр, снятый мгновением позже. Ни один из них не
        «правильнее» по определению, но при расхождении побеждает диспетчер: у него
        голосование по нескольким кадрам, у борта один кадр.

        Расхождение здесь — не баг, а симптом разъехавшейся калибровки: у борта своя
        таблица меток площадок, у диспетчера aruco.pads из config.yaml, а
        vision.marker_edge_deg вообще гипотеза. В первый день на площадке это
        единственный дешёвый способ поймать зеркало по оси или чужой размер маркера.

        Возвращает то, чем борт может ЗАКРЫТЬ ДЫРКУ (клетку, если зрение не нашло
        ничего; число огоньков, если клетка есть, а счёт не вышел). Переопределять
        найденное борт не вправе.
        """
        by_cell: dict[Cell, int] = {}
        counts: dict[Cell, list[int]] = {}
        for name, entry in self.onboard.items():
            obs = entry.get("obs")
            found = bool(obs is not None and obs.found)
            my_cell = as_cell(obs.fire_cell) if found and obs.fire_cell else None
            my_count = obs.fire_count if found else None

            verdict = entry.get("verdict") or {}
            error = entry.get("error", "")
            dry = bool(verdict.get("dry"))
            on_cell = (
                as_cell(verdict["cell"])
                if verdict.get("found") and verdict.get("cell")
                else None
            )
            on_count = verdict.get("count") if verdict.get("found") else None

            if error:
                agree, why = None, f"борт не ответил про огонь: {error}"
            elif dry:
                # Заглушку нельзя выдавать за второй источник — то же правило, по
                # которому mock-модель принципиально не смотрит на кадры.
                agree, why = None, "на том конце заглушка (--dry) — второго источника в этом прогоне нет"
            elif on_cell is not None and my_cell is not None:
                agree = on_cell == my_cell
                why = (
                    f"два независимых разбора одного зависания дали клетку {list(on_cell)}"
                    f" (привязка борта «{verdict.get('anchor')}»"
                    + (f", метка {verdict['marker_id']}" if verdict.get("marker_id") else "")
                    + ")"
                    if agree
                    else (
                        f"РАСХОЖДЕНИЕ: борт видит очаг в {list(on_cell)}, диспетчер по "
                        f"тому же зависанию — в {list(my_cell)}. Побеждает диспетчер "
                        "(у него голосование по кадрам). Проверьте калибровку: размер "
                        "маркера, номера площадок, vision.marker_edge_deg; смотрите "
                        "размеченный кадр *-mark.jpg"
                    )
                )
            elif on_cell is not None:
                agree = None
                why = (
                    f"борт назвал очаг в {list(on_cell)}, а диспетчер на этом кадре "
                    "ничего не нашёл — вердикт борта пойдёт закрывать дырку, если "
                    "очага не найдётся и на остальных кадрах"
                )
            elif my_cell is not None:
                agree = False
                why = (
                    f"диспетчер видит очаг в {list(my_cell)}, а борт на своём кадре "
                    "очага не назвал — это расхождение разборов, а не разных углов"
                )
            else:
                agree, why = None, "ни борт, ни диспетчер очага на этом кадре не нашли"

            self.log.ev(
                "FIRE_CHECK",
                drone=name,
                onboard_cell=list(on_cell) if on_cell else None,
                onboard_count=on_count,
                onboard_count_source=verdict.get("count_source"),
                onboard_anchor=verdict.get("anchor"),
                onboard_marker=verdict.get("marker_id"),
                onboard=("dry" if dry else ("mock" if verdict.get("source") == "mock" else "")),
                my_cell=list(my_cell) if my_cell else None,
                my_count=my_count,
                scene_cell=list(scene.fire_cell) if scene.found else None,
                agree=agree,
                delta_cells=(
                    abs(on_cell[0] - my_cell[0]) + abs(on_cell[1] - my_cell[1])
                    if on_cell is not None and my_cell is not None
                    else None
                ),
                error=error or None,
                reason=why,
            )
            # В голосование идут только настоящие вердикты: заглушка и отказ не в счёт.
            if on_cell is not None and not dry and not error:
                by_cell[on_cell] = by_cell.get(on_cell, 0) + 1
                if on_count and not verdict.get("clipped"):
                    # Кучка, упёршаяся в край кадра, занижает число жетонов — по
                    # такому вердикту степень пожара считать нельзя.
                    counts.setdefault(on_cell, []).append(int(on_count))

        fill: dict[str, Any] = {}
        if not scene.found and by_cell:
            fill["cell"] = max(by_cell.items(), key=lambda kv: (kv[1], kv[0]))[0]
        target = scene.fire_cell if scene.found else fill.get("cell")
        if scene.level is None and target is not None and counts.get(as_cell(target)):
            # Самое частое, при равенстве большее: недовезти воду хуже, чем привезти
            # лишний раз (та же логика, что в vision.merge).
            seen_counts = counts[as_cell(target)]
            fill["level"] = min(
                max(seen_counts, key=lambda c: (seen_counts.count(c), c)),
                self.max_fire_count,
            )
        return fill

    # --- покрытие поля -------------------------------------------------------

    def _log_coverage(self, seen: Sequence[vision.Observation]) -> None:
        """Что из поля кто снял и чего никто не видел.

        Главный вывод этапа 8. Один монитор с 2 м видит около четверти поля, поэтому
        «очага не нашли» без этой сводки читается как «пожара нет», хотя на деле в
        тот угол никто не смотрел. Отказ борта отсюда виден клетками поля, а не
        только строкой об ошибке.
        """
        shots: dict[str, list] = {name: [] for name in self.fleet.monitors}
        for obs in seen:
            shots.setdefault(obs.drone, []).append(obs)

        drones: dict[str, Any] = {}
        covered: set = set()
        blind_names: list[str] = []
        seen_names: list[str] = []
        for name in self.fleet.monitors:
            pad = as_cell(self.cfg.robots.monitors[name].pad)
            quad = self.field.quadrant(pad)
            quarter = self.field.quadrant_cells(quad)
            mine: set = set()
            for obs in shots.get(name, []):
                mine.update(as_cell(c) for c in obs.seen_cells)
            covered |= mine
            why = self._blind_reason(name, shots.get(name, []), mine)
            (seen_names if not why else blind_names).append(name)
            entry = {
                "quarter": self.field.quadrant_name(quad),
                "pad": list(pad),
                "state": "blind" if why else "seen",
                "shots": len(shots.get(name, [])),
                "cells": len(mine),
                "own_quarter": len(mine & set(quarter)),
                "of": len(quarter),
                "why": why,
            }
            # Борт мог сорвать один проход и отработать другой: четверть при этом снята,
            # но сам отказ прятать нельзя — на площадке это повод посмотреть на дрон.
            if not why and name in self.problems:
                entry["trouble"] = self.problems[name]
            drones[name] = entry

        all_cells = set(self.field.cells())
        blind_cells = sorted(all_cells - covered)
        self.coverage = {
            "seen": seen_names,
            "blind": blind_names,
            "blind_cells": [list(c) for c in blind_cells],
            "drones": drones,
        }
        gaps = "; ".join(
            f"четверть {name} ({drones[name]['quarter']}) не снята: {drones[name]['why']}"
            for name in blind_names
        )
        self.log.ev(
            "COVERAGE",
            seen=seen_names,
            blind=blind_names,
            cells_seen=len(covered),
            cells_total=len(all_cells),
            blind_cells=self.coverage["blind_cells"],
            drones=drones,
            reason=(
                f"поле снято {len(covered)} клетками из {len(all_cells)}"
                + (f". {gaps}" if gaps else "; все четверти поля наблюдались")
            ),
        )

    def _blind_reason(self, name: str, shots: Sequence[vision.Observation], cells: set) -> str:
        """Почему монитор ничего не показал. Пустая строка — показал.

        Снятые клетки решают всё: борт, сорвавший один проход и отработавший другой,
        свою четверть видел, и записывать её в пробелы нельзя.
        """
        if cells:
            return ""
        if name in self.offline:
            return "борт не вышел на связь на перекличке"
        if name in self.problems:
            return self.problems[name]
        if not shots:
            return "кадров с этого борта не пришло"
        return "кадры сняты, но привязать их к полю не удалось: " + (
            shots[-1].note or "меток в кадре нет и точка съёмки неизвестна"
        )

    def _blind_note(self) -> str:
        """Одна фраза про пробелы разведки — для причин SURVEY и FIRE_SPOTTED."""
        blind = self.coverage.get("blind") or []
        if not blind:
            return ""
        drones = self.coverage.get("drones", {})
        corners = ", ".join(f"{name} ({drones.get(name, {}).get('quarter', '?')})" for name in blind)
        return f"четверти поля, которые никто не снял: {corners}"

    def _apply_scene(self, scene: vision.Scene, shots: int) -> None:
        """Итог разведки. Не нашли — так и пишем, а не подставляем тихо конфиг."""
        # Сверка с бортами идёт ДО записи итога: борт вправе закрыть дырку, а лог
        # обязан назвать ту самую клетку, на которой потом построится план. Иначе
        # FIRE_SPOTTED скажет одно, а ровер поедет к другому.
        fill = self._check_onboard(scene) if self.onboard else {}
        if not scene.found and not fill.get("cell"):
            blind_cells = {as_cell(c) for c in self.coverage.get("blind_cells", [])}
            self.log.ev(
                "SURVEY",
                source="config",
                shots=shots,
                fire=list(self.sc.fire_cell),
                fire_level=self.sc.fire_level,
                landing_unverified=self.unverified,
                blind=self.coverage.get("blind", []),
                blind_cells=self.coverage.get("blind_cells", []),
                reason=(
                    f"кадров снято {shots}, очаг ни на одном не распознан"
                    + (", бортовые вердикты тоже пусты" if self.onboard else "")
                    + f" — работаем по клетке из config.yaml {list(self.sc.fire_cell)}. "
                    "Проверьте пороги цвета: python3 -m city.vision <кадр> --debug"
                    + (f"; {self._blind_note()}" if self._blind_note() else "")
                    + (
                        f"; клетку {list(self.sc.fire_cell)} из config.yaml никто не снимал — "
                        "проверить её нечем, работаем по ней вслепую"
                        if as_cell(self.sc.fire_cell) in blind_cells
                        else ""
                    )
                    + (
                        f"; посадку не подтвердили: {', '.join(self.unverified)}"
                        if self.unverified
                        else ""
                    )
                ),
            )
            return

        was, was_level = self.sc.fire_cell, self.sc.fire_level
        if scene.found:
            cell, cell_source = scene.fire_cell, "frames"
        else:
            # Зрение диспетчера не нашло ничего, а борт назвал клетку: он закрывает
            # дырку, а не спорит с работающим зрением. Строго лучше прежнего
            # поведения, когда в этом случае тихо брался config.yaml.
            cell, cell_source = as_cell(fill["cell"]), "onboard"
        self.sc.fire_cell = cell
        # Человек по заданию — в окне ГОРЯЩЕГО здания, поэтому ВУП летит туда же.
        self.sc.person_cell = cell
        # Степень пожара = сколько огоньков лежит рядом, и это видно на кадре.
        # Посчитанное побеждает записанное в настройках — как и клетка выше.
        if scene.level is not None:
            self.sc.fire_level = scene.level
            level_source = "frames"
            how = (
                f"огоньков насчитано {scene.level}, значит столько же поездок за водой"
                + (f" (по кадрам: {scene.level_votes})" if len(scene.level_votes) > 1 else "")
                + (f"; {scene.count_note}" if scene.count_note else "")
            )
        elif fill.get("level"):
            self.sc.fire_level = int(fill["level"])
            level_source = "onboard"
            how = (
                f"диспетчер огоньки не сосчитал"
                + (f" ({scene.count_note})" if scene.count_note else "")
                + f", счёт взят с борта: {self.sc.fire_level}"
            )
        else:
            level_source = "config"
            how = (
                "число огоньков по кадрам не получено"
                + (f": {scene.count_note}" if scene.count_note else "")
                + f" — уровень берём заданный организаторами: {self.sc.fire_level}"
            )
        self.log.ev(
            "FIRE_SPOTTED",
            cell=list(cell),
            votes=scene.votes,
            total=scene.total,
            by_cell=scene.by_cell,
            drones=scene.drones,
            level=self.sc.fire_level,
            level_source=level_source,
            cell_source=cell_source,
            fire_count=scene.level,
            level_votes=scene.level_votes,
            was_level=was_level,
            reason=(
                (
                    f"очаг найден по кадрам: {scene.votes} из {scene.total} за клетку "
                    f"{list(cell)} (дроны: {', '.join(scene.drones)}). "
                    if cell_source == "frames"
                    else f"очаг на кадрах диспетчера не распознан, клетку {list(cell)} "
                    "назвал борт своим разбором. "
                )
                + how
            ),
        )
        self.log.ev(
            "SURVEY",
            source="drones",
            shots=shots,
            fire=list(cell),
            fire_level=self.sc.fire_level,
            landing_unverified=self.unverified,
            blind=self.coverage.get("blind", []),
            level_source=level_source,
            cell_source=cell_source,
            reason=(
                f"сцена построена по кадрам мониторов"
                + ("" if cell_source == "frames" else " и бортовому вердикту")
                + (
                    f"; в config.yaml стояла клетка {list(was)}, побеждает найденная"
                    if as_cell(was) != cell
                    else "; совпало с config.yaml"
                )
                + (
                    f"; уровень в config.yaml был {was_level}, стал {self.sc.fire_level}"
                    if level_source != "config" and was_level != self.sc.fire_level
                    else ""
                )
                + (f"; {self._blind_note()}" if self._blind_note() else "")
                + (
                    f"; посадку не подтвердили: {', '.join(self.unverified)}"
                    if self.unverified
                    else ""
                )
            ),
        )

    # --- квадрат огня роверу -------------------------------------------------

    def _fire_payload(self, spot: Cell | None = None) -> dict[str, Any]:
        """Что ровер должен знать про пожар. Клетки, а не метры: метры у него свои."""
        payload: dict[str, Any] = {
            "cell": list(self.sc.fire_cell),
            "level": self.sc.fire_level,
            "tower": list(self.sc.tower),
            "charge": list(self.sc.charge),
            "at": round(self.clock.now(), 1),
        }
        if spot is not None:
            # Клетка подъезда: в саму горящую клетку ровер по регламенту не въезжает.
            payload["approach"] = list(as_cell(spot))
        return payload

    def tell_rover_fire(self, spot: Cell | None = None, clear: bool = False,
                        again: bool = False) -> None:
        """Сказать роверу, где горит. Информирование, а не команда движения.

        Отказ здесь НИКОГДА не срывает попытку: квадрат — это знание, а тушение
        держится на плане диспетчера. Агент ровера запускают руками с ноутбука, и на
        площадке он легко окажется версии, ничего про /fire не знающей: она ответит
        404, и тогда квадрат доедет резервным каналом — полями в теле /drive
        (см. _do_drive). Долбить отказавший путь незачем, поэтому rover_knows_fire
        гасится после первого 404.
        """
        rover = getattr(self.fleet, "rover", None)
        if not self.tell_fire_on or rover is None or not self.rover_knows_fire:
            return
        payload = {"clear": True} if clear else self._fire_payload(spot)
        if not clear and not again and self._same_fire(payload):
            return  # то же самое уже отправлено — молчим, а не повторяем
        try:
            rover.tell_fire(payload)
        except RobotError as exc:
            self.rover_knows_fire = False
            self.log.ev(
                "FIRE_TARGET",
                clear=clear,
                cell=payload.get("cell"),
                level=payload.get("level"),
                ok=False,
                error=str(exc),
                reason=(
                    f"квадрат огня роверу не доставлен основным каналом: {exc}. "
                    "Дальше он поедет полями fire/fire_level в теле /drive — их "
                    "агент любой версии проглатывает молча"
                ),
            )
            return
        self._fire_sent = None if clear else payload
        self.log.ev(
            "FIRE_TARGET",
            clear=clear,
            cell=payload.get("cell"),
            level=payload.get("level"),
            approach=payload.get("approach"),
            tower=payload.get("tower"),
            ok=True,
            via="fire",
            again=again or None,
            reason=(
                "пожар потушен — снимаем квадрат, чтобы статус ровера не утверждал "
                "обратное"
                if clear
                else (
                    ("повторная отправка: " if again else "")
                    + f"ровер знает, что горит в клетке {payload['cell']}, "
                    f"поездок за водой {payload['level']}, башня {payload['tower']}"
                    + (
                        f", подъезд {payload['approach']}"
                        if payload.get("approach")
                        else " (клетку подъезда посчитаем при компиляции плана)"
                    )
                )
            ),
        )

    def _same_fire(self, payload: dict[str, Any]) -> bool:
        """Тот же квадрат, что уже отправлен? Время в сравнение не входит."""
        if self._fire_sent is None:
            return False
        skip = ("at",)
        now = {k: v for k, v in payload.items() if k not in skip}
        was = {k: v for k, v in self._fire_sent.items() if k not in skip}
        return now == was

    def _heal_fire(self, st: dict[str, Any]) -> None:
        """Ровер забыл квадрат — отправить снова.

        Самый вероятный сбой площадки: агент ровера живёт на ноутбуке, и его
        перезапускают руками — после этого он не помнит ничего. Диспетчер и так
        опрашивает статус перед каждым переездом, так что проверка бесплатна. Без
        неё ровер молча забыл бы цель, и заметили бы только при разборе логов.
        """
        if self._fire_sent is None or st.get("fire"):
            return
        self.tell_rover_fire(
            spot=as_cell(self._fire_sent["approach"]) if self._fire_sent.get("approach") else None,
            again=True,
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
            st = rover.status()
            prev = as_cell(st["cell"])
            self._heal_fire(st)
            if not self.energy.can_move():
                raise EnergyError(
                    f"игровой заряд кончился на пути в {list(action.cell)}, "
                    "движение ровера заблокировано"
                )
            # Квадрат огня едет резервным каналом с каждой командой переезда: агент
            # любой версии лишние поля тела молча игнорирует, поэтому отказать этот
            # путь не может. Основной канал — POST /fire, см. tell_rover_fire.
            # Флаг tell_rover_fire гасит ОБА канала: выключают его тогда, когда на
            # площадке ровер, которому про пожар знать не надо вовсе.
            if self.tell_fire_on:
                rover.drive(nxt, fire=self.sc.fire_cell, fire_level=self.sc.fire_level)
            else:
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
            # Снимаем квадрат: иначе /status ровера до конца попытки утверждает, что
            # пожар ещё горит, — а по нему судят и дашборд, и будущая маршрутизация.
            self.tell_rover_fire(clear=True)
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
        # Столько же, сколько монитору: если ВУП поднят нашим бортовым агентом, взлёт
        # у него такой же двухступенчатый — вслепую, потом набор по метке.
        self._wait_state(vup, ("hover",), timeout=45.0)
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
