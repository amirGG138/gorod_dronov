"""Unit tests for the survey mission's pure logic (agent/roles/survey_common.py).

Run:  python3 -m unittest discover -s tests -v
(stdlib only — no pytest dependency, consistent with the repo's zero-deps rule)
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))

from roles.survey_common import (  # noqa: E402
    cell_key,
    chebyshev,
    flight_wait,
    next_verifier,
    plan_summary,
    quorum_state,
    serpentine,
    sweep_plan,
    validate_plan,
    verify_plan,
    zone_split,
    zones_from_map,
)


class TestGrid(unittest.TestCase):
    def test_serpentine_covers_all_cells_once(self):
        path = serpentine(5, 5)
        self.assertEqual(len(path), 25)
        self.assertEqual(len({cell_key(c) for c in path}), 25)

    def test_serpentine_adjacent_steps(self):
        """Каждый следующий шаг змейки — соседняя клетка (эффективный маршрут)."""
        path = serpentine(5, 5)
        for a, b in zip(path, path[1:]):
            self.assertEqual(chebyshev(a, b), 1, f"{a} -> {b} не соседи")

    def test_zone_split_sizes_and_disjoint(self):
        zones = zone_split(5, 5, 4)
        sizes = sorted((len(z) for z in zones), reverse=True)
        self.assertEqual(sizes, [7, 6, 6, 6])
        seen = set()
        for z in zones:
            for c in z:
                self.assertNotIn(cell_key(c), seen)
                seen.add(cell_key(c))
        self.assertEqual(len(seen), 25)

    def test_zones_from_map_prefers_fixture(self):
        m = {"grid_size": [5, 5], "zones": {"Z1": [[0, 0]], "Z2": [[1, 0]]}}
        z = zones_from_map(m, ["Z1", "Z2"])
        self.assertEqual(z["Z1"], [[0, 0]])

    def test_zones_from_map_autosplit_when_missing(self):
        z = zones_from_map({"grid_size": [5, 5]}, ["A", "B", "C", "D"])
        self.assertEqual(sum(len(v) for v in z.values()), 25)


class TestPlans(unittest.TestCase):
    def test_sweep_plan_shape(self):
        plan = sweep_plan([0, 0], [[1, 0], [2, 0]], cells_per_turn=2,
                          wait_per_cell=20, wait_max=60)
        self.assertEqual([a["do"] for a in plan],
                         ["fly_to", "wait", "photo_analyze"] * 2)
        self.assertEqual(plan[1]["seconds"], 20)

    def test_flight_wait_scales_with_distance_and_caps(self):
        self.assertEqual(flight_wait(1, 20, 60), 20)
        self.assertEqual(flight_wait(2, 20, 60), 40)
        self.assertEqual(flight_wait(5, 20, 60), 60)  # cap

    def test_verify_plan_uses_close_look(self):
        plan = verify_plan([0, 0], [3, 3], wait_per_cell=20, wait_max=60)
        self.assertTrue(plan[-1].get("close_look"))

    def test_validate_plan_clamps_and_filters(self):
        raw = [
            {"do": "fly_to", "cell": [99, -5]},          # вне поля -> кламп
            {"do": "wait", "seconds": 999},               # > cap
            {"do": "photo_analyze"},
            {"do": "self_destruct"},                      # неизвестный глагол
        ]
        plan, problems = validate_plan(raw, w=5, h=5, wait_max=60)
        self.assertEqual(plan[0]["cell"], [4, 0])
        self.assertEqual(plan[1]["seconds"], 60)
        self.assertTrue(any("self_destruct" in p for p in problems))

    def test_validate_plan_respects_allowed_cells(self):
        raw = [{"do": "fly_to", "cell": [4, 4]}, {"do": "photo_analyze"}]
        plan, problems = validate_plan(raw, w=5, h=5, allowed_cells=[[0, 0]])
        # чужая клетка выброшена, но фото осталось -> план валиден
        self.assertEqual([a["do"] for a in plan], ["photo_analyze"])
        self.assertTrue(any("outside allowed" in p for p in problems))

    def test_validate_plan_requires_photo(self):
        plan, problems = validate_plan([{"do": "fly_to", "cell": [1, 1]}], w=5, h=5)
        self.assertEqual(plan, [])
        self.assertTrue(any("no photo_analyze" in p for p in problems))

    def test_plan_summary_readable(self):
        s = plan_summary([{"do": "fly_to", "cell": [1, 1]},
                          {"do": "wait", "seconds": 20},
                          {"do": "photo_analyze"}])
        self.assertIn("→[1,1]", s)
        self.assertIn("20с", s)


class TestQuorum(unittest.TestCase):
    QUEUE = ["drone-1", "drone-3", "drone-4"]

    def test_pending_until_all_when_verify_all(self):
        st = quorum_state({"drone-1": True, "drone-3": True}, self.QUEUE,
                          quorum=2, verify_all=True)
        self.assertEqual(st, "pending")  # «полетели все по очереди»

    def test_confirm_after_all_voted(self):
        st = quorum_state({"drone-1": True, "drone-3": True, "drone-4": False},
                          self.QUEUE, quorum=2, verify_all=True)
        self.assertEqual(st, "confirmed")

    def test_reject_when_quorum_unreachable(self):
        st = quorum_state({"drone-1": False, "drone-3": False, "drone-4": False},
                          self.QUEUE, quorum=2, verify_all=True)
        self.assertEqual(st, "rejected")

    def test_early_confirm_without_verify_all(self):
        st = quorum_state({"drone-1": True, "drone-3": True}, self.QUEUE,
                          quorum=2, verify_all=False)
        self.assertEqual(st, "confirmed")

    def test_early_reject_without_verify_all(self):
        st = quorum_state({"drone-1": False, "drone-3": False}, self.QUEUE,
                          quorum=2, verify_all=False)
        self.assertEqual(st, "rejected")  # 2 «нет» из 3 — кворум 2 «да» недостижим

    def test_next_verifier_in_queue_order(self):
        self.assertEqual(next_verifier(self.QUEUE, {}), "drone-1")
        self.assertEqual(next_verifier(self.QUEUE, {"drone-1": False}), "drone-3")
        self.assertIsNone(next_verifier(self.QUEUE,
                                        {q: True for q in self.QUEUE}))


if __name__ == "__main__":
    unittest.main()
