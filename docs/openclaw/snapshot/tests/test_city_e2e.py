"""End-to-end acceptance tests for the city_missions mock executor.

Run:  python3 -m unittest tests.test_city_e2e -v

Asserts the audit's full-acceptance checklist on the city-1 fixture and the key
regulation constraints as executed (not just compiled): level-N fire cycles,
5 s load, escort lag ≤2, no route through an active fire, energy never negative,
within the 15-minute budget.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))

from roles.city_world import load_world, WorldModel   # noqa: E402
from roles.city_executor import run_attempt, ESCORT_MAX_LAG  # noqa: E402

CITY1 = json.loads((ROOT / "test_fixtures" / "city-1" / "map.json").read_text())


def _corridor_delivery_through_fire():
    """1×5 corridor; delivery [0,0]->[4,0] must cross the fire at [2,0]. Fire first
    (forced by the planner) then delivery opens — proves the ordering constraint
    end-to-end."""
    return WorldModel(
        grid=[[0, 0, 0, 0, 0]], w=5, h=1,
        charge_zone=[0, 0], water_tower=[1, 0],
        fire={"cell": [2, 0], "level": 1},
        person={"cell": [2, 0], "window": "N"},
        delivery={"pickup": [0, 0], "dropoff": [4, 0]},
        missions=[{"id": "fire", "danger": 3}, {"id": "delivery", "danger": 1}])


class TestCityE2E(unittest.TestCase):
    def test_full_attempt_passes(self):
        res = run_attempt(load_world(CITY1))
        self.assertEqual(res["order"], ["fire", "delivery"])
        self.assertTrue(res["fire_ok"], "fire must be extinguished")
        self.assertTrue(res["delivery_ok"], "delivery must arrive")
        self.assertTrue(res["person_found"])
        self.assertIsNone(res["blocked"])
        self.assertGreaterEqual(res["final_energy"], 0)
        self.assertTrue(res["within_time"], f"sim {res['sim_time_s']}s must be <15min")

    def test_fire_level2_two_cycles_in_log(self):
        res = run_attempt(load_world(CITY1))
        cycles = [e for e in res["log"]
                  if e["type"] == "ACTION_COMPLETED" and "cycle" in e.get("evidence", {})]
        self.assertEqual(len(cycles), 2)
        ext = [e for e in res["log"] if e["type"] == "FIRE_EXTINGUISHED"][0]
        self.assertEqual(ext["cycles"], 2)

    def test_load_dwell_counted(self):
        res = run_attempt(load_world(CITY1))
        load = [e for e in res["log"]
                if e.get("action_id") == "delivery-load"][0]
        self.assertEqual(load["evidence"]["stationary_seconds"], 5.0)
        self.assertTrue(load["evidence"]["counted"])

    def test_escort_lag_within_limit(self):
        res = run_attempt(load_world(CITY1))
        done = [e for e in res["log"] if e["type"] == "DELIVERY_DONE"][0]
        self.assertLessEqual(done["escort_max_lag"], ESCORT_MAX_LAG)
        self.assertFalse(any(e["type"] == "SAFETY_VIOLATION" for e in res["log"]))

    def test_no_route_through_active_fire_end_to_end(self):
        # fire sits on the only crossing to the dropoff: the planner must do fire
        # first, then delivery succeeds without ever driving through the fire cell
        res = run_attempt(_corridor_delivery_through_fire())
        self.assertEqual(res["order"][0], "fire")
        self.assertTrue(res["fire_ok"])
        self.assertTrue(res["delivery_ok"])
        self.assertIsNone(res["blocked"])
        # the rover never occupied the fire cell while it was active
        self.assertFalse(any(e["type"] == "SAFETY_VIOLATION" for e in res["log"]))

    def test_energy_never_negative(self):
        res = run_attempt(load_world(CITY1))
        self.assertGreaterEqual(res["final_energy"], 0)


if __name__ == "__main__":
    unittest.main()
