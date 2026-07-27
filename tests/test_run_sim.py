import json
import tempfile
import unittest

from city import config as config_mod
from city.clock import SimClock
from city.dispatcher import Dispatcher
from city.field import Field
from city.log import EVENT_TYPES, Log
from city.robots.fleet import build_fleet
from city.run import main

# События, за которыми стоит решение: у них обязан быть reason по-русски —
# это и есть «формат логов решений» из требований регламента к README.
DECISIONS = {
    "MISSION_ORDER",
    "CHARGED",
    "DWELL",
    "FIRE_CYCLE",
    "FIRE_EXTINGUISHED",
    "DELIVERY_DONE",
    "VUP_ABSENT",
    "ENERGY_BLOCK",
    "ERROR",
}


def run_and_read(argv):
    with tempfile.TemporaryDirectory() as tmp:
        code = main(["--quiet", "--logs", tmp, *argv])
        import glob
        import os

        path = sorted(glob.glob(os.path.join(tmp, "run-*.jsonl")))[-1]
        with open(path, encoding="utf-8") as fh:
            events = [json.loads(line) for line in fh if line.strip()]
    return code, events


class TestFullRun(unittest.TestCase):
    def setUp(self):
        self.code, self.events = run_and_read(["--sim"])
        self.types = [e["type"] for e in self.events]

    def test_run_succeeds(self):
        self.assertEqual(self.code, 0)

    def test_timeline_order(self):
        for earlier, later in (
            ("SURVEY", "MISSION_ORDER"),
            ("MISSION_ORDER", "CHARGED"),
            ("CHARGED", "FIRE_EXTINGUISHED"),
            ("FIRE_EXTINGUISHED", "DELIVERY_DONE"),
            ("DELIVERY_DONE", "DONE"),
        ):
            self.assertLess(self.types.index(earlier), self.types.index(later), f"{earlier} < {later}")

    def test_every_event_type_is_known(self):
        for t in self.types:
            self.assertIn(t, EVENT_TYPES)

    def test_decisions_carry_a_reason(self):
        for e in self.events:
            if e["type"] in DECISIONS:
                self.assertTrue(e.get("reason"), f"{e['type']} без причины: {e}")

    def test_all_dwells_counted(self):
        dwells = [e for e in self.events if e["type"] == "DWELL"]
        self.assertEqual(len(dwells), 3)  # два забора воды + погрузка
        for d in dwells:
            self.assertTrue(d["counted"], d)
            self.assertFalse(d["moved"], d)
            self.assertIn(d["led"], ("on", "blink"))

    def test_fire_cycles_match_the_level(self):
        cycles = [e for e in self.events if e["type"] == "FIRE_CYCLE"]
        self.assertEqual(len(cycles), 2)

    def test_energy_never_goes_negative(self):
        for e in self.events:
            if "energy" in e:
                self.assertGreaterEqual(e["energy"], 0, e)

    def test_charged_covers_all_moves(self):
        charged = next(e for e in self.events if e["type"] == "CHARGED")
        done = next(e for e in self.events if e["type"] == "DONE")
        self.assertEqual(charged["units"], done["energy_spent"] + done["energy_left"])

    def test_vup_absence_is_stated_not_faked(self):
        absent = [e for e in self.events if e["type"] == "VUP_ABSENT"]
        self.assertEqual({e["mission"] for e in absent}, {"fire", "delivery"})
        self.assertFalse([e for e in self.events if e["type"] == "PERSON_FOUND"])
        self.assertFalse([e for e in self.events if e["type"] == "ESCORT"])

    def test_no_errors(self):
        self.assertFalse([e for e in self.events if e["type"] == "ERROR"])


class TestScenarioOverrides(unittest.TestCase):
    def test_fire_level_three_gives_three_cycles(self):
        code, events = run_and_read(["--sim", "--fire-level", "3"])
        self.assertEqual(code, 0)
        self.assertEqual(len([e for e in events if e["type"] == "FIRE_CYCLE"]), 3)

    def test_vup_flag_turns_on_escort(self):
        code, events = run_and_read(["--sim", "--vup"])
        self.assertEqual(code, 0)
        escorts = [e for e in events if e["type"] == "ESCORT"]
        self.assertTrue(escorts)
        self.assertFalse([e for e in escorts if e["state"] == "violation"])
        self.assertFalse([e for e in events if e["type"] == "VUP_ABSENT"])

    def test_monitors_fly_and_land(self):
        code, events = run_and_read(["--sim", "--drones"])
        self.assertEqual(code, 0)
        survey = next(e for e in events if e["type"] == "SURVEY")
        self.assertEqual(survey["source"], "drones")
        self.assertEqual(survey["shots"], 4)


class TestEnergyBlock(unittest.TestCase):
    """Недозаряженный ровер обязан встать и честно об этом написать."""

    class Starved(Dispatcher):
        def precharge(self, budget, reason):
            self.energy.charge(3)
            self.log.ev("CHARGED", units=3, seconds=3, energy=3, reason="учебная недозарядка")

    def test_zero_energy_stops_the_rover(self):
        cfg = config_mod.load()
        clock = SimClock()
        with tempfile.TemporaryDirectory() as tmp:
            log = Log(clock, run_dir=tmp, echo=False)
            fleet = build_fleet(cfg, clock)
            code = self.Starved(cfg, Field.from_config(cfg), log, clock, fleet).run()
            log.close()
            with open(log.path, encoding="utf-8") as fh:
                events = [json.loads(line) for line in fh]
        self.assertEqual(code, 1)
        blocks = [e for e in events if e["type"] == "ENERGY_BLOCK"]
        self.assertTrue(blocks)
        self.assertIn("заряд", blocks[0]["reason"])
        done = next(e for e in events if e["type"] == "DONE")
        self.assertEqual(done["missions"], [])


if __name__ == "__main__":
    unittest.main()
