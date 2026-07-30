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
    "rover_agent", os.path.join(ROOT, "rover", "rover_agent.py")
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
        self.delay = 0.0            # сколько «ехать» до цели: нужно, чтобы успеть в
        #                             маршрут вклиниться стопом и увидеть прогресс

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
        if self.delay:
            time.sleep(self.delay)
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


# Копия боевой раскладки из city/config.yaml. Именно копия: конфиг правят на
# площадке, и тесты агента от этого падать не должны.
BUILDINGS = [(1, 1), (4, 1), (1, 4), (4, 4), (2, 1), (1, 2), (3, 4)]
_KEEP = object()  # «поле по умолчанию», в отличие от явного field=None


def make_field():
    return ra.Field(size=(6, 6), cell=0.8, buildings=BUILDINGS)


def make_agent(*argv, start=(3, 3), field=_KEEP):
    args = ra.build_parser().parse_args(
        ["--cell", f"{start[0]},{start[1]}", "--drive-timeout", "3",
         "--poll", "0.02", "--watchdog", "0", *argv]
    )
    anchor = ra.Anchor(args.cell_size, args.map_x0, args.map_y0, args.map_yaw)
    backend = FakeBackend(anchor, start)
    agent = ra.Agent(args, backend, anchor,
                     make_field() if field is _KEEP else field)
    agent._snap = backend.read()  # без фонового опроса снимок пуст
    return agent, backend


def goal_cells(agent, backend):
    """Клетки, которые агент реально заказывал у Nav2 — в порядке заказа."""
    return [agent.anchor.m_to_cell(g["x"], g["y"]) for g in backend.goals]


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


class TestGoto(unittest.TestCase):
    """/goto: маршрут по клеткам в обход домов и езда по нему шаг за шагом.

    Диспетчеру эта ручка не нужна — он считает заряд по одному переезду и зовёт
    /drive. Она для рук оператора, поэтому и проверяется отдельно от /drive.
    """

    def test_route_goes_around_buildings(self):
        # Прямой путь из [3,3] в [0,0] уткнулся бы в дома [2,1] и [1,1]
        agent, backend = make_agent(start=(3, 3))
        agent.goto([0, 0])
        self.assertEqual(wait_state(agent, ("idle",)), "idle")
        self.assertEqual(agent.cell, (0, 0))
        for cell in goal_cells(agent, backend):
            self.assertNotIn(cell, BUILDINGS, f"поехал в дом {cell}")

    def test_goals_follow_the_path_cell_by_cell(self):
        """Nav2 получает каждую клетку маршрута отдельной целью, а не одну дальнюю."""
        agent, backend = make_agent(start=(3, 3))
        answer = agent.goto([3, 0])
        self.assertEqual(wait_state(agent, ("idle",)), "idle")
        path = [tuple(c) for c in answer["path"]]
        self.assertEqual(path[0], (3, 3))
        self.assertEqual(path[-1], (3, 0))
        self.assertEqual(answer["moves"], len(path) - 1)
        self.assertEqual(goal_cells(agent, backend), path[1:])

    def test_a_building_is_refused(self):
        agent, backend = make_agent(start=(3, 3))
        with self.assertRaises(ra.Refused) as caught:
            agent.goto([1, 2])
        self.assertIn("дом", str(caught.exception))
        self.assertEqual(len(backend.goals), 0)

    def test_a_cell_outside_the_field_is_refused(self):
        agent, _ = make_agent(start=(3, 3))
        for outside in ([6, 3], [-1, 0], [0, 9]):
            with self.assertRaises(ra.Refused) as caught:
                agent.goto(outside)
            self.assertIn("за полем", str(caught.exception))

    def test_no_route_is_refused_with_a_reason(self):
        """Цель отрезана занятыми клетками: отказ до старта, а не тупик на месте."""
        agent, backend = make_agent(start=(3, 3))
        with self.assertRaises(ra.Refused) as caught:
            agent.goto([0, 0], blocked=[(1, 0), (0, 1)])
        self.assertIn("маршрута нет", str(caught.exception))
        self.assertEqual(len(backend.goals), 0)

    def test_blocked_cells_are_avoided(self):
        agent, backend = make_agent(start=(3, 3))
        agent.goto([3, 0], blocked=[(3, 1)])
        self.assertEqual(wait_state(agent, ("idle",)), "idle")
        self.assertEqual(agent.cell, (3, 0))
        self.assertNotIn((3, 1), goal_cells(agent, backend))

    def test_own_cell_needs_no_lease(self):
        agent, backend = make_agent(start=(3, 3))
        answer = agent.goto([3, 3])
        self.assertEqual(answer["moves"], 0)
        self.assertEqual(wait_state(agent, ("idle",)), "idle")
        self.assertEqual(backend.leases, 0)

    def test_progress_is_visible_in_status(self):
        agent, backend = make_agent(start=(3, 3))
        backend.delay = 0.1  # иначе маршрут пройдёт быстрее первого же опроса
        agent.goto([3, 0])
        deadline = time.monotonic() + 3.0
        seen = None
        while time.monotonic() < deadline and seen is None:
            st = agent.status()
            if st["state"] == "moving" and "path_left" in st:
                seen = st
            time.sleep(0.01)
        self.assertIsNotNone(seen, "маршрут не показался в /status")
        self.assertEqual(seen["goal"], [3, 0])
        self.assertEqual(seen["path"][0], [3, 3])
        self.assertLessEqual(seen["path_left"], 3)
        wait_state(agent, ("idle",))
        # Маршрут кончился — полей маршрута в статусе больше нет.
        self.assertNotIn("path_left", agent.status())

    def test_stop_interrupts_the_route(self):
        agent, backend = make_agent(start=(3, 3))
        backend.delay = 0.15
        agent.goto([3, 0])
        time.sleep(0.2)
        agent.stop()
        self.assertEqual(wait_state(agent, ("stopped",)), "stopped")
        self.assertEqual(backend.hard_stops, 1)
        # Встали, не дойдя до цели, и клетка в статусе — реально пройденная.
        self.assertNotEqual(agent.cell, (3, 0))
        self.assertNotIn("path_left", agent.status())

    def test_a_failed_step_stops_the_route(self):
        agent, backend = make_agent("--retries", "0", start=(3, 3))
        backend.arrive = False
        agent.goto([3, 0])
        self.assertEqual(wait_state(agent, ("error",)), "error")
        self.assertEqual(agent.cell, (3, 3))  # ни одного шага не засчитано
        self.assertIn("маршрут прерван", agent.last_error)

    def test_route_refused_when_nav2_not_ready(self):
        agent, backend = make_agent(start=(3, 3))
        backend.nav_ready = False
        agent.goto([3, 0])
        self.assertEqual(wait_state(agent, ("idle",), 2.0), "idle")
        self.assertEqual(len(backend.goals), 0)
        self.assertIn("Nav2", agent.last_error)

    def test_second_route_while_moving_is_refused(self):
        agent, backend = make_agent(start=(3, 3))
        backend.delay = 0.15
        agent.goto([3, 0])
        time.sleep(0.05)
        with self.assertRaises(ra.Refused):
            agent.goto([0, 3])
        wait_idle(agent)

    def test_without_a_field_goto_is_refused_but_drive_works(self):
        """Конфиг не прочитался — агент обязан остаться рабочим для диспетчера."""
        agent, backend = make_agent(start=(3, 3), field=None)
        with self.assertRaises(ra.Refused) as caught:
            agent.goto([0, 0])
        self.assertIn("строить нечем", str(caught.exception))
        agent.drive([2, 3])
        self.assertEqual(wait_state(agent, ("idle",)), "idle")
        self.assertEqual(agent.cell, (2, 3))

    def test_resent_goto_does_not_drive_twice(self):
        agent, backend = make_agent(start=(3, 3))
        first = agent.once("cmd-9", lambda: agent.goto([3, 0]))
        second = agent.once("cmd-9", lambda: agent.goto([3, 0]))
        self.assertTrue(first["accepted"])
        self.assertTrue(second["deduplicated"])
        wait_state(agent, ("idle",))
        self.assertEqual(len(backend.goals), first["moves"])


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


class _OverHttp:
    """Агент за сокетом. Намеренно НЕ TestCase: тесты отсюда не собираются, иначе
    каждый наследник прогонял бы их заново."""

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


class TestOverHttp(_OverHttp, unittest.TestCase):
    """То же через сокет: command_id доезжает из тела, статус отвечает из кэша."""

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

    def test_goto_returns_the_route(self):
        """Далёкая клетка, отклонённая в /drive, в /goto принимается с маршрутом."""
        answer = self.post("/goto", {"cell": [0, 0]})
        self.assertTrue(answer["accepted"])
        self.assertEqual(answer["path"][0], [3, 3])
        self.assertEqual(answer["path"][-1], [0, 0])
        self.assertEqual(answer["moves"], len(answer["path"]) - 1)
        wait_state(self.agent, ("idle",))
        self.assertEqual(self.agent.cell, (0, 0))

    def test_goto_into_a_building_returns_403(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/goto", {"cell": [1, 2]})
        self.assertEqual(ctx.exception.code, 403)
        self.assertIn("дом", json.loads(ctx.exception.read())["error"])

    def test_goto_without_a_cell_returns_400(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/goto", {"blocked": []})
        self.assertEqual(ctx.exception.code, 400)


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


class TestFireTarget(unittest.TestCase):
    """Квадрат огня: ровер его ЗНАЕТ и отдаёт в статусе, но никуда по нему не едет."""

    def setUp(self):
        self.agent, self.backend = make_agent(start=(3, 3))

    def test_square_lands_in_status(self):
        answer = self.agent.set_fire(
            {"cell": [4, 2], "level": 3, "tower": [1, 3], "approach": [4, 3],
             "charge": [3, 3], "source": "drones", "at": 12.4}
        )
        self.assertTrue(answer["accepted"])
        fire = self.agent.status()["fire"]
        self.assertEqual(fire["cell"], [4, 2])
        self.assertEqual(fire["level"], 3)
        self.assertEqual(fire["tower"], [1, 3])
        self.assertEqual(fire["approach"], [4, 3])
        self.assertEqual(fire["via"], "fire")

    def test_dispatcher_time_never_mixes_with_our_own(self):
        """at приходит с часов диспетчера, since считается по своим — это разные машины."""
        self.agent.set_fire({"cell": [4, 2], "at": 12.4})
        fire = self.agent.status()["fire"]
        self.assertEqual(fire["at_dispatcher"], 12.4)
        self.assertIn("since", fire)
        self.assertLess(fire["since"], 5.0)  # свои часы, а не 12,4 с диспетчера

    def test_unknown_fields_survive(self):
        """Диспетчер может поумнеть раньше агента — незнакомое не выбрасывается."""
        self.agent.set_fire({"cell": [4, 2], "person": [4, 2], "window": "север"})
        extra = self.agent.status()["fire"]["extra"]
        self.assertEqual(extra, {"person": [4, 2], "window": "север"})

    def test_no_cell_is_a_key_error(self):
        """Handler превращает это в 400: тело без клетки — ошибка запроса."""
        with self.assertRaises(KeyError):
            self.agent.set_fire({"level": 2})

    def test_cell_outside_the_field_is_refused(self):
        with self.assertRaises(ra.Refused):
            self.agent.set_fire({"cell": [99, 99]})

    def test_a_burning_house_is_a_valid_square(self):
        """Проходимость НЕ проверяется: очаг горит в доме, дом не дорога."""
        self.agent.set_fire({"cell": [1, 2]})  # [1,2] — дом в make_field
        self.assertEqual(self.agent.status()["fire"]["cell"], [1, 2])

    def test_clear_forgets_it(self):
        self.agent.set_fire({"cell": [4, 2]})
        self.assertTrue(self.agent.clear_fire()["cleared"])
        self.assertNotIn("fire", self.agent.status())
        self.assertFalse(self.agent.clear_fire()["cleared"])  # повторно снимать нечего

    def test_accepted_while_moving(self):
        """409 на этом пути не бывает: диспетчер вправе уточнить квадрат на ходу."""
        self.backend.delay = 0.3
        self.agent.drive([3, 2])
        self.assertEqual(self.agent.state, "moving")
        self.assertTrue(self.agent.set_fire({"cell": [4, 2]})["accepted"])
        wait_state(self.agent, ("idle",))

    def test_the_square_does_not_change_where_the_rover_drives(self):
        """Главное свойство: знание не превращается в движение само.

        Ровер не отказывается ехать в горящую клетку и не объезжает её сам — запрет
        въезда держит план диспетчера (city/rules.py). Если это когда-нибудь изменят,
        тест должен упасть и заставить перечитать раздел «квадрат огня» в агенте.
        """
        self.agent.set_fire({"cell": [3, 2], "level": 2})
        self.agent.drive([3, 2])  # прямо в горящую клетку
        self.assertEqual(wait_state(self.agent, ("idle",)), "idle")
        self.assertEqual(self.agent.cell, (3, 2))

    def test_backup_channel_arrives_with_a_drive(self):
        self.agent.fire_from_drive({"cell": [3, 2], "fire": [4, 2], "fire_level": 2})
        fire = self.agent.status()["fire"]
        self.assertEqual(fire["cell"], [4, 2])
        self.assertEqual(fire["level"], 2)
        self.assertEqual(fire["via"], "drive")

    def test_backup_channel_fills_gaps_but_never_overwrites(self):
        """Резервный канал беднее основного: он дополняет, а не затирает."""
        self.agent.set_fire({"cell": [4, 2], "level": 3, "tower": [1, 3]})
        was_since = self.agent.status()["fire"]["since"]
        time.sleep(0.05)
        self.agent.fire_from_drive({"cell": [2, 3], "fire": [4, 2]})  # без level
        fire = self.agent.status()["fire"]
        self.assertEqual(fire["level"], 3)  # не потеряли
        self.assertEqual(fire["tower"], [1, 3])
        self.assertEqual(fire["via"], "fire")  # метку канала не понизили
        self.assertGreaterEqual(fire["since"], was_since)  # возраст не сбросили

    def test_backup_channel_with_another_cell_replaces(self):
        """Другая клетка — это новость: диспетчер передумал, берём его последнее слово."""
        self.agent.set_fire({"cell": [4, 2], "level": 3})
        self.agent.fire_from_drive({"cell": [2, 3], "fire": [1, 4], "fire_level": 1})
        fire = self.agent.status()["fire"]
        self.assertEqual(fire["cell"], [1, 4])
        self.assertEqual(fire["via"], "drive")

    def test_a_broken_square_never_breaks_the_drive(self):
        """Переезд важнее квадрата: испорченное поле fire не отменяет движение."""
        self.agent.fire_from_drive({"cell": [3, 2], "fire": "чепуха"})
        self.assertNotIn("fire", self.agent.status())
        self.assertIn("не разобран", self.agent.last_error)
        self.agent.drive([3, 2])
        self.assertEqual(wait_state(self.agent, ("idle",)), "idle")

    def test_no_field_means_no_bounds_check(self):
        """С --no-field границы не проверяются, и агент об этом честно предупреждает."""
        agent, _ = make_agent("--no-field", field=None)
        answer = agent.set_fire({"cell": [99, 99]})
        self.assertTrue(answer["accepted"])
        self.assertIn("границы не проверены", answer["note"])


class TestFireTargetOverHttp(_OverHttp, unittest.TestCase):
    """Тот же квадрат через сокет: коды ответов и дедуп по command_id."""

    def test_fire_round_trip(self):
        answer = self.post("/fire", {"cell": [4, 2], "level": 3})
        self.assertEqual(answer["fire"]["cell"], [4, 2])
        self.assertEqual(self.get("/status")["fire"]["level"], 3)
        read = self.get("/fire")
        self.assertTrue(read["known"])
        self.assertEqual(read["fire"]["cell"], [4, 2])

    def test_unknown_square_is_an_answer_not_a_404(self):
        read = self.get("/fire")
        self.assertFalse(read["known"])
        self.assertIsNone(read["fire"])

    def test_fire_without_cell_returns_400(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/fire", {"level": 2})
        self.assertEqual(ctx.exception.code, 400)

    def test_fire_outside_the_field_returns_403(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/fire", {"cell": [99, 99]})
        self.assertEqual(ctx.exception.code, 403)

    def test_resent_fire_is_not_applied_twice(self):
        body = {"cell": [4, 2], "command_id": "bbbb"}
        self.assertTrue(self.post("/fire", body)["accepted"])
        self.assertTrue(self.post("/fire", body)["deduplicated"])

    def test_backup_channel_survives_a_refused_drive(self):
        """403 на переезд не мешает квадрату дойти: он читается до проверок."""
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/drive", {"cell": [0, 0], "fire": [4, 2], "fire_level": 2})
        self.assertEqual(ctx.exception.code, 403)
        self.assertEqual(self.get("/status")["fire"]["cell"], [4, 2])

    def test_a_corrupt_body_answers_instead_of_dropping_the_connection(self):
        """Битый байт в теле — это 400, а не обрыв соединения.

        Раньше поток обработчика падал на UnicodeDecodeError, и клиент вместо ответа
        получал разрыв связи: на площадке так выглядел бы один искажённый пакет.
        """
        req = urllib.request.Request(
            f"{self.url}/fire", data=b'{"cell":\xff\xfe}',
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)
        self.assertEqual(self.get("/status")["role"], "rover")  # агент жив


if __name__ == "__main__":
    unittest.main()
