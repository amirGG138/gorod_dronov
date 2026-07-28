"""Аварийные пути: остановка флота и брошенные в воздухе мониторы.

Смысл проверок один: авария не должна выглядеть в логе так же, как успех. Молча
проглоченный отказ на «стоп» — это аппарат, который продолжает ехать, пока все
считают, что он остановлен.
"""

import io
import json
import tempfile
import time
import unittest
from contextlib import redirect_stderr

from city import config as config_mod
from city.clock import SimClock
from city.dispatcher import Dispatcher
from city.field import Field
from city.log import Log
from city.robots import fleet as fleet_mod
from city.robots.base import RobotError
from city.robots.fleet import Fleet, build_fleet


class Deaf:
    """Аппарат, не принимающий «стоп»: ровно то, ради чего есть KILL SWITCH."""

    role = "rover"
    name = "rover"

    def stop(self):
        raise RobotError("нет связи с ровером")


class Slow:
    """Аппарат, который на «стоп» не отвечает вовсе — команда уходит в никуда."""

    role = "drone"
    name = "m1"

    def stop(self):
        time.sleep(30.0)


class Good:
    role = "drone"
    name = "m2"

    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True
        return {"accepted": True}


class TestStopAll(unittest.TestCase):
    def test_failure_is_reported_not_swallowed(self):
        good = Good()
        report = Fleet(rover=Deaf(), monitors={"m2": good}).stop_all()
        by_name = {e["name"]: e for e in report}
        self.assertFalse(by_name["rover"]["stopped"])
        self.assertIn("нет связи", by_name["rover"]["error"])
        self.assertTrue(by_name["m2"]["stopped"])
        self.assertNotIn("error", by_name["m2"])

    def test_one_failure_does_not_block_the_others(self):
        good = Good()
        Fleet(rover=Deaf(), monitors={"m2": good}).stop_all()
        self.assertTrue(good.stopped, "отказ ровера отменил остановку дрона")

    def test_silent_robot_counts_as_not_stopped(self):
        was = fleet_mod.STOP_TIMEOUT
        fleet_mod.STOP_TIMEOUT = 0.3  # ждать в тесте настоящие 8 с незачем
        try:
            good = Good()
            report = Fleet(vup=Slow(), monitors={"m2": good}).stop_all()
        finally:
            fleet_mod.STOP_TIMEOUT = was
        by_name = {e["name"]: e for e in report}
        self.assertFalse(by_name["m1"]["stopped"])
        self.assertIn("не ответил", by_name["m1"]["error"])
        self.assertTrue(by_name["m2"]["stopped"], "молчащий аппарат задержал остальных")


def run_dispatcher(cls, cfg=None, prepare=None):
    cfg = cfg or config_mod.load()
    clock = SimClock()
    with tempfile.TemporaryDirectory() as tmp:
        log = Log(clock, run_dir=tmp, echo=False)
        fleet = build_fleet(cfg, clock)
        if prepare:
            prepare(fleet)
        err = io.StringIO()
        with redirect_stderr(err):
            code = cls(cfg, Field.from_config(cfg), log, clock, fleet).run()
        log.close()
        with open(log.path, encoding="utf-8") as fh:
            events = [json.loads(line) for line in fh]
    return code, events, err.getvalue(), fleet


class Broken(Dispatcher):
    """Диспетчер, у которого отказал ровер на самом полезном месте."""

    def precharge(self, budget, reason):
        raise RobotError("ровер перестал отвечать на середине зарядки")


class TestEmergencyStopIsLogged(unittest.TestCase):
    def setUp(self):
        def break_rover_stop(fleet):
            fleet.rover.stop = Deaf().stop

        self.code, self.events, self.stderr, _ = run_dispatcher(Broken, prepare=break_rover_stop)

    def test_run_fails(self):
        self.assertEqual(self.code, 1)

    def test_safety_event_names_who_was_not_stopped(self):
        safety = [e for e in self.events if e["type"] == "SAFETY" and e.get("action") == "stop_all"]
        self.assertEqual(len(safety), 1)
        self.assertEqual(safety[0]["failed"], ["rover"])
        self.assertIn("rover", safety[0]["reason"])

    def test_operator_sees_it_even_with_quiet_logs(self):
        self.assertIn("KILL SWITCH", self.stderr)


class TestMonitorsAreNeverLeftFlying(unittest.TestCase):
    """Сорвавшийся кадр не повод бросить дрон висеть над полем."""

    def test_failed_shot_still_lands_the_drone(self):
        cfg = config_mod.load()
        cfg.override("flags.use_drones", True)

        def break_shots(fleet):
            for drone in fleet.monitors.values():
                drone.shot = _no_frame

        code, events, _, fleet = run_dispatcher(Dispatcher, cfg=cfg, prepare=break_shots)
        self.assertEqual(code, 0, "миссия не должна срываться из-за кадра")
        self.assertTrue([e for e in events if e["type"] == "ERROR"], "отказ камеры не записан")
        for name, drone in fleet.monitors.items():
            self.assertEqual(drone.state, "landed", f"{name} остался в воздухе")

    def test_survey_names_the_source_of_the_level(self):
        """Уровень пожара измерен по кадрам — и в логе это сказано прямо.

        Здесь охраняется честность источника, а не конкретное число. Уровень равен
        числу огоньков на поле, значит он приходит с картинки (level_source=frames);
        если бы он был взят из config.yaml, судья обязан увидеть это в логе, иначе
        выдуманное число рейсов за водой ничем не отличалось бы от измеренного.
        """
        cfg = config_mod.load()
        cfg.override("flags.use_drones", True)
        _, events, _, _ = run_dispatcher(Dispatcher, cfg=cfg)
        survey = [e for e in events if e["type"] == "SURVEY"][-1]
        self.assertGreaterEqual(survey["shots"], 4)
        self.assertEqual(survey["landing_unverified"], [])
        spotted = next(e for e in events if e["type"] == "FIRE_SPOTTED")
        self.assertEqual(spotted["level_source"], "frames")
        self.assertEqual(spotted["level"], spotted["fire_count"])
        self.assertEqual(spotted["level"], cfg.get("scenario.fire.level"))

    def test_the_level_is_not_invented_when_the_fire_is_not_found(self):
        """Разведка ничего не нашла — уровень честно берётся из настроек."""
        cfg = config_mod.load()
        cfg.override("flags.use_drones", True)
        cfg.override("sim.fire_cell", "нет")  # поле без очага
        _, events, _, _ = run_dispatcher(Dispatcher, cfg=cfg)
        survey = [e for e in events if e["type"] == "SURVEY"][-1]
        self.assertEqual(survey["source"], "config")
        self.assertEqual(survey["fire_level"], cfg.get("scenario.fire.level"))
        self.assertFalse([e for e in events if e["type"] == "FIRE_SPOTTED"])


def _no_frame():
    raise RobotError("камера не отдала кадр")


if __name__ == "__main__":
    unittest.main()
