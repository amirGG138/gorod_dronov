"""Бортовой агент дрона: удержание над меткой, вытеснение команд, честность про посадку.

Железа здесь нет: вместо sverk_interfaces подставляется заглушка Board, считающая
вызовы navigate и land, а вместо опознавания меток — подставные замеры. Проверяется
ровно то, что можно проверить без полёта: куда контур велит двигаться, кто пишет
состояние и что борт про это состояние утверждает. Останется ли живой navigate
управляемым, когда поверх него приходит land, проверяется только полётом.
"""

import importlib.util
import json
import math
import os
import threading
import time
import types
import unittest
import urllib.error
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
        self.refuse = False             # борт отвечает отказом на каждую команду
        self.calls: list[dict] = []     # аргументы каждого navigate: по ним видно поправки

    def navigate(self, **kw):
        self.navigates += 1
        self.calls.append(kw)
        if self.refuse:
            return Resp(False, "занят")
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
    """Камера-заглушка: отдаёт «кадр» нужного размера, метки в нём подставляют тесты."""

    def __init__(self) -> None:
        self.pictures = 0

    def take_picture(self, timeout=2.0):
        self.pictures += 1
        return types.SimpleNamespace(ndim=3, size=1, shape=(480, 640, 3))


class Board:
    def __init__(self) -> None:
        self.control = Control()
        self.image = Camera()


def make_agent(*argv: str):
    """Агент с заглушкой вместо борта. Паузы укорочены: ждать нечего, железа нет."""
    args = da.build_parser().parse_args(
        ["--climb-speed", "100", "--lock-wait", "0.05", "--land-wait", "0.1",
         "--watchdog", "0", "--hold-period", "0", *argv]
    )
    agent = da.Agent(args)
    if not args.dry:
        agent.drone = Board()
    return agent


# Сторона метки, которую видно с рабочих 2 м в кадре 640x480 при угле обзора 65°:
# focal = 320/tan(32.5°) ≈ 502 px, значит сторона = focal * 0.25 / 2.
SIDE_AT_2M = da.focal_px(640, 65.0) * da.MARKER_M / 2.0


def fix(u=320.0, v=240.0, side=SIDE_AT_2M, angle=0.0, mid=62):
    """Замер метки в кадре 640x480: по умолчанию точно в центре, ровно, с высоты 2 м."""
    return da.Fix(mid, u, v, side, angle)


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
        agent = make_agent("--lock-wait", "0.5")
        agent.takeoff(1.5)
        time.sleep(0.05)  # navigate уже издан, борт досыпает паузу до передачи контуру
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
        agent = make_agent("--lock-wait", "0.5")
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
        agent = make_agent("--lock-wait", "0.5")
        agent.takeoff(1.5)                       # борт занят: посадка получит отказ
        with self.assertRaises(da.Busy):
            agent.once("cmd-3", agent.land)
        with self.assertRaises(da.Busy):
            agent.once("cmd-3", agent.land)

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


class TestGeometry(unittest.TestCase):
    """Пиксели в метры и в высоту: единственная опора контура — сама метка."""

    def test_altitude_falls_out_of_the_marker_side(self):
        """Сторона метки обратно пропорциональна высоте: вдвое мельче — вдвое выше."""
        focal = da.focal_px(1280, 65.0)
        self.assertAlmostEqual(da.alt_by_side(focal * 0.25 / 2.0, focal), 2.0, places=6)
        self.assertAlmostEqual(da.alt_by_side(focal * 0.25 / 4.0, focal), 4.0, places=6)

    def test_a_degenerate_marker_gives_no_altitude(self):
        self.assertIsNone(da.alt_by_side(0.5, 1000.0))
        self.assertIsNone(da.alt_by_side(120.0, 0.0))

    def test_the_aim_point_is_shifted_back_by_the_camera_arm(self):
        """body считается от центра корпуса, а метку наводит объектив: целимся назад."""
        forward, left = da.aim(fix(), 640, 480, 0.075, 0.0)
        self.assertAlmostEqual(forward, -0.075, places=6)
        self.assertAlmostEqual(left, 0.0, places=6)

    def test_a_marker_below_the_centre_means_the_drone_went_forward(self):
        """Метка ниже центра кадра лежит позади объектива — лететь надо назад."""
        forward, _ = da.aim(fix(v=340.0), 640, 480, 0.0, 0.0)
        self.assertLess(forward, 0.0)
        self.assertAlmostEqual(forward, -100.0 * da.MARKER_M / SIDE_AT_2M, places=6)

    def test_a_marker_left_of_the_centre_pulls_the_drone_left(self):
        _, left = da.aim(fix(u=220.0), 640, 480, 0.0, 0.0)
        self.assertGreater(left, 0.0)

    def test_the_axes_can_be_flipped_without_touching_the_code(self):
        """Знаки осей на железе не сверялись — они обязаны переворачиваться ключом."""
        straight = da.aim(fix(u=220.0, v=340.0), 640, 480, 0.0, 0.0)
        flipped = da.aim(fix(u=220.0, v=340.0), 640, 480, 0.0, 0.0, -1.0, -1.0)
        self.assertAlmostEqual(flipped[0], -straight[0], places=6)
        self.assertAlmostEqual(flipped[1], -straight[1], places=6)


class TestHolder(unittest.TestCase):
    """Плавность контура: сглаживание, демпфирование и мёртвые зоны — без железа."""

    def make(self, **kw):
        args = dict(gain=0.5, damp=0.0, smooth=1.0, tol=0.05, min_hop=0.01, max_hop=0.4,
                    alt_dead=0.07, alt_fix=0.25, yaw_dead=3.0, yaw_step=10.0)
        args.update(kw)
        return da.Holder(**args)

    def test_a_part_of_the_miss_is_worked_off(self):
        holder = self.make()
        self.assertAlmostEqual(holder.command(0.4, 0.0, 0.0, None, 1.0)[0], 0.2, places=6)

    def test_noise_is_smoothed_not_flown(self):
        """Выброс опознания на один кадр отрабатывается вполовину, а не целиком."""
        holder = self.make(smooth=0.5)
        holder.command(0.2, 0.0, 0.0, None, 1.0)
        self.assertAlmostEqual(holder.command(0.4, 0.0, 0.0, None, 1.5)[0], 0.15, places=6)

    def test_a_quickly_shrinking_miss_is_pushed_less(self):
        """Демпфирование: то, что и так сходится, добивать не надо — иначе перелёт."""
        calm = self.make(damp=0.1)
        calm.command(0.4, 0.0, 0.0, None, 1.0)
        damped = calm.command(0.2, 0.0, 0.0, None, 1.5)[0]

        plain = self.make(damp=0.0)
        plain.command(0.4, 0.0, 0.0, None, 1.0)
        self.assertLess(damped, plain.command(0.2, 0.0, 0.0, None, 1.5)[0])

    def test_a_long_gap_does_not_produce_a_damping_kick(self):
        """После потери метки разность замеров даёт выброс — по нему толкать нельзя."""
        holder = self.make(damp=0.1)
        holder.command(0.4, 0.0, 0.0, None, 1.0)
        self.assertAlmostEqual(holder.command(0.2, 0.0, 0.0, None, 30.0)[0], 0.1, places=6)

    def test_tiny_corrections_are_not_sent_at_all(self):
        """Дёргать дрон на шуме опознания метки — это и есть качка."""
        self.assertIsNone(self.make().command(0.02, 0.01, 0.0, None, 1.0))

    def test_the_dead_zone_is_measured_on_the_miss_not_on_the_command(self):
        """Промах чуть больше допуска обязан отрабатываться при любом --gain.

        До 29.07.2026 мёртвая зона стояла на длине команды, то есть делилась на gain:
        при 0,04 и 0,35 дрон переставал править всё, что ближе 11 см, и устойчиво
        висел РЯДОМ с меткой. Слабый коэффициент не должен расширять допуск.
        """
        weak = self.make(gain=0.1, min_hop=0.04)
        command = weak.command(0.08, 0.0, 0.0, None, 1.0)
        self.assertIsNotNone(command)
        # 0,1 × 0,08 = 8 мм короче min_hop, но промах вне допуска: дотягиваем, а не
        # отменяем — отменённая команда и есть «висит рядом с меткой».
        self.assertAlmostEqual(command[0], 0.04, places=6)

    def test_the_miss_inside_the_tolerance_is_left_alone(self):
        self.assertIsNone(self.make(tol=0.1).command(0.09, 0.0, 0.0, None, 1.0))

    def test_a_long_hop_is_cut(self):
        holder = self.make(gain=1.0)
        forward, left, _, _ = holder.command(3.0, 0.0, 0.0, None, 1.0)
        self.assertAlmostEqual(math.hypot(forward, left), 0.4, places=6)

    def test_altitude_has_its_own_dead_zone_and_limit(self):
        holder = self.make()
        self.assertIsNone(holder.command(0.0, 0.0, 0.05, None, 1.0))
        holder.reset()
        self.assertAlmostEqual(holder.command(0.0, 0.0, 0.9, None, 1.0)[2], 0.25, places=6)
        holder.reset()
        self.assertAlmostEqual(holder.command(0.0, 0.0, -0.9, None, 1.0)[2], -0.25, places=6)

    def test_the_turn_rides_in_the_same_command(self):
        """Отдельной команды разворота нет: доворот уходит тем же navigate."""
        command = self.make().command(0.0, 0.0, 0.0, math.radians(20.0), 1.0)
        self.assertIsNotNone(command)
        self.assertAlmostEqual(math.degrees(command[3]), -10.0, places=6)

    def test_an_unusable_heading_measurement_is_not_a_turn(self):
        self.assertIsNone(self.make().command(0.0, 0.0, 0.0, None, 1.0))

    def test_reset_forgets_the_smoothed_state(self):
        holder = self.make(smooth=0.5)
        holder.command(0.4, 0.0, 0.0, None, 1.0)
        holder.reset()
        self.assertAlmostEqual(holder.command(0.2, 0.0, 0.0, None, 1.5)[0], 0.1, places=6)


class TestHoldTick(unittest.TestCase):
    """Такт удержания: за что цепляемся, куда двигаемся и когда молчим."""

    def setUp(self):
        self.seen = {62: fix()}                 # что «видит» опознавание в этом кадре
        self._real = da.markers
        da.markers = lambda frame: self.seen

    def tearDown(self):
        da.markers = self._real

    def hovering(self, *argv):
        agent = make_agent(*argv)
        agent.camera_ok = True
        agent.takeoff(2.0)
        wait_state(agent, ("hover",))
        wait_idle(agent)
        return agent

    @staticmethod
    def settled(agent):
        """Считать, что прошлая поправка доехала и дрон успокоился.

        После каждой команды такт молчит, пока она не отработается (--settle), — иначе
        замер снимался бы с летящего и накренённого дрона. Тестам, которым нужны два
        такта подряд, ждать это по-настоящему незачем: пауза проверяется отдельно.
        """
        agent._settle_until = 0.0
        return agent

    def lost(self, *argv):
        """Дрон висит, а своей метки в кадре нет: следующий такт — уже поиск."""
        agent = self.hovering("--blind-max", "1", *argv)
        self.seen = {}
        return agent

    def tick(self, agent) -> dict:
        """Один шаг поиска: вернуть аргументы команды, которую он отдал."""
        self.assertEqual(self.settled(agent).hold_tick(), "search")
        return agent.drone.control.calls[-1]

    def leg(self, agent):
        call = self.tick(agent)
        return call["x"], call["y"]

    def test_only_our_own_marker_is_held(self):
        """Между метками поля 2,4 м: перецепившись на соседнюю, дрон улетел бы к ней."""
        agent = self.hovering()
        self.seen = {50: fix(u=100.0, mid=50)}
        before = agent.drone.control.navigates
        self.assertEqual(agent.hold_tick(), "blind")
        self.assertEqual(agent.drone.control.navigates, before)
        self.assertEqual(agent.blind, 1)

    def test_the_camera_arm_is_worked_off(self):
        """Плечо задано ключом — метка ровно в центре кадра, а дрон сдаёт назад на него.

        По умолчанию --cam-fwd = 0 (плечо на железе не замерено), поэтому механизм
        проверяется с явно заданным плечом.
        """
        agent = self.hovering("--gain", "1.0", "--damp", "0", "--smooth", "1",
                              "--min-hop", "0.0", "--cam-fwd", "0.075")
        self.assertEqual(agent.hold_tick(), "moved")
        last = agent.drone.control.calls[-1]
        self.assertAlmostEqual(last["x"], -0.075, places=6)
        self.assertAlmostEqual(last["y"], 0.0, places=6)
        self.assertEqual(last["frame_id"], "body")

    def test_the_aim_is_shifted_by_the_drift_seen_by_eye(self):
        """Дрон устойчиво висит мимо метки, а по кадру «попал»: правит это только человек.

        Оператор называет увод самого ДРОНА, и прицел сдвигается ровно на него: в
        равновесии контур отрабатывает эту величину и корпус встаёт над меткой.
        """
        agent = self.hovering("--gain", "1.0", "--damp", "0", "--smooth", "1",
                              "--min-hop", "0.0")
        self.assertEqual(agent.hold_tick(), "hold")     # метка в центре — править нечего
        agent.trim(0.10, -0.08)                         # уехал вперёд и вправо
        self.assertEqual(agent.status()["aim"], [0.1, -0.08])
        self.assertEqual(self.settled(agent).hold_tick(), "moved")
        last = agent.drone.control.calls[-1]
        self.assertAlmostEqual(last["x"], -0.10, places=6)
        self.assertAlmostEqual(last["y"], 0.08, places=6)

    def test_trims_add_up(self):
        """Подстройка идёт по остатку: второй «сдвиг» не отменяет первый, а дополняет."""
        agent = self.hovering()
        agent.trim(0.10, 0.0)
        agent.trim(0.03, -0.02)
        self.assertEqual(agent.status()["aim"], [0.13, -0.02])

    def test_a_trim_forgets_the_smoothed_measurement(self):
        """Сглаженный промах снят по старому прицелу — иначе первая поправка вполовину."""
        agent = self.hovering("--smooth", "0.5")
        self.seen = {62: fix(v=290.0)}
        self.settled(agent).hold_tick()
        agent.trim(0.10, 0.0)
        self.assertIsNone(agent.holder.fwd)

    def test_the_climb_after_takeoff_goes_in_one_command(self):
        """Набор высоты не режется ступеньками: на каждой паузе дрон сносит с метки.

        Первая же поправка контура переинициализирует траекторию взлёта, поэтому
        ступенька по alt_fix означала бы «взлёт до текущей высоты плюс 25 см», а
        дальше подъём лесенкой с паузой на успокоение после каждой ступеньки.
        """
        agent = self.hovering("--smooth", "1")
        self.seen = {62: fix(side=fix().side * 4.0)}    # вчетверо крупнее = высота 0,5 м
        self.assertEqual(agent.hold_tick(), "moved")
        self.assertAlmostEqual(agent.drone.control.calls[-1]["z"], 1.5, places=6)

    def test_a_height_slip_in_flight_is_still_capped(self):
        """Рабочая высота набрана: резкий скачок теперь — сбой замера, а не задача."""
        agent = self.hovering("--smooth", "1")
        agent.hold_tick()                               # висим ровно: высота достигнута
        self.seen = {62: fix(side=fix().side * 4.0)}
        self.assertEqual(self.settled(agent).hold_tick(), "moved")
        self.assertAlmostEqual(agent.drone.control.calls[-1]["z"], 0.25, places=6)

    def test_a_drop_in_height_is_returned(self):
        """Метка стала крупнее — дрон просел, и поправка обязана быть вверх."""
        agent = self.hovering("--smooth", "1")
        self.seen = {62: fix(side=fix().side * 2.0)}    # вдвое крупнее = вдвое ниже
        self.assertEqual(agent.hold_tick(), "moved")
        self.assertGreater(agent.drone.control.calls[-1]["z"], 0.0)
        self.assertLess(agent.alt_seen, agent.alt)

    def test_a_climb_beyond_the_working_height_is_pushed_down(self):
        agent = self.hovering("--smooth", "1")
        self.seen = {62: fix(side=fix().side / 2.0)}
        self.assertEqual(agent.hold_tick(), "moved")
        self.assertLess(agent.drone.control.calls[-1]["z"], 0.0)

    def test_the_heading_reference_is_taken_from_the_first_frame(self):
        """Ждать успокоения нечего: высота абсолютная, а замер всё равно сглаживается."""
        self.seen = {62: fix(angle=math.radians(20.0))}
        agent = self.hovering()
        agent.hold_tick()
        self.assertAlmostEqual(math.degrees(agent._yaw_ref), 20.0, places=6)
        self.assertEqual(agent.status()["yaw_ref"], 20)

    def test_the_drift_of_the_heading_is_worked_off(self):
        agent = self.hovering()
        agent.hold_tick()                                    # снял эталон 0°
        self.seen = {62: fix(angle=math.radians(10.0))}      # висел и отвернулся
        self.assertEqual(self.settled(agent).hold_tick(), "moved")
        self.assertAlmostEqual(math.degrees(agent.drone.control.calls[-1]["yaw"]), -10.0, places=6)
        self.assertEqual(agent.status()["yaw_drift"], 10)

    def test_an_implausible_marker_does_not_turn_the_drone(self):
        """Сбой опознания метки не должен разворачивать дрон на десятки градусов."""
        agent = self.hovering()
        agent.hold_tick()
        self.seen = {62: fix(angle=math.radians(120.0))}
        self.settled(agent).hold_tick()
        self.assertEqual(agent.drone.control.calls[-1]["yaw"], 0.0)

    def test_a_drone_standing_still_is_left_alone(self):
        """Всё в мёртвых зонах — команду слать незачем, она только занимает борт."""
        agent = self.hovering()
        agent.hold_tick()
        before = agent.drone.control.navigates
        self.assertEqual(agent.hold_tick(), "hold")
        self.assertEqual(agent.drone.control.navigates, before)

    def test_the_correction_is_given_time_to_arrive(self):
        """navigate только ставит цель. Мерить, пока дрон к ней едет, — это и есть качка.

        Прежняя версия слала новую цель каждые полсекунды поверх недоехавшей: цели
        складывались, дрон проскакивал метку и висел рядом с ней, а не над ней.
        """
        agent = self.hovering("--settle", "5")
        self.seen = {62: fix(v=290.0)}          # метка ушла из центра — есть что править
        self.assertEqual(agent.hold_tick(), "moved")
        before = agent.drone.control.navigates
        self.assertEqual(agent.hold_tick(), "settling")
        self.assertEqual(agent.drone.control.navigates, before)
        self.assertTrue(agent.status()["settling"])

    def test_the_pause_covers_the_flight_of_the_correction(self):
        """Ждать надо не только успокоение: сама поправка летит путь/скорость секунд."""
        agent = self.hovering()
        # 0,4 м на 0,25 м/с = 1,6 с полёта плюс 0,6 с на успокоение.
        self.assertAlmostEqual(agent._travel(0.4, 0.0, 0.0, 0.25), 2.2, places=6)
        # Горизонталь и высота отрабатываются одновременно — берём длинную из них.
        self.assertAlmostEqual(agent._travel(0.0, 0.0, 0.25, 0.25), 1.6, places=6)

    def test_a_new_flight_does_not_wait_for_the_previous_one(self):
        agent = self.hovering("--settle", "5")
        self.seen = {62: fix(v=290.0)}          # метка ушла из центра — есть что править
        agent.hold_tick()
        agent.land()
        wait_state(agent, ("landed", "landed_unverified"))
        agent.takeoff(2.0)
        wait_state(agent, ("hover",))
        wait_idle(agent)
        self.assertEqual(agent.hold_tick(), "moved")

    def test_a_drone_on_the_ground_is_not_held(self):
        agent = self.hovering()
        agent.land()
        wait_state(agent, ("landed", "landed_unverified"))
        before = agent.drone.control.navigates
        self.assertEqual(agent.hold_tick(), "idle")
        self.assertEqual(agent.drone.control.navigates, before)

    def test_a_busy_board_is_not_disturbed(self):
        agent = self.hovering("--lock-wait", "0.5")
        agent.takeoff(2.0)
        agent.state = "hover"
        agent._busy = True
        self.assertEqual(agent.hold_tick(), "busy")

    def test_a_lost_marker_is_admitted_not_guessed(self):
        agent = self.hovering("--blind-max", "3")
        self.seen = {}
        for _ in range(2):
            self.assertEqual(agent.hold_tick(), "blind")
        self.assertFalse(agent.marker_lost)
        self.assertEqual(self.settled(agent).hold_tick(), "search")
        self.assertTrue(agent.marker_lost)
        self.assertTrue(agent.status()["marker_lost"])
        # Вернулась метка — вернулось и удержание, без перезапуска агента.
        self.seen = {62: fix()}
        self.settled(agent).hold_tick()
        self.assertFalse(agent.marker_lost)
        self.assertEqual(agent.blind, 0)

    def test_the_search_rises_and_walks_around_the_loss(self):
        """Метки нет — стоять бессмысленно: поднимаемся и обходим стороны по очереди."""
        agent = self.lost("--search-step", "0.3", "--search-rise", "0.1")
        moves = [self.leg(agent) for _ in range(8)]
        # Отход — возврат — отход: каждая сторона пробуется от точки потери, а не от
        # предыдущего отхода, иначе дрон уполз бы на метр с лишним.
        self.assertEqual([(round(x, 2), round(y, 2)) for x, y in moves], [
            (0.3, 0.0), (-0.3, 0.0),        # вперёд и назад в центр
            (-0.3, 0.0), (0.3, 0.0),        # назад и назад в центр
            (0.0, 0.3), (0.0, -0.3),        # влево и назад в центр
            (0.0, -0.3), (0.0, 0.3),        # вправо и назад в центр
        ])

    def test_the_search_rises_no_more_than_allowed(self):
        """Подъём — единственное, что уводит дрон от площадки: он и ограничен счётом."""
        agent = self.lost("--search-rise", "0.1", "--search-rise-max", "5")
        ups = [self.tick(agent)["z"] for _ in range(80)]
        self.assertEqual([round(z, 2) for z in ups if z], [0.1] * 5)
        self.assertEqual(agent.status()["search_rises"], 5)

    def test_the_search_does_not_climb_through_the_ceiling(self):
        """Потолок регламента (2.6) старше поиска: у самого предела не поднимаемся вовсе."""
        agent = self.lost("--alt", "2.0", "--max-alt", "2.25", "--search-rise", "0.1")
        ups = [self.tick(agent)["z"] for _ in range(40)]
        self.assertEqual([round(z, 2) for z in ups if z], [0.1] * 2)

    def test_a_found_marker_gives_the_search_its_rises_back(self):
        """Предел подъёмов — на каждую потерю: иначе вторая потеря искалась бы вслепую."""
        agent = self.lost("--search-rise-max", "1")
        self.tick(agent)
        self.assertEqual(agent._search_rises, 1)
        self.seen = {62: fix()}
        self.settled(agent).hold_tick()
        self.assertEqual(agent._search_rises, 0)
        self.assertEqual(agent._search_off, (0.0, 0.0))

    def test_the_search_is_switched_off_by_a_zero_step(self):
        """Выключенный поиск — прежнее поведение: висим на автопилоте и не дёргаемся."""
        agent = self.lost("--search-step", "0")
        before = agent.drone.control.navigates
        self.assertEqual(self.settled(agent).hold_tick(), "lost")
        self.assertEqual(agent.drone.control.navigates, before)

    def test_a_search_step_that_did_not_go_through_is_retried(self):
        """Команду не приняли — сторона не считается пройденной, иначе поиск её пропустит.

        Хуже пропуска то, что учёт отхода разошёлся бы с тем, где дрон висит на самом
        деле, и «возврат в центр» увёл бы его на 30 см мимо.
        """
        agent = self.lost()
        agent.drone.control.refuse = True
        self.assertEqual(self.settled(agent).hold_tick(), "refused")
        self.assertEqual(agent._search_off, (0.0, 0.0))
        agent.drone.control.refuse = False
        self.assertEqual(round(self.leg(agent)[0], 2), 0.3)   # всё та же первая сторона

    def test_holding_starts_right_after_the_takeoff_is_accepted(self):
        """Прежняя версия ждала набор высоты и успокоение — около девяти секунд."""
        self.seen = {62: fix(u=200.0)}         # метку снесло: контуру есть что править
        agent = make_agent("--climb-speed", "0.1", "--lock-wait", "0.05")
        agent.camera_ok = True
        started = time.monotonic()
        agent.takeoff(2.0)                     # набор 2 м на 0,1 м/с = 20 с
        self.assertEqual(wait_state(agent, ("hover",), 2.0), "hover")
        self.assertLess(time.monotonic() - started, 1.0)
        wait_idle(agent)
        self.assertEqual(agent.hold_tick(), "moved")

    def test_switched_off_by_the_flag(self):
        agent = self.hovering("--no-hold")
        self.assertFalse(agent.hold_on)
        self.assertEqual(agent.hold_tick(), "idle")
        self.assertNotIn("marker", agent.status())

    def test_the_status_shows_what_the_drone_sees(self):
        agent = self.hovering()
        agent.hold_tick()
        st = agent.status()
        self.assertEqual(st["marker"], 62)
        self.assertAlmostEqual(st["alt_seen"], round(agent.alt_seen, 2))
        self.assertIsNotNone(st["side_px"])
        self.assertEqual(st["blind"], 0)


class TestMarkerByCell(unittest.TestCase):
    """Номер своей метки берётся из карты поля, но задаётся и руками."""

    def test_every_pad_has_its_marker(self):
        for cell, mid in ((("1,4"), 50), (("4,4"), 60), (("1,1"), 62), (("4,1"), 7)):
            with self.subTest(cell=cell):
                self.assertEqual(make_agent("--cell", cell).marker, mid)

    def test_an_unknown_cell_is_admitted_not_guessed(self):
        """Метки для этой клетки в карте нет — врать про неё нельзя."""
        self.assertEqual(make_agent("--cell", "2,2").marker, -1)

    def test_the_key_beats_the_map(self):
        self.assertEqual(make_agent("--cell", "1,1", "--marker", "13").marker, 13)


try:
    import cv2 as _cv2

    HAVE_CV2 = hasattr(_cv2, "aruco")
except ImportError:
    HAVE_CV2 = False


def marker_frame(deg: float = 0.0, mid: int = 62, size: int = 100):
    """Кадр 640x480 с меткой mid в центре, повёрнутой на deg градусов ПРОТИВ часовой.

    Против часовой — потому что так считает cv2.getRotationMatrix2D; в осях кадра
    (y вниз) тому же повороту соответствует отрицательный угол ребра, и именно его
    отдаёт markers().
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


@unittest.skipUnless(HAVE_CV2, "нужен cv2 с модулем aruco")
class TestMarkers(unittest.TestCase):
    """Опознание меток на нарисованных кадрах: на борту это и курс, и высота, и место."""

    def test_a_straight_marker_reads_as_zero(self):
        self.assertAlmostEqual(math.degrees(da.markers(marker_frame())[62].angle), 0.0, places=1)

    def test_a_turned_marker_reads_the_turn(self):
        for deg in (15.0, -20.0, 90.0):
            with self.subTest(deg=deg):
                angle = math.degrees(da.markers(marker_frame(deg))[62].angle)
                self.assertAlmostEqual(angle, -deg, delta=1.0)

    def test_an_empty_frame_has_no_markers(self):
        import numpy as np

        self.assertEqual(da.markers(np.full((480, 640, 3), 255, np.uint8)), {})

    def test_our_field_markers_are_all_recognised(self):
        """id 60 и 62 в словарь 4X4_50 не влезают — на нём держаться было бы не за что."""
        for mid in (50, 60, 62, 7):
            with self.subTest(marker=mid):
                self.assertIn(mid, da.markers(marker_frame(0.0, mid)))

    def test_the_side_and_the_centre_are_measured(self):
        seen = da.markers(marker_frame(0.0, 62, 100))[62]
        self.assertAlmostEqual(seen.side, 100.0, delta=2.0)
        self.assertAlmostEqual(seen.u, 320.0, delta=2.0)
        self.assertAlmostEqual(seen.v, 240.0, delta=2.0)

    def test_the_centre_is_where_the_diagonals_cross(self):
        """У наклонённой метки середина сторон и середина диагоналей — разные точки."""
        skewed = ((0.0, 0.0), (100.0, 0.0), (60.0, 60.0), (0.0, 40.0))
        self.assertNotAlmostEqual(da.quad_center(skewed)[0], 40.0, places=3)
        square = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))
        self.assertAlmostEqual(da.quad_center(square)[0], 5.0, places=6)
        self.assertAlmostEqual(da.quad_center(square)[1], 5.0, places=6)


# Кадр для проверок огня рисуется в масштабе 0,005 м на пиксель: метка 50 px = 0,25 м.
# Тогда весь кадр 640x480 — это 3,2 x 2,4 м поля, то есть в него влезают соседние
# клетки, а не только своя. «Жетон» на таком кадре — квадрат 18 px, поэтому агенту в
# этих тестах задаётся жетон 0,09 м со сплошным силуэтом: TOKEN — это мерка, по которой
# делятся слипшиеся пятна, и она обязана совпадать с тем, что нарисовано.
MPP = da.MARKER_M / 50.0
TOKEN_PX = 18
TOKEN = ("--token-m", str(TOKEN_PX * MPP), "--token-fill", "1.0")
# Центр клетки (2,2) в пикселях этого кадра: метка 62 стоит в клетке (1,1), то есть в
# (−1.2, −1.2) м, а соседняя по диагонали клетка на 0,8 м правее и выше = 160 px.
CELL22 = (320 + 160, 240 - 160)


def fire_frame(spots, mid: int = 62, size: int = 50):
    """Кадр с меткой и красными жетонами: spots — список (u, v, сторона в пикселях)."""
    import cv2

    img = marker_frame(0.0, mid, size)
    for u, v, side in spots:
        half = side // 2
        cv2.rectangle(img, (u - half, v - half), (u + half, v + half), (0, 0, 200), -1)
    return img


def heap(count: int, side: int = TOKEN_PX):
    """Кучка из count жетонов вокруг центра клетки (2,2), симметрично."""
    u, v = CELL22
    step = 40  # 0,2 м между жетонами: одна кучка (порог 0,4 м), но пятна раздельные
    start = -(count - 1) / 2.0
    return [(int(u + (start + i) * step), v, side) for i in range(count)]


@unittest.skipUnless(HAVE_CV2, "нужен cv2 с модулем aruco")
class TestFire(unittest.TestCase):
    """Огонь на борту: клетка очага и число огоньков = сколько раз ехать за водой."""

    def agent(self, *argv):
        agent = make_agent("--cell", "1,1", *TOKEN, *argv)
        agent.camera_ok = True
        return agent

    def test_three_tokens_in_a_heap_are_three_trips_for_water(self):
        report = self.agent().see_fire(fire_frame(heap(3)))
        self.assertTrue(report["found"])
        self.assertEqual(report["cell"], [2, 2])
        self.assertEqual(report["count"], 3)
        self.assertEqual(report["count_source"], "blobs")
        self.assertEqual(report["anchor"], "marker")
        self.assertEqual(report["marker_id"], 62)

    def test_an_empty_field_is_admitted_not_guessed(self):
        """Уровень пожара не выдумывается: не нашли — так и пишем."""
        report = self.agent().see_fire(marker_frame(0.0, 62, 50))
        self.assertFalse(report["found"])
        self.assertIsNone(report["cell"])
        self.assertIn("очага", report["note"])

    def test_a_single_token_is_a_single_trip(self):
        report = self.agent().see_fire(fire_frame(heap(1)))
        self.assertTrue(report["found"])
        self.assertEqual(report["count"], 1)
        self.assertEqual(report["count_source"], "blobs")

    def test_stuck_together_tokens_are_split_by_area(self):
        """Жетоны легли вплотную — пятно одно, но оно кратно одиночному по размеру."""
        import cv2

        img = fire_frame([])
        u, v = CELL22
        cv2.rectangle(img, (u - TOKEN_PX, v - TOKEN_PX // 2),
                      (u + TOKEN_PX, v + TOKEN_PX // 2), (0, 0, 200), -1)
        report = self.agent().see_fire(img)
        self.assertTrue(report["found"])
        self.assertEqual(report["count"], 2)
        self.assertEqual(report["count_source"], "area")

    def test_a_speck_of_dust_is_not_a_fire(self):
        """Порог площади отсекает шум: пятно в четыре пикселя огоньком не бывает."""
        report = self.agent().see_fire(fire_frame(heap(1, side=2)))
        self.assertFalse(report["found"])

    def test_a_spot_outside_the_field_is_not_a_fire(self):
        """Красный предмет за краем поля — не очаг, и приписывать ему клетку нельзя."""
        report = self.agent().see_fire(fire_frame([(30, 440, TOKEN_PX)]))
        self.assertFalse(report["found"])
        self.assertIn("за границей поля", report["note"])

    def test_the_count_never_exceeds_what_the_field_can_hold(self):
        report = self.agent("--max-fire", "2").see_fire(fire_frame(heap(3)))
        self.assertEqual(report["count"], 2)
        self.assertIn("больше, чем бывает", report["note"])

    def test_the_answer_is_remembered_for_the_status(self):
        agent = self.agent()
        self.assertNotIn("fire", agent.status())
        agent.last_fire = agent.see_fire(fire_frame(heap(1)))
        self.assertTrue(agent.status()["fire"]["found"])

    def test_without_a_marker_the_frame_is_still_placed_by_height(self):
        """Метку не видно — привязываемся по своей площадке и высоте. Грубее, но не молча."""
        import numpy as np

        agent = self.agent()
        agent.alt = 2.0
        blank = np.full((480, 640, 3), 255, np.uint8)
        import cv2

        cv2.rectangle(blank, (330, 230), (350, 250), (0, 0, 200), -1)
        report = agent.see_fire(blank)
        self.assertEqual(report["anchor"], "pose")
        self.assertTrue(report["found"])


class TestHttp(unittest.TestCase):
    """Сетевой слой: что борт отвечает на запросы диспетчера и пульта."""

    def setUp(self):
        self.agent = make_agent("--dry")
        handler = type("Bound", (da.Handler,), {"agent": self.agent})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def get(self, path):
        with urllib.request.urlopen(self.url + path, timeout=5) as answer:
            return answer.status, answer.read()

    def post(self, path, body=None):
        request = urllib.request.Request(
            self.url + path, data=json.dumps(body or {}).encode(), method="POST"
        )
        with urllib.request.urlopen(request, timeout=5) as answer:
            return answer.status, json.loads(answer.read())

    def test_status_answers_always(self):
        code, body = self.get("/status")
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)["ok"])

    def test_takeoff_and_land_are_accepted(self):
        self.assertTrue(self.post("/takeoff", {"alt": 2.0})[1]["accepted"])
        wait_state(self.agent, ("hover",))
        self.assertTrue(self.post("/land")[1]["accepted"])

    def test_a_shot_is_a_jpeg(self):
        code, body = self.get("/shot")
        self.assertEqual(code, 200)
        self.assertTrue(body.startswith(b"\xff\xd8"))

    def test_fire_answers_in_the_dry_run_too(self):
        code, body = self.get("/fire")
        self.assertEqual(code, 200)
        self.assertFalse(json.loads(body)["found"])

    def test_a_removed_path_is_a_clear_404(self):
        """Перелётов по полю больше нет — и это должно быть видно, а не молча висеть."""
        request = urllib.request.Request(
            self.url + "/look", data=b"{}", method="POST"
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(caught.exception.code, 404)
        caught.exception.close()


if __name__ == "__main__":
    unittest.main()
