"""Бортовой агент дрона: вытеснение команд, повторы и честность про посадку.

Железа здесь нет: вместо sverk_interfaces подставляется заглушка Board, считающая
вызовы navigate и land. Проверяется ровно то, что можно проверить без полёта, —
кто пишет состояние и что борт про это состояние утверждает. Останется ли живой
navigate управляемым, когда поверх него приходит land, проверяется только полётом.
"""

import importlib.util
import json
import os
import threading
import time
import types
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "drone_agent", os.path.join(ROOT, "onboard", "drone_agent.py")
)
da = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(da)

# Строки борта адресованы человеку, стоящему рядом с дроном; в прогоне тестов это
# просто шум, тем более что паузы укорочены и потоки печатают вперемешку.
da.say = lambda text: None


class Resp:
    def __init__(self, success: bool = True, message: str = "") -> None:
        self.success = success
        self.message = message


class Control:
    """Полётный контроллер-заглушка: считает команды и держит признак arm."""

    def __init__(self) -> None:
        self.navigates = 0
        self.lands = 0
        self.armed = True
        self.telemetry_hangs = False

    def navigate(self, **kw):
        self.navigates += 1
        self.armed = True
        return Resp()

    def land(self):
        self.lands += 1
        self.armed = False
        return Resp()

    def get_telemetry(self, frame_id="body"):
        if self.telemetry_hangs:
            time.sleep(30.0)
        return types.SimpleNamespace(x=0.0, y=0.0, z=0.0, armed=self.armed, mode="OFFBOARD")


class Board:
    def __init__(self) -> None:
        self.control = Control()


def make_agent(*argv: str):
    """Агент с заглушкой вместо борта. Паузы укорочены: ждать нечего, железа нет."""
    args = da.build_parser().parse_args(
        ["--climb-speed", "100", "--settle", "0.4", "--land-wait", "0.1",
         "--watchdog", "0", *argv]
    )
    agent = da.Agent(args)
    if not args.dry:
        agent.drone = Board()
    return agent


def wait_state(agent, states, seconds=5.0) -> str:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if agent.state in states:
            return agent.state
        time.sleep(0.02)
    return agent.state


class TestPreemption(unittest.TestCase):
    """Аварийная посадка обязана вытеснить взлёт, а не встать за ним в очередь."""

    def test_stop_during_takeoff_lands_and_takeoff_does_not_write_hover(self):
        agent = make_agent()
        agent.takeoff(1.5)
        time.sleep(0.05)  # navigate уже издан, борт досыпает набор высоты
        agent.stop()

        self.assertEqual(wait_state(agent, ("landed", "landed_unverified")), "landed_unverified")
        self.assertEqual(agent.drone.control.lands, 1)
        # Досыпающий взлёт просыпается уже после посадки: если он допишет «вишу»,
        # оператор увидит в пульте летящий дрон вместо севшего.
        time.sleep(0.6)
        self.assertEqual(agent.state, "landed_unverified")

    def test_second_takeoff_does_not_issue_a_second_navigate(self):
        agent = make_agent()
        agent.takeoff(1.5)
        wait_state(agent, ("hover",))
        agent.takeoff(1.5)
        self.assertEqual(agent.drone.control.navigates, 1)

    def test_ordinary_command_while_busy_is_refused(self):
        """Вытесняет только аварийная посадка: обычная команда так же ждёт очереди."""
        agent = make_agent()
        agent.takeoff(1.5)
        with self.assertRaises(da.Busy):
            agent.land()


class TestDedup(unittest.TestCase):
    """Повтор POST по потерянному ответу — не вторая команда."""

    def test_same_command_id_runs_once(self):
        agent = make_agent()
        first = agent.once("cmd-1", lambda: agent.takeoff(1.5))
        second = agent.once("cmd-1", lambda: agent.takeoff(1.5))
        self.assertTrue(first["accepted"])
        self.assertTrue(second["deduplicated"])
        self.assertNotIn("deduplicated", first)
        wait_state(agent, ("hover",))
        self.assertEqual(agent.drone.control.navigates, 1)

    def test_repeat_gets_an_answer_instead_of_busy(self):
        """Без дедупликации повтор ловил бы 409 «занят» на свою же команду."""
        agent = make_agent()
        agent.once("cmd-2", lambda: agent.takeoff(1.5))
        again = agent.once("cmd-2", lambda: agent.takeoff(1.5))
        self.assertTrue(again["accepted"])

    def test_different_ids_are_different_commands(self):
        agent = make_agent()
        agent.once("a", lambda: agent.takeoff(1.5))
        wait_state(agent, ("hover",))
        agent.once("b", agent.land)
        self.assertEqual(wait_state(agent, ("landed", "landed_unverified")), "landed_unverified")
        self.assertEqual(agent.drone.control.lands, 1)

    def test_refusal_is_not_remembered(self):
        """Отказ — не выполненная работа: повтор имеет право получить свежий ответ."""
        agent = make_agent()  # без --allow-goto перелёт запрещён
        with self.assertRaises(da.Refused):
            agent.once("cmd-3", lambda: agent.goto([2, 2], 1.5))
        with self.assertRaises(da.Refused):
            agent.once("cmd-3", lambda: agent.goto([2, 2], 1.5))

    def test_command_without_id_still_works(self):
        """curl с руки никакого id не шлёт — это должно остаться рабочим."""
        agent = make_agent()
        self.assertTrue(agent.once("", lambda: agent.takeoff(1.5))["accepted"])


class TestLandingIsNotOverclaimed(unittest.TestCase):
    """«Принял команду» и «сел» — разные вещи, и статус обязан их различать."""

    def test_without_telemetry_landing_stays_unverified(self):
        agent = make_agent()
        agent.land()
        self.assertEqual(wait_state(agent, ("landed", "landed_unverified")), "landed_unverified")

    def test_disarm_in_telemetry_confirms_landing(self):
        agent = make_agent("--telemetry")
        agent.land()
        self.assertEqual(wait_state(agent, ("landed", "landed_unverified")), "landed")

    def test_still_armed_is_not_a_landing(self):
        agent = make_agent("--telemetry")
        agent.drone.control.land = lambda: Resp()  # команда принята, дрон не сел
        agent.land()
        self.assertEqual(wait_state(agent, ("landed", "landed_unverified")), "landed_unverified")

    def test_hanging_telemetry_does_not_wedge_the_landing(self):
        """get_telemetry на наших сборках виснет — посадка не должна виснуть с ним."""
        agent = make_agent("--telemetry")
        agent.drone.control.telemetry_hangs = True
        agent.land()
        self.assertEqual(wait_state(agent, ("landed", "landed_unverified"), 8.0), "landed_unverified")

    def test_refused_land_says_so(self):
        agent = make_agent()
        agent.drone.control.land = lambda: Resp(success=False, message="нет связи с FCU")
        agent.land()
        self.assertEqual(wait_state(agent, ("land_failed",), 8.0), "land_failed")
        self.assertNotIn(agent.state, da.ON_GROUND)


class TestOverHttp(unittest.TestCase):
    """То же самое, но через сокет: command_id должен доехать из тела запроса."""

    def setUp(self):
        self.agent = make_agent()
        handler = type("Bound", (da.Handler,), {"agent": self.agent})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(
            f"{self.url}{path}", data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def test_resent_takeoff_does_not_fly_twice(self):
        body = {"alt": 1.5, "command_id": "aaaa-bbbb"}
        self.assertTrue(self.post("/takeoff", body)["accepted"])
        self.assertTrue(self.post("/takeoff", body)["deduplicated"])
        wait_state(self.agent, ("hover",))
        self.assertEqual(self.agent.drone.control.navigates, 1)

    def test_status_reports_the_unverified_landing(self):
        self.post("/land", {"command_id": "l-1"})
        wait_state(self.agent, ("landed", "landed_unverified"))
        with urllib.request.urlopen(f"{self.url}/status", timeout=5) as resp:
            st = json.loads(resp.read())
        self.assertEqual(st["state"], "landed_unverified")


if __name__ == "__main__":
    unittest.main()
