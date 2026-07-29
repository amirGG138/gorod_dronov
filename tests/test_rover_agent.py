"""Агент ровера: соседство клеток, прибытие по факт-позе, лиз, лента, сторож.

Ровера здесь нет: вместо родного API подставляется FakeBackend, у которого поза,
готовность Nav2 и исход заезда задаются тестом. Проверяется ровно то, что можно
проверить без ровера, — логика перевода нашего контракта в команды ровера. Реально
ли доедет Nav2 и совпадёт ли привязка сетки с картой, проверяется на площадке.
"""

import importlib.util
import json
import os
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "rover_agent", os.path.join(ROOT, "onboard", "rover_agent.py")
)
ra = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ra)

ra.say = lambda text: None  # строки борта в тесте — шум


class FakeBackend:
    """Родной API ровера-заглушка: тест задаёт позу, готовность Nav2 и исход заезда."""

    def __init__(self, anchor, start_cell) -> None:
        self.anchor = anchor
        self.nav_ready = True
        self.frame_id = "map"
        self.battery = 12.4
        self.link = True
        self.pose = anchor.cell_to_m(start_cell) + (0.0,)
        self.arrive = True          # доезжает ли до цели (телепортом в позу цели)
        self.stuck_state = "aborted"  # что отдаёт nav_status, когда не доехал
        self.goals: list[dict] = []
        self.leases = 0
        self.cancels = 0
        self.hard_stops = 0
        self.leds: list[dict] = []
        self.led_fails = False

    def read(self, with_battery=True):
        return {"link": self.link, "nav_ready": self.nav_ready, "pose": self.pose,
                "frame_id": self.frame_id,
                "battery": self.battery if with_battery else None}

    def goal(self, x, y, yaw_deg, request_id):
        if not self.nav_ready:
            raise ra.RoverRefused("Nav2 не готов")
        if self.frame_id and self.frame_id != "map":
            raise ra.RoverRefused(f"frame {self.frame_id}")
        self.leases += 1
        self.goals.append({"x": x, "y": y, "yaw": yaw_deg, "id": request_id})
        if self.arrive:
            self.pose = (x, y, yaw_deg)  # доехал: подтверждение по позе пройдёт

    def nav_status(self):
        return {"state": "succeeded" if self.arrive else self.stuck_state}

    def cancel(self, request_id):
        self.cancels += 1

    def hard_stop(self):
        self.hard_stops += 1

    def led(self, enabled, effect, brightness, speed, primary, secondary):
        if self.led_fails:
            raise ra.RoverLinkError("лента недоступна")
        self.leds.append({"enabled": enabled, "effect": effect, "color": primary})


def make_agent(*argv, start=(3, 3)):
    args = ra.build_parser().parse_args(
        ["--cell", f"{start[0]},{start[1]}", "--drive-timeout", "3",
         "--poll", "0.02", "--watchdog", "0", *argv]
    )
    anchor = ra.Anchor(args.cell_size, args.map_x0, args.map_y0, args.map_yaw)
    backend = FakeBackend(anchor, start)
    agent = ra.Agent(args, backend, anchor)
    agent._snap = backend.read()  # без фонового опроса снимок пуст
    return agent, backend


def wait_state(agent, states, seconds=4.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if agent.state in states and not agent._busy:
            return agent.state
        time.sleep(0.02)
    return agent.state


def wait_idle(agent, seconds=4.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not agent._busy:
            return True
        time.sleep(0.02)
    return False


class TestAnchor(unittest.TestCase):
    """Клетка <-> метры карты: перевод обратим, поворот учитывается."""

    def test_round_trip_without_rotation(self):
        a = ra.Anchor(0.8, 1.0, 2.0, 0.0)
        self.assertEqual(a.m_to_cell(*a.cell_to_m((4, 1))), (4, 1))

    def test_rotation_is_applied(self):
        a = ra.Anchor(0.8, 0.0, 0.0, 0.0)
        b = ra.Anchor(0.8, 0.0, 0.0, 1.5707963)  # +90°
        x0, y0 = a.cell_to_m((1, 0))
        x1, y1 = b.cell_to_m((1, 0))
        self.assertAlmostEqual(x0, 0.8, places=6)
        self.assertAlmostEqual(y0, 0.0, places=6)
        self.assertAlmostEqual(x1, 0.0, places=6)   # поворот увёл вперёд в бок
        self.assertAlmostEqual(y1, 0.8, places=6)


class TestDrive(unittest.TestCase):
    def test_drive_to_neighbour_reaches_and_counts_move(self):
        agent, backend = make_agent(start=(3, 3))
        agent.drive([2, 3])
        self.assertEqual(wait_state(agent, ("idle",)), "idle")
        self.assertEqual(list(agent.cell), [2, 3])
        self.assertEqual(len(backend.goals), 1)
        # since_move обнулился: переезд — это движение.
        self.assertLess(agent.status()["since_move"], 1.0)

    def test_non_adjacent_is_refused_immediately(self):
        agent, _ = make_agent(start=(3, 3))
        with self.assertRaises(ra.Refused):
            agent.drive([1, 1])

    def test_second_drive_while_moving_is_refused(self):
        agent, backend = make_agent(start=(3, 3))
        backend.arrive, backend.stuck_state = False, "navigating"  # заезд ещё идёт
        agent.drive([2, 3])
        time.sleep(0.05)
        with self.assertRaises(ra.Refused):
            agent.drive([3, 3])
        agent.stop()

    def test_same_cell_needs_no_lease(self):
        """Уже в клетке — засчитываем как доехал, ровер не трогаем."""
        agent, backend = make_agent(start=(3, 3))
        agent.drive([3, 3])
        self.assertEqual(wait_state(agent, ("idle",)), "idle")
        self.assertEqual(backend.leases, 0)

    def test_goal_is_sent_in_map_metres(self):
        agent, backend = make_agent("--map-x0", "1.0", "--cell-size", "0.8", start=(3, 3))
        agent.drive([2, 3])
        wait_state(agent, ("idle",))
        goal = backend.goals[0]
        self.assertAlmostEqual(goal["x"], 1.0 + 2 * 0.8, places=6)
        self.assertAlmostEqual(goal["y"], 3 * 0.8, places=6)

    def test_not_arriving_ends_in_error_after_retries(self):
        agent, backend = make_agent("--retries", "1", start=(3, 3))
        backend.arrive = False
        agent.drive([2, 3])
        self.assertEqual(wait_state(agent, ("error",)), "error")
        self.assertEqual(list(agent.cell), [3, 3])  # клетку не сдвинули
        self.assertEqual(len(backend.goals), 2)     # заезд + один повтор

    def test_drive_refused_when_nav2_not_ready(self):
        """Nav2 не поднят — отказ до старта: ровер стоит, а не «едет» и не «error»."""
        agent, backend = make_agent(start=(3, 3))
        backend.nav_ready = False
        agent.drive([2, 3])
        self.assertEqual(wait_state(agent, ("idle",), 2.0), "idle")
        self.assertEqual(len(backend.goals), 0)
        self.assertIn("Nav2", agent.last_error)

    def test_drive_refused_when_pose_not_in_map(self):
        agent, backend = make_agent(start=(3, 3))
        backend.frame_id = "odom"
        agent.drive([2, 3])
        self.assertEqual(wait_state(agent, ("idle",), 2.0), "idle")
        self.assertEqual(len(backend.goals), 0)


class TestDedup(unittest.TestCase):
    def test_resent_drive_does_not_lease_twice(self):
        agent, backend = make_agent(start=(3, 3))
        first = agent.once("cmd-1", lambda: agent.drive([2, 3]))
        second = agent.once("cmd-1", lambda: agent.drive([2, 3]))
        self.assertTrue(first["accepted"])
        self.assertTrue(second["deduplicated"])
        wait_state(agent, ("idle",))
        self.assertEqual(len(backend.goals), 1)


class TestLed(unittest.TestCase):
    def test_blink_maps_to_blink_effect(self):
        agent, backend = make_agent()
        res = agent.led("blink", "#FF0000")
        self.assertTrue(res["accepted"])
        self.assertEqual(agent.status()["led"], "blink")
        self.assertEqual(backend.leds[-1]["effect"], "blink")
        self.assertTrue(backend.leds[-1]["enabled"])

    def test_off_disables_the_strip(self):
        agent, backend = make_agent()
        agent.led("off")
        self.assertFalse(backend.leds[-1]["enabled"])

    def test_unknown_mode_is_refused(self):
        agent, _ = make_agent()
        with self.assertRaises(ra.Refused):
            agent.led("strobe")

    def test_led_failure_is_reported_not_raised(self):
        """Отказ ленты не валит агент, но и не выдаётся за успех."""
        agent, backend = make_agent()
        backend.led_fails = True
        res = agent.led("blink")
        self.assertFalse(res["accepted"])
        self.assertIn("error", res)
        self.assertEqual(agent.led_mode, "off")  # режим не переписан на несделанное


class TestStop(unittest.TestCase):
    def test_stop_preempts_a_drive(self):
        agent, backend = make_agent(start=(3, 3))
        backend.arrive, backend.stuck_state = False, "navigating"
        agent.drive([2, 3])
        time.sleep(0.05)
        agent.stop()
        self.assertEqual(wait_state(agent, ("stopped",)), "stopped")
        self.assertGreaterEqual(backend.hard_stops, 1)

    def test_watchdog_stops_when_laptop_goes_quiet(self):
        agent, backend = make_agent("--watchdog", "0.3", start=(3, 3))
        backend.arrive, backend.stuck_state = False, "navigating"
        threading.Thread(target=agent.watchdog, daemon=True).start()
        agent.drive([2, 3])
        self.assertEqual(wait_state(agent, ("stopped",), 3.0), "stopped")


class TestOverHttp(unittest.TestCase):
    """То же через сокет: command_id доезжает из тела, статус отвечает из кэша."""

    def setUp(self):
        self.agent, self.backend = make_agent(start=(3, 3))
        handler = type("Bound", (ra.Handler,), {"agent": self.agent})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def post(self, path, body):
        req = urllib.request.Request(
            f"{self.url}{path}", data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def get(self, path):
        with urllib.request.urlopen(f"{self.url}{path}", timeout=5) as resp:
            return json.loads(resp.read())

    def test_status_reports_role_and_led(self):
        st = self.get("/status")
        self.assertEqual(st["role"], "rover")
        self.assertIn("led", st)
        self.assertIn("since_move", st)

    def test_resent_drive_over_http_leases_once(self):
        body = {"cell": [2, 3], "command_id": "aaaa"}
        self.assertTrue(self.post("/drive", body)["accepted"])
        self.assertTrue(self.post("/drive", body)["deduplicated"])
        wait_state(self.agent, ("idle",))
        self.assertEqual(len(self.backend.goals), 1)

    def test_non_adjacent_drive_returns_403(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/drive", {"cell": [0, 0]})
        self.assertEqual(ctx.exception.code, 403)


class TestDryBackend(unittest.TestCase):
    """--dry: файл запускается где угодно без ровера и «ездит» мгновенно."""

    def test_dry_drive_moves_between_cells(self):
        args = ra.build_parser().parse_args(["--dry", "--cell", "3,3", "--watchdog", "0"])
        anchor = ra.Anchor(args.cell_size, args.map_x0, args.map_y0, args.map_yaw)
        agent = ra.Agent(args, ra.DryBackend(anchor, (3, 3)), anchor)
        agent._snap = agent.backend.read()
        agent.drive([2, 3])
        self.assertEqual(wait_state(agent, ("idle",)), "idle")
        self.assertEqual(list(agent.cell), [2, 3])


if __name__ == "__main__":
    unittest.main()
