import unittest

from city.field import Field
from city.rules import (
    EnergyError,
    EnergyLedger,
    RouteBlocked,
    RuleSet,
    Scenario,
    compile_plan,
    delivery_route,
    escort_lag_ok,
    fire_route,
    load_dwell_valid,
    mission_order,
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
        pickup=(0, 0),
        dropoff=(5, 5),
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

    def test_load_dwell_needs_five_seconds(self):
        self.assertFalse(load_dwell_valid(4.9, moved=False, in_zone=True, led_on=True))
        self.assertTrue(load_dwell_valid(5.0, moved=False, in_zone=True, led_on=True))


class TestEscort(unittest.TestCase):
    def test_two_cells_is_still_ok(self):
        self.assertTrue(escort_lag_ok((3, 3), (3, 1)))

    def test_three_cells_is_a_violation(self):
        self.assertFalse(escort_lag_ok((3, 3), (3, 0)))


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


class TestDeliveryRoute(unittest.TestCase):
    def test_beacon_on_for_the_whole_mission(self):
        route = delivery_route(field(), (3, 3), (0, 0), (5, 5), RULES)
        leds = [a for a in route.actions if a.kind == "led"]
        self.assertEqual([a.led for a in leds], ["blink", "off"])
        self.assertEqual(route.actions[0].kind, "led")  # мигалка до начала движения

    def test_five_second_load(self):
        route = delivery_route(field(), (3, 3), (0, 0), (5, 5), RULES)
        dwell = next(a for a in route.actions if a.dwell_kind == "load")
        self.assertEqual(dwell.seconds, 5.0)
        self.assertEqual(dwell.cell, (0, 0))

    def test_route_blocked_by_unextinguished_fire(self):
        # пожар на дороге в горлышке коридора: объехать нечем
        f = Field(size=(6, 6), cell=0.8, buildings=[(0, 1), (1, 1)])
        with self.assertRaises(RouteBlocked):
            delivery_route(f, (3, 3), (0, 0), (5, 5), RULES, blocked=[(1, 0)])


class TestMissionOrder(unittest.TestCase):
    def test_fire_first_by_score(self):
        order, reasons = mission_order(field(), scenario(), {"fire": 3, "delivery": 1}, RULES)
        self.assertEqual(order, ["fire", "delivery"])
        self.assertTrue(any("опасность" in r for r in reasons))

    def test_fire_forced_first_when_delivery_cannot_pass(self):
        f = Field(size=(6, 6), cell=0.8, buildings=[(0, 1), (1, 1)])
        sc = scenario(fire_cell=(1, 0), fire_level=1, charge=(3, 3), rover_start=(3, 3))
        order, reasons = mission_order(f, sc, {"fire": 0, "delivery": 9}, RULES)
        self.assertEqual(order[0], "fire")
        self.assertIn("доставка не проходит мимо пожара — сначала тушим", reasons)


class TestPlan(unittest.TestCase):
    def test_plan_covers_both_missions(self):
        actions, moves, end = compile_plan(field(), scenario(), ["fire", "delivery"], RULES)
        self.assertEqual(end, (5, 5))
        self.assertGreater(moves, 0)
        self.assertEqual({a.mission for a in actions}, {"fire", "delivery"})

    def test_delivery_after_fire_may_cross_the_burnt_cell(self):
        # пожар на дороге: до тушения клетка закрыта, после — открыта
        f = Field(size=(6, 6), cell=0.8)
        sc = scenario(fire_cell=(3, 2), fire_level=1)
        first, _, _ = compile_plan(f, sc, ["delivery", "fire"], RULES)
        for a in first:
            if a.mission == "delivery":
                self.assertNotIn((3, 2), a.path)

    def test_budget_includes_return_and_reserve(self):
        f = field()
        _, moves, end = compile_plan(f, scenario(), ["fire", "delivery"], RULES)
        total, reason = plan_total_energy(f, scenario(), moves, end, RULES)
        back = Field.moves(f.astar(end, (3, 3)))
        self.assertEqual(total, moves + back + RULES.energy_reserve)
        self.assertIn("резерв", reason)


if __name__ == "__main__":
    unittest.main()
