"""Пульт: что оператор видит в ответ на «статус» и «огонь».

Проверяем не сеть и не борт, а пересказ: пульт — это единственное место, где человек
на площадке узнаёт, что происходит с дроном. Молчание про потерянную метку или
бодрое «очаг найден» там, где борт ничего не нашёл, стоят дороже любой другой ошибки
в этом файле.
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from city import pult
from city.robots.base import RobotError


class FakeDrone:
    """Борт-заглушка: отвечает тем, что ему положили, или отказывает."""

    def __init__(self, status=None, fire=None, error: str = "") -> None:
        self._status = status or {"state": "hover", "alt": 2.0, "cell": [1, 1], "camera": True}
        self._fire = fire
        self.error = error
        self.trims: list[tuple[float, float]] = []
        self.asked = 0  # сколько раз у борта спросили про огонь

    def status(self):
        return self._status

    def fire(self):
        self.asked += 1
        if self.error:
            raise RobotError(self.error)
        return self._fire or {"found": False, "note": "очага в кадре нет"}

    def trim(self, fwd, left):
        self.trims.append((fwd, left))
        return {"accepted": True, "aim": [fwd, left]}


class Spoken(unittest.TestCase):
    """Общая обвязка: перехватываем строки, которые пульт говорит оператору."""

    def setUp(self):
        self.lines: list[str] = []
        self._say = pult.say
        pult.say = self.lines.append

    def tearDown(self):
        pult.say = self._say

    def said(self, *words) -> bool:
        return any(all(word in line for word in words) for line in self.lines)


class FireTest(Spoken):
    def test_a_fire_is_retold_with_the_number_of_trips(self):
        """Число огоньков — это число поездок за водой, и сказать надо именно так."""
        drone = FakeDrone(fire={
            "found": True, "cell": [2, 2], "count": 3, "count_source": "blobs",
            "spread_m": 0.21, "anchor": "marker", "note": "",
        })
        pult.do_fire(drone)
        self.assertTrue(self.said("ОЧАГ", "[2, 2]", "3"))
        self.assertTrue(self.said("поездок за водой"))

    def test_an_empty_answer_is_not_dressed_up(self):
        drone = FakeDrone(fire={"found": False, "note": "очага в кадре нет"})
        pult.do_fire(drone)
        self.assertTrue(self.said("не вижу", "очага в кадре нет"))
        self.assertFalse(self.said("ОЧАГ в клетке"))

    def test_a_caveat_is_passed_on(self):
        drone = FakeDrone(fire={
            "found": True, "cell": [2, 2], "count": 2, "count_source": "area",
            "spread_m": 0.1, "anchor": "marker", "note": "кучка у края кадра",
        })
        pult.do_fire(drone)
        self.assertTrue(self.said("оговорка", "у края кадра"))

    def test_a_silent_board_is_reported_not_swallowed(self):
        pult.do_fire(FakeDrone(error="нет связи"))
        self.assertTrue(self.said("не ответил про огонь", "нет связи"))


class StatusTest(Spoken):
    def test_holding_the_marker_is_shown_with_the_miss_and_the_height(self):
        drone = FakeDrone({
            "state": "hover", "alt": 2.0, "cell": [1, 1], "camera": True,
            "marker": 62, "alt_seen": 1.94, "miss": 0.06, "side_px": 129, "blind": 0,
        })
        pult.show_status(drone)
        self.assertTrue(self.said("держусь за метку 62", "0.06", "1.94"))

    def test_a_lost_marker_is_said_out_loud(self):
        """Молча переставший держаться дрон хуже, чем не державшийся никогда."""
        drone = FakeDrone({
            "state": "hover", "alt": 2.0, "cell": [1, 1], "camera": True,
            "marker": 62, "alt_seen": None, "miss": None, "side_px": None,
            "blind": 30, "marker_lost": True,
        })
        pult.show_status(drone)
        self.assertTrue(self.said("ПОТЕРЯЛ"))

    def test_the_last_fire_answer_is_repeated_in_the_status(self):
        drone = FakeDrone({
            "state": "hover", "alt": 2.0, "cell": [1, 1], "camera": True,
            "fire": {"found": True, "cell": [3, 2], "count": 1},
        })
        pult.show_status(drone)
        self.assertTrue(self.said("последний ответ про огонь", "[3, 2]"))

    def test_a_board_that_holds_nothing_says_nothing_extra(self):
        pult.show_status(FakeDrone())
        self.assertFalse(self.said("держусь за метку"))
        self.assertFalse(self.said("последний ответ про огонь"))

    def test_a_shifted_aim_is_shown(self):
        """Иначе «промах 0.00» у висящего мимо метки дрона выглядит как исправность."""
        drone = FakeDrone({
            "state": "hover", "alt": 2.0, "cell": [1, 1], "camera": True,
            "marker": 62, "alt_seen": 2.0, "miss": 0.0, "side_px": 129, "blind": 0,
            "aim": [0.1, -0.08],
        })
        pult.show_status(drone)
        self.assertTrue(self.said("прицел сдвинут", "+10", "-8"))

    def test_an_unshifted_aim_is_not_mentioned(self):
        drone = FakeDrone({
            "state": "hover", "alt": 2.0, "cell": [1, 1], "camera": True,
            "marker": 62, "alt_seen": 2.0, "miss": 0.0, "side_px": 129, "blind": 0,
            "aim": [0.0, 0.0],
        })
        pult.show_status(drone)
        self.assertFalse(self.said("прицел сдвинут"))


class TrimTest(Spoken):
    """Команда «сдвиг»: оператор говорит, куда уехал дрон, борт правит прицел."""

    def test_centimetres_become_metres_and_right_becomes_left(self):
        """Человек говорит «вправо», борт считает влево: знак обязан перевернуться."""
        drone = FakeDrone()
        pult.do_trim(drone, "10 8")
        self.assertEqual(len(drone.trims), 1)
        fwd, left = drone.trims[0]
        self.assertAlmostEqual(fwd, 0.1, places=6)
        self.assertAlmostEqual(left, -0.08, places=6)

    def test_one_number_shifts_only_forward(self):
        drone = FakeDrone()
        pult.do_trim(drone, "-5")
        self.assertEqual(drone.trims, [(-0.05, -0.0)])

    def test_nonsense_is_not_sent_to_the_board(self):
        drone = FakeDrone()
        pult.do_trim(drone, "вперёд немного")
        pult.do_trim(drone, "")
        self.assertEqual(drone.trims, [])
        self.assertTrue(self.said("сдвиг 10 8"))

    def test_an_absurd_shift_is_refused(self):
        """Полметра за раз — это ошибка замера, а не подстройка: дрон уедет с метки."""
        drone = FakeDrone()
        pult.do_trim(drone, "80 0")
        self.assertEqual(drone.trims, [])
        self.assertTrue(self.said("полуметра"))


class BoardsTest(unittest.TestCase):
    """`--all`: четыре борта берутся из config.yaml вместе с метками и площадками."""

    def boards(self, argv):
        return pult.build_boards(pult.build_parser().parse_args(argv))

    def test_one_board_by_default(self):
        boards = self.boards([])
        self.assertEqual(len(boards), 1)
        self.assertEqual(boards[0].name, "m1")

    def test_all_takes_pads_and_markers_from_the_map(self):
        """Номера меток на площадке путают чаще всего — руками их вводить не надо."""
        boards = {b.name: b for b in self.boards(["--all"])}
        self.assertEqual(sorted(boards), ["m1", "m2", "m3", "m4"])
        self.assertEqual(boards["m1"].cell, "1,1")
        self.assertEqual(boards["m1"].marker, 62)
        self.assertEqual(boards["m4"].cell, "4,4")
        self.assertEqual(boards["m4"].marker, 60)
        self.assertEqual(len({b.marker for b in boards.values()}), 4)

    def test_given_addresses_win_over_the_config(self):
        boards = self.boards(["--all", "10.0.0.1,10.0.0.2"])
        self.assertEqual([b.ip for b in boards], ["10.0.0.1", "10.0.0.2"])
        self.assertEqual(boards[0].url, "http://10.0.0.1:2200")
        self.assertEqual(boards[1].marker, 7)  # площадка m2, метка из карты

    def test_more_addresses_than_drones_is_refused(self):
        with self.assertRaises(RobotError):
            self.boards(["--all", "1.1.1.1,2.2.2.2,3.3.3.3,4.4.4.4,5.5.5.5"])


class ManyBoardsTest(Spoken):
    """Команда без имени идёт всем бортам, с именем — одному."""

    def setUp(self):
        super().setUp()
        args = pult.build_parser().parse_args([])
        self.args = args
        self.boards = []
        for name in ("m1", "m2", "m3"):
            board = pult.Board(name, "127.0.0.1", "sverk", "http://x", "1,1", 62)
            board.drone = FakeDrone()
            self.boards.append(board)

    def typed(self, *lines):
        # Подсказку со списком команд пульт печатает при входе в цикл: в отчёте
        # тестов она только мешает.
        with redirect_stdout(io.StringIO()):
            with mock.patch("builtins.input", side_effect=[*lines, "выход"]):
                pult.loop(self.boards, self.args)
        return [b.drone.asked for b in self.boards]

    def test_a_command_without_a_name_goes_to_everyone(self):
        self.assertEqual(self.typed("огонь"), [1, 1, 1])

    def test_a_named_command_goes_to_one_board(self):
        self.assertEqual(self.typed("m2 огонь"), [0, 1, 0])

    def test_a_name_alone_asks_what_to_do(self):
        self.assertEqual(self.typed("m2"), [0, 0, 0])
        self.assertTrue(self.said("что сделать борту m2"))

    def test_trim_demands_a_single_board(self):
        """Уводы у бортов разные: сдвинуть прицел всем разом — это испортить три."""
        self.typed("сдвиг 10 8")
        self.assertEqual([b.drone.trims for b in self.boards], [[], [], []])
        self.assertTrue(self.said("сдвиг задаётся одному борту"))

    def test_a_refusing_board_does_not_stop_the_others(self):
        self.boards[0].drone.error = "нет связи"
        self.assertEqual(self.typed("огонь"), [1, 1, 1])
        self.assertTrue(self.said("не ответил про огонь"))


if __name__ == "__main__":
    unittest.main()
