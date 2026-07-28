import unittest

from city.field import Field
from city.rules import (
    EnergyError,
    EnergyLedger,
    RouteBlocked,
    RuleSet,
    Scenario,
    compile_plan,
    fire_route,
    plan_reasons,
    plan_total_energy,
    water_dwell_valid,
)

RULES = RuleSet()
BUILDINGS = [(1, 1), (4, 1), (1, 4), (4, 4), (3, 1), (4, 2), (2, 4)]


def field():
    return Field(size=(6, 6), cell=0.8, buildings=BUILDINGS)


def scenario(**kw):
    base = dict(
        fire_cell=(4, 2),
        fire_level=2,
        tower=(1, 3),
        charge=(3, 3),
        rover_start=(3, 3),
    )
    base.update(kw)
    return Scenario(**base)


class TestEnergy(unittest.TestCase):
    def test_starts_empty(self):
        self.assertEqual(EnergyLedger().energy, 0)

    def test_zero_energy_blocks_move(self):
        led = EnergyLedger()
        with self.assertRaises(EnergyError):
            led.spend_move()

    def test_only_whole_seconds_count(self):
        led = EnergyLedger()
        self.assertEqual(led.charge(2.9), 2)  # 2,9 с это два перемещения, не три
        self.assertEqual(led.energy, 2)

    def test_spend_until_blocked(self):
        led = EnergyLedger()
        led.charge(2)
        led.spend_move()
        led.spend_move()
        with self.assertRaises(EnergyError):
            led.spend_move()
        self.assertEqual(led.spent, 2)


class TestDwell(unittest.TestCase):
    """Регламент: пропуск стоянки или движение во время неё аннулируют шаг."""

    def test_water_dwell_ok(self):
        self.assertTrue(water_dwell_valid(3.0, moved=False, in_zone=True, led_on=True))

    def test_water_dwell_29_is_not_enough(self):
        self.assertFalse(water_dwell_valid(2.9, moved=False, in_zone=True, led_on=True))

    def test_movement_kills_the_dwell(self):
        self.assertFalse(water_dwell_valid(5.0, moved=True, in_zone=True, led_on=True))

    def test_led_off_kills_the_dwell(self):
        self.assertFalse(water_dwell_valid(5.0, moved=False, in_zone=True, led_on=False))

    def test_wrong_cell_kills_the_dwell(self):
        self.assertFalse(water_dwell_valid(5.0, moved=False, in_zone=False, led_on=True))


class TestFireRoute(unittest.TestCase):
    def test_level_equals_number_of_cycles(self):
        route = fire_route(field(), (3, 3), (4, 2), 3, (1, 3), RULES)
        dwells = [a for a in route.actions if a.dwell_kind == "water"]
        self.assertEqual(len(dwells), 3)
        self.assertTrue(all(a.seconds == 3.0 and a.led == "blink" for a in dwells))

    def test_rover_never_enters_the_fire_cell(self):
        route = fire_route(field(), (3, 3), (4, 2), 2, (1, 3), RULES)
        for action in route.actions:
            self.assertNotIn((4, 2), action.path)

    def test_zero_level_is_rejected(self):
        with self.assertRaises(RouteBlocked):
            fire_route(field(), (3, 3), (4, 2), 0, (1, 3), RULES)


class TestPlanReasons(unittest.TestCase):
    """Лог решений: план обязан объяснять себя по-русски, даже когда миссия одна."""

    def test_reasons_name_the_only_mission_and_the_cycles(self):
        reasons = plan_reasons(field(), scenario(), RULES)
        text = " ".join(reasons)
        self.assertIn("Пожар", text)
        self.assertIn("уровень 2", text)

    def test_approach_cell_is_stated(self):
        reasons = plan_reasons(field(), scenario(), RULES)
        spot = field().approach((4, 2), (1, 3))
        self.assertTrue(any(str(list(spot)) in r for r in reasons))

    def test_unreachable_fire_is_reported(self):
        # горящий дом заперт домами со всех сторон: подъезжать некуда
        f = Field(size=(6, 6), cell=0.8, buildings=[(2, 2), (1, 2), (3, 2), (2, 1), (2, 3)])
        with self.assertRaises(RouteBlocked):
            plan_reasons(f, scenario(fire_cell=(2, 2)), RULES)


class TestPlan(unittest.TestCase):
    def test_plan_is_the_fire_mission_only(self):
        actions, moves, end = compile_plan(field(), scenario(), RULES)
        self.assertGreater(moves, 0)
        self.assertEqual({a.mission for a in actions}, {"fire"})

    def test_plan_starts_from_the_rover_cell(self):
        actions, _, _ = compile_plan(field(), scenario(rover_start=(0, 0)), RULES)
        first_drive = next(a for a in actions if a.kind == "drive")
        self.assertEqual(first_drive.path[0], (0, 0))

    def test_budget_includes_return_and_reserve(self):
        f = field()
        _, moves, end = compile_plan(f, scenario(), RULES)
        total, reason = plan_total_energy(f, scenario(), moves, end, RULES)
        back = Field.moves(f.astar(end, (3, 3)))
        self.assertEqual(total, moves + back + RULES.energy_reserve)
        self.assertIn("резерв", reason)


if __name__ == "__main__":
    unittest.main()
