"""Сеть по-настоящему: клиент и мок-сервер разговаривают через сокет.

Смысл этих проверок — не «работает ли urllib», а «одинаково ли ведут себя аппарат
в памяти и аппарат на другом конце провода». Если контракт разъедется, на площадке
это вылезет полётом, а не сообщением.
"""

import json
import time
import unittest
import urllib.request

from city.robots.base import RobotError
from city.robots.http_robot import HttpRobot, wait_online
from city.robots.mock_server import serve


def post(url: str, path: str, body: dict) -> dict:
    """POST мимо HttpRobot: он ставит новый command_id на каждый вызов, а нам нужен тот же."""
    req = urllib.request.Request(
        f"{url}{path}", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def wait_until(robot, check, timeout=5.0):
    """Дождаться состояния борта — ровно так же, как это делает диспетчер.

    Команда принимается мгновенно, а исполняется потом: у настоящего дрона иначе не
    бывает, поэтому и в проверках мы ждём факта, а не верим ответу на команду.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = robot.status()
        if check(st):
            return st
        time.sleep(0.05)
    raise AssertionError(f"не дождались нужного состояния, последнее: {robot.status()}")


class HttpCase(unittest.TestCase):
    role = "rover"
    cell = (3, 3)

    def setUp(self):
        self.server, self.mock = serve(self.role, 0, self.cell, move_time=0.01, quiet=True)
        port = self.server.server_address[1]
        self.robot = HttpRobot(f"http://127.0.0.1:{port}", name=self.role)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()


class TestRover(HttpCase):
    def test_status_matches_the_mock(self):
        st = self.robot.status()
        self.assertTrue(st["ok"])
        self.assertEqual(st["role"], "rover")
        self.assertEqual(st["cell"], [3, 3])
        self.assertIn("since_move", st)

    def test_drive_to_neighbour(self):
        self.assertTrue(self.robot.drive([3, 2])["accepted"])
        wait_until(self.robot, lambda st: st["cell"] == [3, 2] and not st["busy"])

    def test_second_command_while_driving_is_refused(self):
        slow, mock = serve("rover", 0, (3, 3), move_time=0.5, quiet=True)
        try:
            robot = HttpRobot(f"http://127.0.0.1:{slow.server_address[1]}")
            robot.drive([3, 2])
            with self.assertRaises(RobotError) as ctx:
                robot.drive([3, 4])  # соседняя, но ровер ещё в пути
            self.assertRegex(str(ctx.exception), "занят|уже едет")
        finally:
            slow.shutdown()
            slow.server_close()

    def test_drive_far_is_refused_with_a_readable_reason(self):
        with self.assertRaises(RobotError) as ctx:
            self.robot.drive([0, 0])
        self.assertIn("не соседняя клетка", str(ctx.exception))

    def test_led(self):
        self.robot.led("blink")
        self.assertEqual(self.robot.status()["led"], "blink")

    def test_bad_led_mode_is_refused(self):
        with self.assertRaises(RobotError):
            self.robot.led("rainbow")

    def test_since_move_grows_while_standing(self):
        self.robot.drive([3, 2])
        wait_until(self.robot, lambda st: not st["busy"])
        first = self.robot.status()["since_move"]
        time.sleep(0.15)
        self.assertGreater(self.robot.status()["since_move"], first)

    def test_unsupported_command_for_this_role(self):
        with self.assertRaises(RobotError):
            self.robot.takeoff(1.5)

    def test_stop(self):
        self.assertTrue(self.robot.stop()["accepted"])

    def test_resent_command_is_answered_not_repeated(self):
        """Теряется чаще ответ, а не команда: повтор с тем же id — не второй заезд.

        Без дедупликации повтор либо уезжает второй раз, либо получает 409 «занят»
        на свою же собственную команду — и диспетчер считает попытку сорванной.
        """
        slow, mock = serve("rover", 0, (3, 3), move_time=0.5, quiet=True)
        try:
            url = f"http://127.0.0.1:{slow.server_address[1]}"
            body = {"cell": [3, 2], "command_id": "same-id"}
            self.assertTrue(post(url, "/drive", body)["accepted"])
            self.assertTrue(post(url, "/drive", body)["deduplicated"])
            robot = HttpRobot(url)
            wait_until(robot, lambda st: not st["busy"], timeout=5)
            self.assertEqual(robot.status()["cell"], [3, 2])
        finally:
            slow.shutdown()
            slow.server_close()

    def test_command_without_id_still_works(self):
        """curl с руки никакого id не шлёт — контракт обязан это пережить."""
        url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.assertTrue(post(url, "/drive", {"cell": [3, 2]})["accepted"])


class TestDrone(HttpCase):
    role = "drone"
    cell = (1, 1)

    def test_takeoff_shot_land(self):
        self.robot.takeoff(1.5)
        wait_until(self.robot, lambda st: st["state"] == "hover", timeout=10)
        frame = self.robot.shot()
        self.assertTrue(frame.startswith(b"\xff\xd8"), "кадр должен быть JPEG")
        self.robot.land()
        wait_until(self.robot, lambda st: st["state"] == "landed", timeout=10)

    def test_goto_before_takeoff_is_refused(self):
        with self.assertRaises(RobotError):
            self.robot.goto([2, 2], 1.5)


class TestNoConnection(unittest.TestCase):
    def test_dead_address_gives_a_clear_error(self):
        robot = HttpRobot("http://127.0.0.1:9", name="потеряшка")
        with self.assertRaises(RobotError) as ctx:
            robot.status()
        self.assertIn("нет связи", str(ctx.exception))

    def test_wait_online_gives_up_and_says_so(self):
        robot = HttpRobot("http://127.0.0.1:9", name="потеряшка")
        with self.assertRaises(RobotError) as ctx:
            wait_online(robot, seconds=0.5)
        self.assertIn("не ответил", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
