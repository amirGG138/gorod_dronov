import unittest

from city.field import Field
from city.rules import (
    EnergyError,
    EnergyLedger,
    RouteBlocked,
    RuleSet,
    Scenario,
    approach_options,
    budget_for,
    check_proposal,
    compile_plan,
    fire_route,
    plan_reasons,
    plan_total_energy,
    water_dwell_valid,
)

RULES = RuleSet()
# Копия боевой раскладки из city/config.yaml. Именно копия, а не чтение конфига:
# конфиг правят на площадке, и тесты правил от этого падать не должны.
BUILDINGS = [(1, 1), (4, 1), (1, 4), (4, 4), (2, 1), (1, 2), (3, 4)]
# Горящий дом сценария. Его соседи-дороги: [3,3], [2,4], [3,5]; ближайшая к башне
# [1,3] — [2,4] (её и выбирает approach), поэтому в тестах ниже она дефолтная.
FIRE = (3, 4)


def field():
    return Field(size=(6, 6), cell=0.8, buildings=BUILDINGS)


def scenario(**kw):
    base = dict(
        fire_cell=FIRE,
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
        route = fire_route(field(), (3, 3), FIRE, 3, (1, 3), RULES)
        dwells = [a for a in route.actions if a.dwell_kind == "water"]
        self.assertEqual(len(dwells), 3)
        self.assertTrue(all(a.seconds == 3.0 and a.led == "blink" for a in dwells))

    def test_rover_never_enters_the_fire_cell(self):
        route = fire_route(field(), (3, 3), FIRE, 2, (1, 3), RULES)
        for action in route.actions:
            self.assertNotIn(FIRE, action.path)

    def test_zero_level_is_rejected(self):
        with self.assertRaises(RouteBlocked):
            fire_route(field(), (3, 3), FIRE, 0, (1, 3), RULES)


class TestPlanReasons(unittest.TestCase):
    """Лог решений: план обязан объяснять себя по-русски, даже когда миссия одна."""

    def test_reasons_name_the_only_mission_and_the_cycles(self):
        reasons = plan_reasons(field(), scenario(), RULES)
        text = " ".join(reasons)
        self.assertIn("Пожар", text)
        self.assertIn("уровень 2", text)

    def test_approach_cell_is_stated(self):
        reasons = plan_reasons(field(), scenario(), RULES)
        spot = field().approach(FIRE, (1, 3))
        self.assertTrue(any(str(list(spot)) in r for r in reasons))

    def test_approach_from_the_model_is_the_one_explained(self):
        """Судье называется та клетка, на которую построен план, а не запасная."""
        default = field().approach(FIRE, (1, 3))
        other = next(c for c in approach_options(field(), scenario()) if c != default)
        reasons = plan_reasons(field(), scenario(), RULES, spot=other)
        text = " ".join(reasons)
        self.assertIn(str(list(other)), text)
        self.assertNotIn(str(list(default)), text)
        self.assertIn("модель", text)

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


class TestProposal(unittest.TestCase):
    """Предложение LLM. Правила решают, а не модель: всё непроходное отбрасывается.

    Каждый отказ обязан называть причину — она уходит в лог целиком и потом
    показывается судьям как доказательство, что модель не в цепи управления.
    """

    def base_budget(self, spot=None):
        return budget_for(field(), scenario(), spot, RULES)[0]

    def check(self, **over):
        proposal = {"approach": [3, 3], "charge_budget": self.base_budget((3, 3))}
        proposal.update(over)
        return check_proposal(field(), scenario(), proposal, RULES)

    def test_options_start_with_the_deterministic_choice(self):
        options = approach_options(field(), scenario())
        self.assertEqual(options[0], field().approach(FIRE, (1, 3)))
        self.assertNotIn(FIRE, options)  # сама клетка пожара вариантом не бывает

    def test_valid_proposal_is_accepted(self):
        verdict = self.check()
        self.assertTrue(verdict.ok, verdict.reason)
        self.assertEqual(verdict.spot, (3, 3))

    def test_the_fire_cell_itself_is_refused(self):
        verdict = self.check(approach=list(FIRE))
        self.assertFalse(verdict.ok)
        self.assertIn("въезжать нельзя", verdict.reason)

    def test_a_building_is_refused(self):
        verdict = self.check(approach=[4, 1])  # дом из BUILDINGS
        self.assertFalse(verdict.ok)
        self.assertIn("здание", verdict.reason)

    def test_a_far_away_cell_is_refused(self):
        verdict = self.check(approach=[0, 0])
        self.assertFalse(verdict.ok)
        self.assertIn("не соседняя", verdict.reason)

    def test_too_small_budget_is_refused(self):
        verdict = self.check(charge_budget=1)
        self.assertFalse(verdict.ok)
        self.assertIn("встанет на полпути", verdict.reason)

    def test_wasteful_budget_is_refused(self):
        """Единица заряда это секунда стоянки, а попытка длится 15 минут."""
        verdict = self.check(charge_budget=self.base_budget((3, 3)) * 3)
        self.assertFalse(verdict.ok)
        self.assertIn("удвоенного", verdict.reason)

    def test_small_extra_budget_is_allowed(self):
        self.assertTrue(self.check(charge_budget=self.base_budget((3, 3)) + 2).ok)

    def test_garbage_answers_do_not_crash(self):
        for junk in ("не объект", None, [1, 2], {"approach": "рядом", "charge_budget": 5}):
            verdict = check_proposal(field(), scenario(), junk, RULES)
            self.assertFalse(verdict.ok)
            self.assertTrue(verdict.reason)

    def test_non_numeric_budget_is_refused(self):
        verdict = self.check(charge_budget="много")
        self.assertFalse(verdict.ok)
        self.assertIn("неразборчиво", verdict.reason)

    def test_chosen_spot_changes_the_route(self):
        """Принятая клетка действительно меняет план, иначе выбор был бы декорацией."""
        actions, _, end = compile_plan(field(), scenario(), RULES, spot=(3, 5))
        self.assertEqual(end, (3, 5))
        for action in actions:
            self.assertNotIn(FIRE, action.path)


if __name__ == "__main__":
    unittest.main()
