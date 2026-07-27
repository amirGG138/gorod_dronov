"""In-process E2E for the test-3x3 scan_debate scenario (no docker, no LLM, no bort).

Drives the real coordinator/controller/flyer role logic through the phase machine
against an in-memory board, proving:
  * the two pilots propose DIFFERENT full-coverage routes and argue;
  * the single flyer scans the ACTIVE pilot's route to completion -> DONE;
  * switching the helm (state/control.json) mid-scan re-routes the flyer onto the
    OTHER pilot's path and it covers the whole field that way instead.

Run:  python3 -m unittest tests.test_scan_debate -v
"""
import json
import os
import sys
import types
import unittest
from pathlib import Path

os.environ["SCAN_SIM_STEP"] = "0"          # no sleeps in the flight simulation

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))

import roles                                                    # noqa: E402
from roles import scan_debate                                   # noqa: E402

MAP = json.loads((ROOT / "test_fixtures" / "test-3x3" / "map.json").read_text())
ALL_CELLS = sorted((x, y) for y in range(3) for x in range(3))
CONTROL = "/mock/state/control.json"


class MockBB:
    def __init__(self):
        self._phase = {"phase": "INIT", "round": 0}
        self._world: dict = {}
        self.messages: list = []
        self.events: list = []
        self._progress: dict = {}
        self._json: dict = {}
        self.state = Path("/mock/state")

    def read_phase(self): return dict(self._phase)
    def write_phase(self, phase, round_=0, deadline=None):
        self._phase = {"phase": phase, "round": round_}
    def read_world(self): return dict(self._world)
    def write_world(self, obj): self._world = dict(obj)
    def read_all_progress(self): return {k: dict(v) for k, v in self._progress.items()}
    def list_messages(self): return list(self.messages)
    def append_event(self, ev): self.events.append(ev)
    def write_progress(self, aid, entry): self._progress[aid] = dict(entry)
    def write_json(self, path, obj): self._json[str(path)] = obj
    def read_json(self, path, default=None): return self._json.get(str(path), default)


class MockBrain:
    is_mock = True


AGENTS = [("coordinator", "coordinator"), ("pilot-a", "controller"),
          ("pilot-b", "controller"), ("drone-1", "flyer")]


def _ctx(bb, aid, role):
    ctx = types.SimpleNamespace()
    ctx.bb = bb
    ctx.brain = MockBrain()
    ctx.agent_id = aid
    ctx.role = role
    ctx.config = {"task": "scan_debate", "controllers": ["pilot-a", "pilot-b"],
                  "flyer": "drone-1"}
    ctx.scenario_map = MAP
    ctx.soul = {}
    ctx.soul_body = ""
    ctx.bridge = None
    ctx.phase = bb.read_phase()
    ctx.messages = bb.list_messages()
    ctx.progress = bb.read_all_progress()
    ctx.world = bb.read_world()
    ctx.emit = bb.append_event
    return ctx


def _run(bb, cycles=40, hook=None):
    for i in range(cycles):
        if bb.read_phase()["phase"] == "DONE":
            break
        for aid, role in AGENTS:
            res = roles.step(_ctx(bb, aid, role))
            for m in res.get("messages", []):
                m.setdefault("id", f"m{len(bb.messages)}")
                bb.messages.append(m)
        if hook:
            hook(bb, i)
    return bb


class TestScanDebate(unittest.TestCase):
    def test_routes_distinct_and_cover_all(self):
        ra = scan_debate.route_for(MAP, 0)
        rb = scan_debate.route_for(MAP, 1)
        self.assertEqual(sorted(map(tuple, ra)), ALL_CELLS)
        self.assertEqual(sorted(map(tuple, rb)), ALL_CELLS)
        self.assertNotEqual(ra, rb, "два пилота должны предлагать РАЗНЫЕ маршруты")
        self.assertEqual(ra[-1], [1, 1], "pilot-a (периметр) снимает центр последним")
        self.assertEqual(rb[0], [1, 1], "pilot-b (спираль) стартует с центра")

    def test_debate_then_scan_reaches_done(self):
        bb = _run(MockBB())
        self.assertEqual(bb.read_phase()["phase"], "DONE")
        self.assertTrue([m for m in bb.messages if m.get("type") == "ROUTE"],
                        "пилоты обязаны предложить маршруты")
        self.assertTrue([m for m in bb.messages if m.get("type") == "REBUTTAL"],
                        "должен быть хотя бы один rebuttal (спор)")
        self.assertEqual(bb.read_json(CONTROL, {}).get("active"), "pilot-a",
                         "по умолчанию у руля pilot-a")
        fp = bb.read_all_progress().get("drone-1", {})
        self.assertEqual(fp.get("active"), "pilot-a")
        self.assertEqual(sorted(map(tuple, fp.get("flown", []))), ALL_CELLS,
                         "борт снял все клетки активного маршрута")

    def test_switch_helm_flies_second_route(self):
        bb = MockBB()

        def switch_once(b, i):
            # as soon as the scan starts and the bort has flown a couple of cells
            # of pilot-a, the operator flips the helm to pilot-b (as in a pause).
            fp = b.read_all_progress().get("drone-1", {})
            if (b.read_phase()["phase"] == "SCAN" and fp.get("flying") == "pilot-a"
                    and fp.get("idx", 0) >= 2
                    and b.read_json(CONTROL, {}).get("active") == "pilot-a"):
                b.write_json(b.state / "control.json", {"active": "pilot-b"})

        _run(bb, cycles=60, hook=switch_once)
        self.assertEqual(bb.read_phase()["phase"], "DONE")
        fp = bb.read_all_progress().get("drone-1", {})
        self.assertEqual(fp.get("active"), "pilot-b",
                         "после переключения борт исполняет маршрут pilot-b")
        self.assertEqual(sorted(map(tuple, fp.get("flown", []))), ALL_CELLS,
                         "поле покрыто целиком и по второму маршруту")
        self.assertTrue(any(e.get("kind") == "helm" and e.get("active") == "pilot-b"
                            for e in bb.events), "должно быть событие смены руля")


if __name__ == "__main__":
    unittest.main()
