"""In-process multi-agent E2E for city_missions (no docker, no LLM, no robots).

Drives the real coordinator/scout/safety_drone role logic through the phase
machine against an in-memory blackboard, proving the agents actually coordinate:
scouts fly zones and post structured OBSERVATIONs -> the coordinator consolidates
confirmed facts -> ranks + executes the missions -> the evidence trail lands on
the board and the phase reaches DONE.

Run:  python3 -m unittest tests.test_city_agents -v
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))

import roles                                        # noqa: E402

CITY1 = json.loads((ROOT / "test_fixtures" / "city-1" / "map.json").read_text())


class MockBB:
    def __init__(self):
        self._phase = {"phase": "INIT", "round": 0}
        self._world: dict = {}
        self.messages: list = []
        self.events: list = []
        self._progress: dict = {}

    def read_phase(self): return dict(self._phase)
    def write_phase(self, phase, round_=0, deadline=None):
        self._phase = {"phase": phase, "round": round_}
    def read_world(self): return dict(self._world)
    def write_world(self, obj): self._world = dict(obj)
    def read_all_progress(self): return dict(self._progress)
    def read_assignments(self): return {}
    def list_messages(self): return list(self.messages)
    def append_event(self, ev): self.events.append(ev)
    def write_progress(self, aid, entry): self._progress[aid] = entry


class MockBrain:
    is_mock = True


def _run(scenario_map, agents, cycles=30):
    bb = MockBB()
    scouts = [a for a, r in agents if r == "scout"]
    for _ in range(cycles):
        if bb.read_phase()["phase"] == "DONE":
            break
        for agent_id, role in agents:
            ctx = type("Ctx", (), {})()
            ctx.bb = bb
            ctx.brain = MockBrain()
            ctx.agent_id = agent_id
            ctx.role = role
            ctx.config = {"task": "city_missions", "scouts": scouts, "sectors": []}
            ctx.scenario_map = scenario_map
            ctx.soul = {}
            ctx.soul_body = ""
            ctx.bridge = None
            ctx.phase = bb.read_phase()
            ctx.messages = bb.list_messages()
            ctx.assignments = bb.read_assignments()
            ctx.progress = bb.read_all_progress()
            ctx.world = bb.read_world()
            ctx.emit = bb.append_event
            res = roles.step(ctx)
            for m in res.get("messages", []):
                bb.messages.append(m)
    return bb


AGENTS = ([("coordinator", "coordinator")]
          + [(f"drone-{i}", "scout") for i in range(1, 5)]
          + [("rover", "rover"), ("safety-1", "safety_drone")])


class TestCityAgents(unittest.TestCase):
    def test_multiagent_attempt_reaches_done(self):
        bb = _run(CITY1, AGENTS)
        self.assertEqual(bb.read_phase()["phase"], "DONE")

    def test_scouts_post_observations(self):
        bb = _run(CITY1, AGENTS)
        obs = [m for m in bb.messages if m.get("type") == "OBSERVATION"]
        self.assertTrue(obs, "scouts must publish OBSERVATIONs")
        # fire + delivery pickup/dropoff + person all observed by someone
        seen = {d["type"] for m in obs for d in (m["payload"].get("detections") or [])}
        for t in ("fire", "delivery_pickup", "delivery_dropoff", "person_in_window"):
            self.assertIn(t, seen, f"{t} must be observed")

    def test_coordinator_consolidates_and_executes(self):
        bb = _run(CITY1, AGENTS)
        w = bb.read_world()
        self.assertTrue(w.get("done"))
        self.assertEqual(w["facts"]["fire"]["cell"], [4, 2])   # fire on a non-aruco house
        self.assertEqual(int(w["facts"]["fire"]["level"]), 2)
        res = w["result"]
        self.assertTrue(res["fire_ok"] and res["delivery_ok"])
        self.assertTrue(res["person_found"])
        self.assertTrue(res["within_time"])

    def test_evidence_trail_on_board(self):
        bb = _run(CITY1, AGENTS)
        kinds = [e.get("type") for e in bb.events if e.get("kind") == "city_evidence"]
        self.assertIn("FIRE_EXTINGUISHED", kinds)
        self.assertIn("DELIVERY_DONE", kinds)
        self.assertIn("PERSON_FOUND", kinds)
        # coordinator published a plan decision + a final report
        types = {m.get("type") for m in bb.messages if m.get("from") == "coordinator"}
        self.assertIn("DECISION", types)
        self.assertIn("REPORT", types)


if __name__ == "__main__":
    unittest.main()
