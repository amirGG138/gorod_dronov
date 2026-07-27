"""Unit tests for city_missions pure logic (agent/roles/city_world.py).

Run:  python3 -m unittest discover -s tests -v
(stdlib only — no pytest, consistent with the repo's zero-deps rule)

Covers the audit's mandatory negative cases: 2.9 s water dwell rejected, 4.9 s
load dwell rejected, delivery route through an active fire rejected, movement at
zero energy blocked, plus the level-2 fire = exactly two water→fire cycles.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))

from roles.city_world import (  # noqa: E402
    EnergyLedger, EnergyError, RouteBlocked, WorldModel, load_world,
    astar, path_moves, fire_route, delivery_route, rank_missions,
    water_dwell_valid, load_dwell_valid, WATER_DWELL_S, LOAD_DWELL_S,
)

CITY1 = json.loads((ROOT / "test_fixtures" / "city-1" / "map.json").read_text())


def _corridor_world(fire_cell=None, level=1):
    """1×3 corridor [0,0]-[1,0]-[2,0]; pickup at 0,0 dropoff at 2,0, middle is the
    only crossing — used to prove the 'no delivery through active fire' rule."""
    return WorldModel(
        grid=[[0, 0, 0]], w=3, h=1, charge_zone=[0, 0], water_tower=[0, 0],
        fire={"cell": fire_cell, "level": level} if fire_cell else None,
        delivery={"pickup": [0, 0], "dropoff": [2, 0]})


class TestGridAndEnergy(unittest.TestCase):
    def test_astar_avoids_buildings(self):
        w = load_world(CITY1)
        # [1,1] is a building (drone pad on a roof) -> path must not step on it
        path = astar(w.grid, [0, 0], [2, 2])
        self.assertIsNotNone(path)
        self.assertNotIn([1, 1], path[1:-1])
        self.assertEqual(path[0], [0, 0])
        self.assertEqual(path[-1], [2, 2])

    def test_astar_blocked_returns_none(self):
        # corridor with the middle blocked -> unreachable
        self.assertIsNone(astar([[0, 0, 0]], [0, 0], [2, 0], blocked=[[1, 0]]))

    def test_energy_charge_and_spend(self):
        e = EnergyLedger()
        self.assertEqual(e.energy, 0)
        e.charge(3)                     # 3 confirmed seconds -> 3 units
        self.assertEqual(e.energy, 3)
        for _ in range(3):
            e.spend_move()
        self.assertEqual(e.energy, 0)

    def test_zero_energy_blocks_move(self):
        e = EnergyLedger()
        with self.assertRaises(EnergyError):
            e.spend_move()

    def test_partial_second_not_credited(self):
        e = EnergyLedger()
        e.charge(2.9)                   # only whole confirmed seconds count
        self.assertEqual(e.energy, 2)


class TestDwellValidators(unittest.TestCase):
    def test_water_dwell_exact_boundary(self):
        self.assertTrue(water_dwell_valid(WATER_DWELL_S))
        self.assertFalse(water_dwell_valid(2.9))            # 2.9 s not counted
        self.assertFalse(water_dwell_valid(3.0, moved=True))
        self.assertFalse(water_dwell_valid(3.0, led_on=False))
        self.assertFalse(water_dwell_valid(3.0, in_zone=False))

    def test_load_dwell_exact_boundary(self):
        self.assertTrue(load_dwell_valid(LOAD_DWELL_S))
        self.assertFalse(load_dwell_valid(4.9))             # 4.9 s not counted
        self.assertFalse(load_dwell_valid(5.0, led_on=False))


class TestFireRoute(unittest.TestCase):
    def test_level2_has_two_cycles(self):
        w = load_world(CITY1)
        self.assertEqual(int(w.fire["level"]), 2)
        actions, moves = fire_route(w)
        water_dwells = [a for a in actions
                        if a["do"] == "dwell" and a.get("led") == "blink"]
        fire_dwells = [a for a in actions if a["action_id"].endswith("extinguish")]
        self.assertEqual(len(water_dwells), 2)              # exactly 2 water trips
        self.assertEqual(len(fire_dwells), 2)
        for a in water_dwells:
            self.assertEqual(a["seconds"], WATER_DWELL_S)
            self.assertIn("pose_stable_3s", a["success_evidence"])
        self.assertGreater(moves, 0)
        self.assertTrue(actions[-1]["do"] == "done")

    def test_level_scales(self):
        w = load_world(CITY1)
        w.fire["level"] = 3
        actions, _ = fire_route(w)
        self.assertEqual(sum(1 for a in actions if a["action_id"].endswith("water-dwell")), 3)


class TestDeliveryRoute(unittest.TestCase):
    def test_delivery_has_5s_load(self):
        w = load_world(CITY1)
        actions, moves = delivery_route(w, avoid_fire=False)
        load = [a for a in actions if a["action_id"] == "del-load-dwell"][0]
        self.assertEqual(load["seconds"], LOAD_DWELL_S)
        self.assertEqual(load["led"], "blink")
        self.assertTrue(any(a["do"] == "escort" for a in actions))
        self.assertGreater(moves, 0)

    def test_delivery_blocked_by_active_fire(self):
        w = _corridor_world(fire_cell=[1, 0])              # fire on the only crossing
        with self.assertRaises(RouteBlocked):
            delivery_route(w, avoid_fire=True)
        # once extinguished, the route opens
        w.fire["extinguished"] = True
        actions, _ = delivery_route(w, avoid_fire=True)
        self.assertTrue(actions)

    def test_delivery_ignores_extinguished_fire(self):
        w = load_world(CITY1)
        w.fire["extinguished"] = True
        actions, _ = delivery_route(w, avoid_fire=True)     # must not raise
        self.assertTrue(actions)


class TestPlanner(unittest.TestCase):
    def test_fire_first_when_it_blocks_delivery(self):
        # corridor: delivery [0,0]->[2,0] must cross [1,0]; fire sits there
        w = _corridor_world(fire_cell=[1, 0])
        w.missions = [{"id": "fire", "danger": 3}, {"id": "delivery", "danger": 1}]
        order, reasons = rank_missions(w)
        self.assertEqual(order[0], "fire")
        self.assertIn("constraint", reasons)

    def test_order_by_danger_when_independent(self):
        w = load_world(CITY1)                               # fire in a corner, no block
        order, _ = rank_missions(w)
        self.assertEqual(set(order), {"fire", "delivery"})
        self.assertEqual(order[0], "fire")                  # higher danger first


if __name__ == "__main__":
    unittest.main()
