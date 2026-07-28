"""Бортовой агент дрона: вытеснение команд, повторы и честность про посадку.

Железа здесь нет: вместо sverk_interfaces подставляется заглушка Board, считающая
вызовы navigate и land. Проверяется ровно то, что можно проверить без полёта, —
кто пишет состояние и что борт про это состояние утверждает. Останется ли живой
navigate управляемым, когда поверх него приходит land, проверяется только полётом.
"""

import importlib.util
import json
import math
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
        self.calls: list[dict] = []     # аргументы каждого navigate: по ним видно курс

    def navigate(self, **kw):
        self.navigates += 1
        self.calls.append(kw)
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


class Camera:
    """Камера-заглушка: отдаёт «кадр», по которому опознавание подставит нужный угол."""

    def __init__(self, angle=None) -> None:
        self.angle = angle          # что «увидит» marker_angle: радианы или None
        self.pictures = 0

    def take_picture(self, timeout=2.0):
        self.pictures += 1
        return types.SimpleNamespace(ndim=3, size=1)


class Board:
    def __init__(self) -> None:
        self.control = Control()
        self.image = Camera()


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


def wait_idle(agent, seconds=5.0) -> bool:
    """Дождаться конца команды. По состоянию это не видно: в полёте борт «висит»."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not agent._busy:
            return True
        time.sleep(0.02)
    return False


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


class TestYawArithmetic(unittest.TestCase):
    """Арифметика удержания курса — без агента и без железа."""

    def test_error_is_measured_the_short_way_around(self):
        """179° вправо и 181° влево — это −179°, а не +181°: круг замыкается."""
        error = da.turn_error(math.radians(-179.0), math.radians(179.0), 360.0)
        self.assertAlmostEqual(math.degrees(error), 2.0, places=6)

    def test_implausible_turn_is_rejected_not_zeroed(self):
        """Увод больше предела — негодный замер: об этом надо сказать, а не смолчать."""
        self.assertIsNone(da.turn_error(math.radians(90.0), 0.0, 45.0))
        self.assertIsNotNone(da.turn_error(math.radians(40.0), 0.0, 45.0))

    def test_correction_is_opposite_to_the_drift(self):
        """Отвернуло против часовой — доворачиваем по часовой, иначе увод удвоится."""
        self.assertLess(da.yaw_fix(math.radians(10.0), 3.0, 15.0), 0.0)
        self.assertGreater(da.yaw_fix(math.radians(-10.0), 3.0, 15.0), 0.0)

    def test_small_drift_is_left_alone(self):
        """Шум опознания метки не повод дёргать дрон."""
        self.assertEqual(da.yaw_fix(math.radians(2.0), 3.0, 15.0), 0.0)

    def test_big_drift_is_worked_off_in_steps(self):
        turn = da.yaw_fix(math.radians(40.0), 3.0, 15.0)
        self.assertAlmostEqual(math.degrees(turn), -15.0, places=6)

    def test_vector_is_rotated_into_the_body_axes(self):
        """Дрон отвернуло на 90° — «вперёд по полю» для него теперь «вправо»."""
        forward, left = da.to_body(1.0, 0.0, math.radians(90.0), 3.0)
        self.assertAlmostEqual(forward, 0.0, places=6)
        self.assertAlmostEqual(left, -1.0, places=6)

    def test_vector_is_untouched_inside_the_dead_zone(self):
        self.assertEqual(da.to_body(1.0, 2.0, math.radians(1.0), 3.0), (1.0, 2.0))


def marker_frame(deg: float, mid: int = 50, size: int = 200):
    """Кадр 640x480 с меткой mid, повёрнутой на deg градусов ПРОТИВ часовой.

    Против часовой — потому что так считает cv2.getRotationMatrix2D; в осях кадра
    (y вниз) тому же повороту соответствует отрицательный угол ребра, и именно его
    отдаёт marker_angle.
    """
    import cv2
    import numpy as np

    img = np.full((480, 640), 255, np.uint8)
    tag = cv2.aruco.generateImageMarker(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_1000), mid, size
    )
    top, left = (480 - size) // 2, (640 - size) // 2
    img[top:top + size, left:left + size] = tag
    turn = cv2.getRotationMatrix2D((320.0, 240.0), deg, 1.0)
    img = cv2.warpAffine(img, turn, (640, 480), borderValue=255)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


try:
    import cv2 as _cv2

    HAVE_CV2 = hasattr(_cv2, "aruco")
except ImportError:
    HAVE_CV2 = False


@unittest.skipUnless(HAVE_CV2, "нужен cv2 с модулем aruco")
class TestMarkerAngle(unittest.TestCase):
    """Опознание поворота метки на нарисованных кадрах: на борту это единственный курс."""

    def test_straight_marker_reads_as_zero(self):
        self.assertAlmostEqual(math.degrees(da.marker_angle(marker_frame(0.0))), 0.0, places=1)

    def test_turned_marker_reads_the_turn(self):
        for deg in (15.0, -20.0, 90.0):
            with self.subTest(deg=deg):
                angle = math.degrees(da.marker_angle(marker_frame(deg)))
                self.assertAlmostEqual(angle, -deg, delta=1.0)

    def test_empty_frame_has_no_angle(self):
        import numpy as np

        self.assertIsNone(da.marker_angle(np.full((480, 640, 3), 255, np.uint8)))

    def test_our_field_markers_are_all_recognised(self):
        """id 60 и 62 в словарь 4X4_50 не влезают — на нём курс держался бы не всегда."""
        for mid in (50, 60, 62, 7):
            with self.subTest(marker=mid):
                self.assertIsNotNone(da.marker_angle(marker_frame(0.0, mid)))


class TestYawHold(unittest.TestCase):
    """Курс держится по метке: эталон с взлёта, поправка — в ближайшую же команду."""

    def setUp(self):
        self.seen = [math.radians(0.0)]         # что «видит» камера в этом кадре
        self._real_angle = da.marker_angle
        da.marker_angle = lambda frame: self.seen[0]

    def tearDown(self):
        da.marker_angle = self._real_angle

    def flying(self, *argv):
        agent = make_agent("--frame", "body", "--allow-scan", "--hop-wait", "0.1", *argv)
        agent.camera_ok = True
        agent.takeoff(1.5)
        wait_state(agent, ("hover",))
        return agent

    def test_takeoff_remembers_the_heading(self):
        self.seen[0] = math.radians(20.0)
        agent = self.flying()
        self.assertAlmostEqual(math.degrees(agent._yaw_ref), 20.0, places=6)
        self.assertEqual(agent.status()["yaw_ref"], 20)

    def test_hop_carries_the_correction(self):
        agent = self.flying()
        self.seen[0] = math.radians(10.0)       # за время висения отвернуло
        agent.look([-1.0, -1.2], 1.5)
        wait_idle(agent)
        turn = agent.drone.control.calls[-1]["yaw"]
        self.assertAlmostEqual(math.degrees(turn), -10.0, places=6)
        self.assertEqual(agent.status()["yaw_drift"], 10)

    def test_hop_without_a_marker_still_flies(self):
        """Метку потеряли — летим без поправки, а не отказываемся лететь."""
        agent = self.flying()
        self.seen[0] = None
        agent.look([-1.0, -1.2], 1.5)
        self.assertTrue(wait_idle(agent))
        self.assertEqual(agent.state, "hover")
        self.assertEqual(agent.drone.control.calls[-1]["yaw"], 0.0)

    def test_map_frame_is_left_to_the_onboard_localisation(self):
        """С aruco_map yaw абсолютный: свой доворот там крутил бы дрон дважды."""
        agent = make_agent("--frame", "aruco_map", "--allow-scan", "--hop-wait", "0.1")
        agent.camera_ok = True
        agent.takeoff(1.5)
        wait_state(agent, ("hover",))
        self.assertFalse(agent.yaw_hold)
        self.assertIsNone(agent._yaw_ref)
        self.assertNotIn("yaw_ref", agent.status())
        agent.look([-1.0, -1.2], 1.5)
        wait_idle(agent)
        self.assertEqual(agent.drone.control.calls[-1]["yaw"], 0.0)

    def test_landing_forgets_the_heading(self):
        """Эталон живёт один полёт: следующий взлёт снимет свой."""
        agent = self.flying()
        agent.land()
        wait_state(agent, ("landed", "landed_unverified"))
        self.assertIsNone(agent._yaw_ref)

    def test_switched_off_by_the_flag(self):
        agent = self.flying("--no-yaw-hold")
        self.assertFalse(agent.yaw_hold)
        self.assertIsNone(agent._yaw_ref)
        self.seen[0] = math.radians(10.0)
        agent.look([-1.0, -1.2], 1.5)
        wait_idle(agent)
        self.assertEqual(agent.drone.control.calls[-1]["yaw"], 0.0)

    def test_implausible_marker_does_not_turn_the_drone(self):
        """Сбой опознания метки не должен разворачивать дрон на десятки градусов."""
        agent = self.flying()
        self.seen[0] = math.radians(120.0)
        agent.look([-1.0, -1.2], 1.5)
        wait_idle(agent)
        self.assertEqual(agent.drone.control.calls[-1]["yaw"], 0.0)


class TestYawKeeper(unittest.TestCase):
    """Доворот на висении: между командами монитор висит минутами, увод копится."""

    def setUp(self):
        self.seen = [0.0]
        self._real_angle = da.marker_angle
        da.marker_angle = lambda frame: self.seen[0]

    def tearDown(self):
        da.marker_angle = self._real_angle

    def hovering(self, *argv):
        agent = make_agent("--frame", "body", "--yaw-period", "0.2", "--yaw-wait", "0.1",
                           *argv)
        agent.camera_ok = True
        agent.takeoff(1.5)
        wait_state(agent, ("hover",))
        return agent

    def test_drift_is_worked_off_while_hovering(self):
        agent = self.hovering()
        self.seen[0] = math.radians(10.0)       # висел и потихоньку отвернулся
        before = agent.drone.control.navigates
        threading.Thread(target=agent.keeper, daemon=True).start()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and agent.drone.control.navigates == before:
            time.sleep(0.05)
        self.assertGreater(agent.drone.control.navigates, before)
        last = agent.drone.control.calls[-1]
        self.assertAlmostEqual(math.degrees(last["yaw"]), -10.0, places=6)
        # Доворот — это только курс: дрон стоит там же, где стоял.
        self.assertEqual((last["x"], last["y"], last["z"]), (0.0, 0.0, 0.0))

    def test_a_drone_on_the_ground_is_not_turned(self):
        """Севший дрон крутить нельзя ни при каких обстоятельствах."""
        agent = self.hovering()
        agent.land()
        wait_state(agent, ("landed", "landed_unverified"))
        before = agent.drone.control.navigates
        threading.Thread(target=agent.keeper, daemon=True).start()
        time.sleep(1.0)
        self.assertEqual(agent.drone.control.navigates, before)


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
