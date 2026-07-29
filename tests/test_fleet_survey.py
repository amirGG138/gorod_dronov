"""Четыре монитора: покрытие поля, отказ борта и одновременный взлёт (этап 8).

Главное, что здесь охраняется, — честность пробела. Один дрон с рабочей высоты
видит около четверти поля, поэтому «очага не нашли» без сводки покрытия читается
как «пожара нет», хотя в тот угол никто не смотрел. Отказ борта обязан быть виден
клетками поля, а не только строкой об ошибке.
"""

import io
import json
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr

from city import config as config_mod
from city.clock import RealClock, SimClock
from city.dispatcher import Dispatcher
from city.field import Field
from city.log import Log
from city.robots.base import RobotError
from city.robots.fleet import Fleet, build_fleet


def with_drones():
    cfg = config_mod.load()
    cfg.override("flags.use_drones", True)
    return cfg


def run_dispatcher(cfg, prepare=None):
    """Прогон попытки на моках в памяти. Возвращает код возврата и события лога."""
    clock = SimClock()
    with tempfile.TemporaryDirectory() as tmp:
        log = Log(clock, run_dir=tmp, echo=False)
        fleet = build_fleet(cfg, clock)
        if prepare:
            prepare(fleet)
        err = io.StringIO()
        with redirect_stderr(err):
            code = Dispatcher(cfg, Field.from_config(cfg), log, clock, fleet).run()
        log.close()
        with open(log.path, encoding="utf-8") as fh:
            events = [json.loads(line) for line in fh]
    return code, events, fleet


def coverage_of(events):
    return next(e for e in events if e["type"] == "COVERAGE")


class TestWholeFieldIsCovered(unittest.TestCase):
    """Четыре монитора со своих площадок покрывают поле целиком."""

    def setUp(self):
        _, self.events, _ = run_dispatcher(with_drones())
        self.cov = coverage_of(self.events)

    def test_every_quarter_was_looked_at(self):
        self.assertEqual(self.cov["blind"], [])
        self.assertEqual(sorted(self.cov["seen"]), ["m1", "m2", "m3", "m4"])

    def test_no_cell_of_the_field_is_left_unseen(self):
        self.assertEqual(self.cov["cells_seen"], self.cov["cells_total"])
        self.assertEqual(self.cov["blind_cells"], [])

    def test_every_drone_covers_its_own_quarter(self):
        for name, entry in self.cov["drones"].items():
            self.assertEqual(entry["own_quarter"], entry["of"], f"{name} не закрыл свою четверть")
            self.assertEqual(entry["state"], "seen")
            self.assertEqual(entry["why"], "")

    def test_quarters_are_named_in_russian(self):
        quarters = {e["quarter"] for e in self.cov["drones"].values()}
        self.assertEqual(len(quarters), 4, "четыре дрона обязаны стоять в разных четвертях")
        self.assertIn("ближняя левая", quarters)


class TestBrokenMonitorDoesNotStopTheRun(unittest.TestCase):
    """Отказ одного борта: попытка идёт дальше, а его четверть помечается пробелом."""

    def setUp(self):
        cfg = with_drones()

        def break_m2(fleet):
            def refuse(alt):
                raise RobotError("m2: взлёт не принят")

            fleet.monitors["m2"].takeoff = refuse

        self.code, self.events, self.fleet = run_dispatcher(cfg, prepare=break_m2)
        self.cov = coverage_of(self.events)

    def test_the_run_finishes(self):
        self.assertEqual(self.code, 0)

    def test_the_quarter_is_marked_blind_with_a_reason(self):
        self.assertEqual(self.cov["blind"], ["m2"])
        self.assertIn("взлёт не принят", self.cov["drones"]["m2"]["why"])
        self.assertEqual(self.cov["drones"]["m2"]["cells"], 0)

    def test_the_other_three_worked(self):
        self.assertEqual(sorted(self.cov["seen"]), ["m1", "m3", "m4"])
        self.assertEqual(self.cov["cells_seen"], self.cov["cells_total"] - 9)

    def test_the_survey_says_out_loud_which_corner_nobody_saw(self):
        """Очаг лежит как раз в четверти отказавшего борта — молчать об этом нельзя."""
        survey = [e for e in self.events if e["type"] == "SURVEY"][-1]
        self.assertEqual(survey["source"], "config")
        self.assertEqual(survey["blind"], ["m2"])
        self.assertIn("никто не снял", survey["reason"])
        self.assertIn("вслепую", survey["reason"])


class TestOfflineMonitorIsNotCalled(unittest.TestCase):
    """Не ответивший на перекличке борт в разведку не зовут: это потерянные секунды."""

    def setUp(self):
        def mute_m3(fleet):
            def silent():
                raise RobotError("m3: нет связи")

            fleet.monitors["m3"].status = silent

        self.code, self.events, self.fleet = run_dispatcher(with_drones(), prepare=mute_m3)
        self.cov = coverage_of(self.events)

    def test_the_run_finishes(self):
        self.assertEqual(self.code, 0)

    def test_the_silent_drone_never_took_off(self):
        self.assertEqual(self.fleet.monitors["m3"].alt, 0.0)
        self.assertEqual(self.fleet.monitors["m3"].state, "idle")

    def test_its_quarter_is_blind_because_of_the_roll_call(self):
        self.assertEqual(self.cov["blind"], ["m3"])
        self.assertIn("перекличк", self.cov["drones"]["m3"]["why"])


# --- одновременный взлёт ---------------------------------------------------------


class Timed:
    """Борт-заглушка по сети: засекает, когда он был в воздухе."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.role = "drone"
        self.state = "idle"
        self.up = 0.0
        self.down = 0.0

    def status(self):
        return {"state": self.state, "cell": [0, 0], "busy": False, "alt": 0.0}

    def takeoff(self, alt):
        time.sleep(0.3)
        self.state = "hover"
        self.up = time.monotonic()
        return {"accepted": True}

    def shot(self):
        time.sleep(0.1)
        return b"not-a-picture"  # разбор кадра тут не проверяется

    def land(self):
        time.sleep(0.3)
        self.state = "landed"
        self.down = time.monotonic()
        return {"accepted": True}

    def stop(self):
        return {"accepted": True}


def survey_with_stubs(serial: bool):
    """Одна разведка четырьмя заглушками по сети. Возвращает борта."""
    cfg = with_drones()
    if serial:
        cfg.override("survey.serial", True)
    drones = {name: Timed(name) for name in cfg.robots.monitors}
    fleet = Fleet(monitors=drones, transport="http")
    clock = RealClock()
    with tempfile.TemporaryDirectory() as tmp:
        log = Log(clock, run_dir=tmp, echo=False)
        Dispatcher(cfg, Field.from_config(cfg), log, clock, fleet).survey()
        log.close()
    return drones


class TestMonitorsFlyTogether(unittest.TestCase):
    def test_all_four_are_in_the_air_at_once(self):
        """Последний взлетел раньше, чем сел первый, — значит летели вместе."""
        drones = survey_with_stubs(serial=False)
        self.assertLess(
            max(d.up for d in drones.values()),
            min(d.down for d in drones.values()),
            "борта поднимались по очереди, а должны были разом",
        )

    def test_the_serial_key_brings_back_the_queue(self):
        drones = survey_with_stubs(serial=True)
        order = sorted(drones.values(), key=lambda d: d.up)
        for first, second in zip(order, order[1:]):
            self.assertLess(first.down, second.up, "с --survey-serial борта не должны пересекаться")


class TestLogSurvivesManyVoices(unittest.TestCase):
    """Четыре потока пишут в один лог: строки не должны перемешиваться посреди слова."""

    def test_every_line_stays_whole(self):
        clock = RealClock()
        with tempfile.TemporaryDirectory() as tmp:
            log = Log(clock, run_dir=tmp, echo=False)

            def spam(name):
                for i in range(50):
                    log.ev("SCAN", drone=name, xy=[0.0, 0.0], reason="строка " * 20)

            threads = [threading.Thread(target=spam, args=(f"m{i}",)) for i in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            log.close()
            with open(log.path, encoding="utf-8") as fh:
                lines = fh.read().splitlines()

        self.assertEqual(len(lines), 200)
        for line in lines:
            json.loads(line)  # каждая строка — целый JSON, иначе лог нечитаем


if __name__ == "__main__":
    unittest.main()
