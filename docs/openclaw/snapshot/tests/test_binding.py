"""Unit tests: привязка дрон↔хендлер (agent/binding.py) — несколько команд в
одной сети, постоянная память, отказ чужому хабу."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))

from binding import (  # noqa: E402
    accept_registration,
    fleet_for_task,
    load_binding,
    normalize_fleet,
    registration_meta,
    resolve,
    save_binding,
)


class TestResolve(unittest.TestCase):
    def test_env_only(self):
        cfg = resolve({"HANDLER_ID": "team-7", "HUB_URL": "http://h:8080",
                       "FLEET": "city", "AGENT_ID": "drone-3"}, {})
        self.assertEqual(cfg["handler_id"], "team-7")
        self.assertEqual(cfg["fleet"], "city")
        self.assertFalse(cfg["bound"])  # env не делает дрона привязанным

    def test_stored_binding_survives_reboot(self):
        stored = {"handler_id": "team-7", "hub_url": "http://h:8080",
                  "agent_id": "drone-3", "fleet": "city", "bound": True}
        cfg = resolve({}, stored)
        self.assertTrue(cfg["bound"])
        self.assertEqual(cfg["agent_id"], "drone-3")

    def test_env_overrides_stored(self):
        stored = {"handler_id": "team-7", "hub_url": "http://old:8080",
                  "agent_id": "drone-3", "fleet": "city", "bound": True}
        cfg = resolve({"HUB_URL": "http://new:8080"}, stored)
        self.assertEqual(cfg["hub_url"], "http://new:8080")
        self.assertTrue(cfg["bound"])  # handler не менялся — привязка жива

    def test_handler_conflict_unbinds(self):
        """Дрона перевезли в другую команду (env переписали) — старая привязка
        не должна тащить его к прежнему хендлеру."""
        stored = {"handler_id": "team-7", "agent_id": "drone-3", "bound": True}
        cfg = resolve({"HANDLER_ID": "team-9"}, stored)
        self.assertEqual(cfg["handler_id"], "team-9")
        self.assertFalse(cfg["bound"])
        self.assertTrue(cfg["stored_conflict"])


class TestFleet(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_fleet("PAINTERS"), "painter")
        self.assertEqual(normalize_fleet("survey"), "city")
        self.assertEqual(normalize_fleet("город"), "city")
        self.assertEqual(normalize_fleet("wat"), "")

    def test_fleet_for_task(self):
        self.assertEqual(fleet_for_task("painting"), "painter")
        self.assertEqual(fleet_for_task("survey"), "city")
        self.assertEqual(fleet_for_task("safe_passage"), "city")
        self.assertEqual(fleet_for_task("debate"), "")


class TestAcceptRegistration(unittest.TestCase):
    def test_own_drone_accepted(self):
        self.assertIsNone(accept_registration(
            "team-7", "city", {"handler_id": "team-7", "fleet": "city"}))

    def test_unbound_candidate_accepted(self):
        # ещё не привязан (пустой handler) — кандидат на LED-регистрацию
        self.assertIsNone(accept_registration(
            "team-7", "city", {"handler_id": "", "fleet": "city"}))

    def test_foreign_team_rejected(self):
        r = accept_registration("team-7", "city",
                                {"handler_id": "team-9", "fleet": "city"})
        self.assertIn("team-9", r or "")

    def test_wrong_fleet_rejected(self):
        r = accept_registration("team-7", "city",
                                {"handler_id": "team-7", "fleet": "painter"})
        self.assertIn("fleet", r or "")

    def test_open_hub_accepts_anyone(self):
        self.assertIsNone(accept_registration("", "", {"handler_id": "x",
                                                       "fleet": "painter"}))


class TestPersistence(unittest.TestCase):
    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "nested" / "binding.json"
            data = {"handler_id": "team-7", "agent_id": "drone-3", "bound": True}
            self.assertTrue(save_binding(data, p))
            self.assertEqual(load_binding(p)["handler_id"], "team-7")

    def test_load_missing_is_empty(self):
        self.assertEqual(load_binding(Path("/nonexistent/binding.json")), {})

    def test_registration_meta_carries_identity(self):
        meta = registration_meta({"handler_id": "team-7", "fleet": "city",
                                  "bound": True}, {"name": "Magpie"})
        self.assertEqual(meta["handler_id"], "team-7")
        self.assertEqual(meta["fleet"], "city")
        self.assertTrue(meta["bound"])
        self.assertEqual(meta["name"], "Magpie")


if __name__ == "__main__":
    unittest.main()
