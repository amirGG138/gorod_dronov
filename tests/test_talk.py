"""Обвязка сообщений: что попадает в журнал, что нет и чего она не смеет ломать.

Три свойства здесь важнее остальных, и каждое проверяется отдельно:

* опрос /status не пишется НИКОГДА — иначе журнал утонет в опросах, а он материал
  техзащиты;
* обвязка не меняет объект: isinstance и поля живы, иначе Fleet.connect перестанет
  ждать борта при старте;
* сбой журнала не отменяет команду аппарату — визуализация не главнее ровера.
"""

import json
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from city.clock import SimClock
from city.log import Log
from city.robots import talk
from city.robots.base import RobotError
from city.robots.fake import FakeDrone, FakeRover
from city.robots.http_robot import HttpRobot


class _Harness(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = SimClock()
        self.log = Log(self.clock, run_dir=self.dir.name, echo=False)

    def tearDown(self):
        self.log.close()
        self.dir.cleanup()

    def events(self):
        self.log._fh.flush()
        with open(self.log.path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def msgs(self):
        return [e for e in self.events() if e["type"] == "MSG"]


class TestWhatGetsWritten(_Harness):
    def test_status_is_never_logged(self):
        rover = FakeRover(self.clock)
        talk.attach(rover, self.log)
        for _ in range(100):
            rover.status()
        self.assertEqual(self.msgs(), [])

    def test_a_command_is_logged_once_with_args_and_answer(self):
        rover = FakeRover(self.clock)
        talk.attach(rover, self.log)
        rover.led("blink")
        (msg,) = self.msgs()
        self.assertEqual(msg["verb"], "led")
        self.assertEqual(msg["dir"], "out")
        self.assertEqual(msg["frm"], talk.DISPATCHER)
        self.assertEqual(msg["to"], "rover")
        self.assertEqual(msg["args"], {"mode": "blink"})
        self.assertEqual(msg["answer"]["led"], "blink")
        self.assertTrue(msg["ok"])
        self.assertTrue(msg["reason"])  # правило city/log.py: причина по-русски

    def test_information_flows_from_the_drone(self):
        """Стрелка смотрит по потоку данных, а не по тому, кто сделал запрос.

        Кадр и вердикт запрашивает диспетчер, но содержимое летит ОТ борта. Иначе
        схема обмена утверждала бы, что диспетчер сам себе прислал детекцию.
        """
        drone = FakeDrone(self.clock, name="m1", fire_verdict={"found": True, "cell": [4, 2]})
        talk.attach(drone, self.log)
        drone.shot()
        drone.fire()
        shot, fire = self.msgs()
        self.assertEqual((shot["dir"], shot["frm"], shot["to"]), ("in", "m1", talk.DISPATCHER))
        self.assertEqual((fire["dir"], fire["frm"], fire["to"]), ("in", "m1", talk.DISPATCHER))

    def test_a_frame_is_logged_by_length_not_by_content(self):
        drone = FakeDrone(self.clock, name="m1")
        talk.attach(drone, self.log)
        drone.shot()
        (msg,) = self.msgs()
        self.assertGreater(msg["answer"]["bytes"], 0)
        self.assertNotIn("frame", json.dumps(msg))

    def test_a_refusal_is_logged_and_still_raised(self):
        rover = FakeRover(self.clock, cell=(3, 3))
        talk.attach(rover, self.log)
        with self.assertRaises(RobotError):
            rover.drive([0, 0])  # не соседняя клетка
        (msg,) = self.msgs()
        self.assertFalse(msg["ok"])
        self.assertIn("не соседняя", msg["error"])
        self.assertIn("не выполнил", msg["reason"])

    def test_the_backup_fire_channel_is_visible_in_the_args(self):
        rover = FakeRover(self.clock, cell=(3, 3), move_time=0.0)
        talk.attach(rover, self.log)
        rover.drive([3, 2], fire=[4, 2], fire_level=3)
        (msg,) = self.msgs()
        self.assertEqual(msg["args"], {"cell": [3, 2], "fire": [4, 2], "fire_level": 3})

    def test_an_internal_call_does_not_become_a_second_message(self):
        """FakeRover.drive внутри себя запоминает квадрат — но это не обмен.

        Раньше он звал свой же публичный tell_fire, и обвязанный вызов попадал в
        ленту: на дашборде выглядело так, будто диспетчер повторяет квадрат на каждом
        переезде.
        """
        rover = FakeRover(self.clock, cell=(3, 3), move_time=0.0)
        talk.attach(rover, self.log)
        rover.drive([3, 2], fire=[4, 2], fire_level=3)
        self.assertEqual([m["verb"] for m in self.msgs()], ["drive"])
        self.assertEqual(rover.fire["cell"], [4, 2])  # запомнил всё равно


class TestItChangesNothingElse(_Harness):
    def test_the_object_stays_the_same_object(self):
        robot = HttpRobot("http://127.0.0.1:1/", name="rover", role="rover")
        talk.attach(robot, self.log)
        # Fleet.connect по isinstance решает, ждать ли борт при старте, а по .url
        # печатает, куда стучались.
        self.assertIsInstance(robot, HttpRobot)
        self.assertEqual(robot.url, "http://127.0.0.1:1")
        self.assertEqual(robot.role, "rover")

    def test_only_the_verbs_the_robot_has_are_wrapped(self):
        rover = FakeRover(self.clock)
        wrapped = talk.attach(rover, self.log)
        self.assertIn("drive", wrapped)
        self.assertIn("tell_fire", wrapped)
        self.assertNotIn("takeoff", wrapped)  # ровер не взлетает, и это норма

    def test_attaching_twice_does_not_double_the_records(self):
        rover = FakeRover(self.clock)
        talk.attach(rover, self.log)
        self.assertEqual(talk.attach(rover, self.log), [])
        rover.led("on")
        self.assertEqual(len(self.msgs()), 1)

    def test_a_broken_log_does_not_cancel_the_command(self):
        """Журнал не вправе отменить команду: визуализация не главнее ровера."""

        class Broken:
            path = "—"

            def ev(self, *a, **kw):
                raise OSError("диск кончился")

        rover = FakeRover(self.clock, cell=(3, 3), move_time=0.0)
        talk.attach(rover, Broken())
        self.assertTrue(rover.led("blink")["accepted"])
        rover.drive([3, 2])
        self.assertEqual(rover.cell, (3, 2))


class TestParallelWrites(_Harness):
    def test_lines_do_not_get_mixed_up(self):
        """Аварийная остановка рассылает «стоп» всем аппаратам параллельно.

        Без замка в Log.ev две строки JSONL склеиваются — и ломается ровно тот файл,
        который сдают как лог решений.
        """
        robots = [FakeRover(self.clock, cell=(3, 3)) for _ in range(6)]
        for i, r in enumerate(robots):
            r.name = f"rover{i}"
            talk.attach(r, self.log)

        def hammer(robot):
            for _ in range(40):
                robot.led("blink")
                robot.stop()

        threads = [threading.Thread(target=hammer, args=(r,)) for r in robots]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # Главное: каждая строка — целый JSON. events() упал бы на склейке.
        self.assertEqual(len(self.msgs()), 6 * 40 * 2)


if __name__ == "__main__":
    unittest.main()
