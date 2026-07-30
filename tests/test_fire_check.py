"""Сверка двух разборов огня и передача квадрата роверу.

Почему отдельным файлом и без полного прогона: ветки «совпало» и «расхождение»
требуют, чтобы СВОЁ зрение диспетчера что-то нашло, а оно работает через OpenCV,
которого на машине разработчика может не быть вовсе (тогда `--sim --drones` всегда
даёт пустую сцену). Здесь Observation и Scene собираются руками, и обе ветки
проверяются на любой машине.

Главное правило, которое здесь закрепляется: при расхождении ПОБЕЖДАЕТ ДИСПЕТЧЕР.
У него голосование по нескольким кадрам, у борта один кадр. Борт вправе только
закрыть дырку — назвать клетку, если зрение не нашло ничего, или число огоньков,
если клетка есть, а счёт не вышел.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from city import config as config_mod
from city import vision
from city.clock import SimClock
from city.dispatcher import Dispatcher
from city.field import Field
from city.log import Log
from city.robots.base import RobotError
from city.robots.fake import FakeDrone, FakeRover
from city.robots.fleet import Fleet


def obs(drone, cell=None, count=0, clipped=False):
    """Что дал один кадр в разборе ДИСПЕТЧЕРА."""
    return vision.Observation(
        drone=drone, fire_cell=cell, fire_count=count, clipped=clipped,
        count_source="blobs" if count else "", anchor="markers",
    )


def verdict(cell=None, count=None, clipped=False, dry=False, source="mock"):
    """Что ответил БОРТ на GET /fire."""
    if dry:
        return {"found": False, "dry": True}
    if cell is None:
        return {"found": False, "source": source}
    out = {"found": True, "cell": list(cell), "anchor": "marker", "marker_id": 62,
           "source": source, "clipped": clipped}
    if count is not None:
        out["count"] = count
        out["count_source"] = "blobs"
    return out


class _Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = SimClock()
        self.cfg = config_mod.load()
        self.cfg.override("flags.use_drones", True)
        self.log = Log(self.clock, run_dir=self.dir.name, echo=False)
        self.field = Field.from_config(self.cfg)
        self.rover = FakeRover(self.clock, self.cfg.cells.rover_start, move_time=0.0)
        self.monitors = {
            name: FakeDrone(self.clock, (1, 1), name=name) for name in ("m1", "m2", "m3")
        }
        self.fleet = Fleet(rover=self.rover, monitors=self.monitors, transport="fake")
        self.d = Dispatcher(self.cfg, self.field, self.log, self.clock, self.fleet)

    def tearDown(self):
        self.log.close()
        self.dir.cleanup()

    def events(self, kind):
        self.log._fh.flush()
        with open(self.log.path, encoding="utf-8") as fh:
            return [json.loads(x) for x in fh if x.strip() and json.loads(x)["type"] == kind]

    def told(self, pairs):
        """Разложить пары (кадр диспетчера, вердикт борта) так, как это делает разведка."""
        for name, (o, v) in pairs.items():
            entry = {"ok": True, "verdict": v, "obs": o} if v is not None else {
                "ok": False, "error": "борт не ответил", "obs": o}
            self.d.onboard[name] = entry


class TestAgreement(_Base):
    def test_the_same_cell_is_agreement(self):
        self.told({"m1": (obs("m1", (4, 2), 2), verdict((4, 2), 2))})
        fill = self.d._check_onboard(vision.merge([obs("m1", (4, 2), 2)]))
        (check,) = self.events("FIRE_CHECK")
        self.assertTrue(check["agree"])
        self.assertEqual(check["delta_cells"], 0)
        self.assertEqual(check["onboard_cell"], [4, 2])
        self.assertEqual(check["my_cell"], [4, 2])
        self.assertEqual(fill, {})  # закрывать нечего

    def test_a_different_cell_is_a_discrepancy_and_the_dispatcher_wins(self):
        seen = [obs("m1", (4, 2), 2), obs("m2", (4, 2), 2)]
        self.told({"m1": (obs("m1", (4, 2), 2), verdict((1, 2), 1))})
        scene = vision.merge(seen)
        fill = self.d._check_onboard(scene)
        (check,) = self.events("FIRE_CHECK")
        self.assertFalse(check["agree"])
        self.assertEqual(check["delta_cells"], 3)
        self.assertIn("Побеждает диспетчер", check["reason"])
        self.assertIn("калибровку", check["reason"])  # подсказка для первого дня
        self.assertEqual(fill, {})  # клетку борт не переопределяет
        self.d._apply_scene(scene, shots=2)
        self.assertEqual(self.d.sc.fire_cell, (4, 2))  # осталась своя

    def test_the_board_silent_while_the_dispatcher_sees_is_also_a_discrepancy(self):
        self.told({"m1": (obs("m1", (4, 2), 2), verdict())})
        self.d._check_onboard(vision.merge([obs("m1", (4, 2), 2)]))
        (check,) = self.events("FIRE_CHECK")
        self.assertFalse(check["agree"])
        self.assertIn("расхождение разборов", check["reason"])

    def test_a_dry_board_is_never_a_second_source(self):
        """Заглушку нельзя выдавать за второй источник — как и mock-модель для кадров."""
        self.told({"m1": (obs("m1"), verdict(dry=True))})
        fill = self.d._check_onboard(vision.merge([obs("m1")]))
        (check,) = self.events("FIRE_CHECK")
        self.assertIsNone(check["agree"])
        self.assertEqual(check["onboard"], "dry")
        self.assertEqual(fill, {})  # дырку заглушка не закрывает

    def test_a_refusal_still_produces_a_record(self):
        """Иначе по логу не отличить «спрашивали и не ответил» от «не спрашивали»."""
        self.told({"m1": (obs("m1"), None)})
        self.d._check_onboard(vision.merge([obs("m1")]))
        (check,) = self.events("FIRE_CHECK")
        self.assertIsNone(check["agree"])
        self.assertIn("не ответил", check["reason"])


class TestFillingGaps(_Base):
    def test_the_board_names_the_cell_when_vision_found_nothing(self):
        """Строго лучше прежнего: раньше тут тихо брался config.yaml."""
        self.told({
            "m1": (obs("m1"), verdict((4, 2), 2)),
            "m2": (obs("m2"), verdict((4, 2), 2)),
            "m3": (obs("m3"), verdict((1, 4), 1)),
        })
        scene = vision.merge([obs("m1"), obs("m2"), obs("m3")])
        self.assertFalse(scene.found)
        fill = self.d._check_onboard(scene)
        self.assertEqual(fill["cell"], (4, 2))  # два голоса против одного
        self.assertEqual(fill["level"], 2)
        self.d._apply_scene(scene, shots=3)
        (spotted,) = self.events("FIRE_SPOTTED")
        self.assertEqual(spotted["cell"], [4, 2])
        self.assertEqual(spotted["cell_source"], "onboard")
        self.assertEqual(spotted["level_source"], "onboard")
        self.assertEqual(self.d.sc.fire_cell, (4, 2))
        self.assertEqual(self.d.sc.person_cell, (4, 2))  # ВУП летит туда же

    def test_the_board_counts_the_tokens_when_the_dispatcher_could_not(self):
        seen = [obs("m1", (4, 2), 0, clipped=True)]
        self.told({"m1": (seen[0], verdict((4, 2), 3))})
        scene = vision.merge(seen)
        self.assertTrue(scene.found)
        self.assertIsNone(scene.level)
        fill = self.d._check_onboard(scene)
        self.assertEqual(fill["level"], 3)
        self.d._apply_scene(scene, shots=1)
        (spotted,) = self.events("FIRE_SPOTTED")
        self.assertEqual(spotted["level"], 3)
        self.assertEqual(spotted["level_source"], "onboard")
        self.assertEqual(spotted["cell_source"], "frames")  # клетку нашли сами

    def test_a_clipped_verdict_never_sets_the_level(self):
        """Кучка у края кадра занижает число жетонов, а это недовезённая вода."""
        seen = [obs("m1", (4, 2), 0, clipped=True)]
        self.told({"m1": (seen[0], verdict((4, 2), 1, clipped=True))})
        fill = self.d._check_onboard(vision.merge(seen))
        self.assertNotIn("level", fill)

    def test_the_level_never_exceeds_the_ceiling(self):
        seen = [obs("m1", (4, 2), 0, clipped=True)]
        self.told({"m1": (seen[0], verdict((4, 2), 99))})
        fill = self.d._check_onboard(vision.merge(seen))
        self.assertEqual(fill["level"], self.d.max_fire_count)

    def test_nothing_anywhere_falls_back_to_the_config_out_loud(self):
        self.told({"m1": (obs("m1"), verdict())})
        self.d._apply_scene(vision.merge([obs("m1")]), shots=1)
        self.assertEqual(self.events("FIRE_SPOTTED"), [])
        (survey,) = self.events("SURVEY")
        self.assertEqual(survey["source"], "config")
        self.assertIn("бортовые вердикты тоже пусты", survey["reason"])


class TestAskingTheBoard(_Base):
    def test_the_flag_switches_the_question_off(self):
        self.d.ask_onboard = False
        self.assertIsNone(self.d._ask_onboard("m1", self.monitors["m1"]))

    def test_a_board_without_a_verdict_is_a_refusal_not_an_empty_answer(self):
        asked = self.d._ask_onboard("m1", self.monitors["m1"])
        self.assertFalse(asked["ok"])
        self.assertIn("не задан", asked["error"])

    def test_the_budget_stops_further_questions(self):
        self.d.onboard_spent = self.d.onboard_budget
        self.assertIsNone(self.d._ask_onboard("m1", self.monitors["m1"]))
        (note,) = [e for e in self.events("SURVEY") if e.get("stage") == "onboard-budget"]
        self.assertIn("бюджет", note["reason"])
        # Второй раз про бюджет не пишем — иначе на четыре борта четыре строки.
        self.d._ask_onboard("m2", self.monitors["m2"])
        self.assertEqual(len([e for e in self.events("SURVEY")
                              if e.get("stage") == "onboard-budget"]), 1)


class TestTellingTheRover(_Base):
    def test_the_square_reaches_the_rover_and_gets_logged(self):
        self.d.sc.fire_cell, self.d.sc.fire_level = (4, 2), 3
        self.d.tell_rover_fire()
        self.assertEqual(self.rover.fire["cell"], [4, 2])
        self.assertEqual(self.rover.fire["level"], 3)
        (target,) = self.events("FIRE_TARGET")
        self.assertTrue(target["ok"])
        self.assertEqual(target["via"], "fire")
        self.assertEqual(target["tower"], list(self.d.sc.tower))

    def test_the_same_square_is_not_sent_twice(self):
        self.d.sc.fire_cell = (4, 2)
        self.d.tell_rover_fire()
        self.d.tell_rover_fire()
        self.assertEqual(len(self.events("FIRE_TARGET")), 1)

    def test_the_approach_cell_is_an_update_worth_sending(self):
        self.d.sc.fire_cell = (4, 2)
        self.d.tell_rover_fire()
        self.d.tell_rover_fire(spot=(4, 3))
        self.assertEqual(len(self.events("FIRE_TARGET")), 2)
        self.assertEqual(self.rover.fire["approach"], [4, 3])

    def test_clear_removes_it(self):
        self.d.sc.fire_cell = (4, 2)
        self.d.tell_rover_fire()
        self.d.tell_rover_fire(clear=True)
        self.assertIsNone(self.rover.fire)
        self.assertTrue(self.events("FIRE_TARGET")[-1]["clear"])

    def test_a_rover_that_does_not_know_the_path_never_breaks_the_run(self):
        """404 — не авария: одна строка, флаг, дальше квадрат едет резервным каналом."""

        class OldRover(FakeRover):
            def tell_fire(self, payload):
                raise RobotError("rover: POST /fire -> 404 нет такого пути")

        self.fleet.rover = OldRover(self.clock, (3, 3), move_time=0.0)
        self.d.sc.fire_cell = (4, 2)
        self.d.tell_rover_fire()
        (target,) = self.events("FIRE_TARGET")
        self.assertFalse(target["ok"])
        self.assertIn("в теле /drive", target["reason"])
        self.assertFalse(self.d.rover_knows_fire)
        # Больше не долбим отказавший путь.
        self.d.tell_rover_fire(spot=(4, 3))
        self.assertEqual(len(self.events("FIRE_TARGET")), 1)

    def test_the_flag_switches_the_whole_exchange_off(self):
        self.d.tell_fire_on = False
        self.d.sc.fire_cell = (4, 2)
        self.d.tell_rover_fire()
        self.assertIsNone(self.rover.fire)
        self.assertEqual(self.events("FIRE_TARGET"), [])

    def test_a_forgotten_square_is_sent_again(self):
        """Агента ровера запускают руками и могут перезапустить посреди попытки."""
        self.d.sc.fire_cell = (4, 2)
        self.d.tell_rover_fire()
        self.rover.fire = None  # «перезапустили»
        self.d._heal_fire(self.rover.status())
        self.assertEqual(self.rover.fire["cell"], [4, 2])
        again = self.events("FIRE_TARGET")[-1]
        self.assertTrue(again["again"])
        self.assertIn("повторная отправка", again["reason"])

    def test_a_square_the_rover_still_has_is_not_resent(self):
        self.d.sc.fire_cell = (4, 2)
        self.d.tell_rover_fire()
        self.d._heal_fire(self.rover.status())
        self.assertEqual(len(self.events("FIRE_TARGET")), 1)

    def test_healing_stays_quiet_until_something_was_sent(self):
        """У ровера прошлой версии квадрата в статусе не будет никогда — не спамим."""
        self.d.sc.fire_cell = (4, 2)
        self.d._heal_fire({"cell": [3, 3]})
        self.assertEqual(self.events("FIRE_TARGET"), [])


if __name__ == "__main__":
    unittest.main()
