"""Шлюз к модели: он обязан молчать в тряпочку, а не ронять попытку.

Главное, что здесь проверяется, — не «умеет ли Brain говорить с моделью», а
обратное: что при любом поведении чужого сервера прогон продолжается
детерминированным путём, а в логе остаётся честная причина. И что провайдер
mock не выдумывает того, чего не видел.
"""

import json
import subprocess
import tempfile
import unittest
from unittest import mock

from city import config as config_mod
from city.brain import Brain, _extract_json, _parse_reply

CONFIG = {
    "flags": {"use_llm": True},
    "llm": {
        "provider": "mock",
        "base": "https://ai.sverk.tech/v1",
        "key_env": "TEST_KEY_NOT_SET",
        "model": "deepseek-v4-pro",
        "vlm_model": "gemma4-vlm",
        "timeout": 5,
        "advise_plan": True,
        "explain": True,
        "see": True,
        "confirm_fire": True,
    },
}

FACTS = {
    "fire": [4, 2],
    "level": 2,
    "tower": [1, 3],
    "candidates": [[3, 2], [4, 3]],
    "base_budget": 14,
}


def brain(**over):
    data = json.loads(json.dumps(CONFIG))
    data["llm"].update(over)
    return Brain(config_mod.Config(data))


def reply(content: str, finish: str = "stop") -> dict:
    return {"choices": [{"finish_reason": finish, "message": {"content": content}}]}


def curl_returns(stdout: str, code: int = 0):
    """Подменить curl: вернуть заданный вывод, не ходя в сеть."""
    return mock.Mock(returncode=code, stdout=stdout.encode("utf-8"), stderr=b"")


class TestMockProvider(unittest.TestCase):
    def test_plan_answer_is_structured(self):
        ans = brain().advise_plan(FACTS)
        self.assertTrue(ans.ok, ans.error)
        self.assertEqual(ans.data["approach"], [3, 2])
        self.assertEqual(ans.data["charge_budget"], 14)
        self.assertTrue(ans.text)

    def test_mock_never_touches_the_network(self):
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("сеть")):
            self.assertTrue(brain().advise_plan(FACTS).ok)
            self.assertTrue(brain().explain("тема", {"a": 1}).ok)

    def test_mock_refuses_to_look_at_a_picture(self):
        """Провайдер без глаз обязан отказаться, а не «увидеть» человека."""
        ans = brain().see_person(b"\xff\xd8jpeg", (4, 2))
        self.assertFalse(ans.ok)
        self.assertIn("не выдумывает", ans.error)
        self.assertFalse(ans.data)

    def test_mock_without_candidates_says_so(self):
        ans = brain().advise_plan({"base_budget": 3})
        self.assertFalse(ans.ok)
        self.assertIn("клетки подъезда", ans.error)

    def test_model_name_is_reported_honestly(self):
        self.assertEqual(brain().advise_plan(FACTS).model, "mock")
        self.assertEqual(brain(provider="sverk").name("see"), "gemma4-vlm")
        self.assertEqual(brain(provider="sverk").name("plan"), "deepseek-v4-pro")


class TestSwitches(unittest.TestCase):
    def test_disabled_by_the_main_flag(self):
        data = json.loads(json.dumps(CONFIG))
        data["flags"]["use_llm"] = False
        off = Brain(config_mod.Config(data))
        for use in ("plan", "explain", "see"):
            self.assertFalse(off.wants(use))

    def test_each_use_switches_off_separately(self):
        b = brain(see=False)
        self.assertTrue(b.wants("plan"))
        self.assertFalse(b.wants("see"))


class TestFailuresAreSurvivable(unittest.TestCase):
    """Ни один сбой чужого сервера не имеет права стать исключением у нас."""

    def test_missing_key_is_explained(self):
        ans = brain(provider="sverk").advise_plan(FACTS)
        self.assertFalse(ans.ok)
        self.assertIn("TEST_KEY_NOT_SET", ans.error)

    def test_unknown_provider(self):
        ans = brain(provider="ollama").explain("тема", {})
        self.assertFalse(ans.ok)
        self.assertIn("неизвестный провайдер", ans.error)

    def test_internal_crash_becomes_an_answer(self):
        with mock.patch("city.brain._mock_reply", side_effect=RuntimeError("бум")):
            ans = brain().explain("тема", {})
        self.assertFalse(ans.ok)
        self.assertIn("бум", ans.error)


class TestRemoteTransport(unittest.TestCase):
    """Ветка живого шлюза, но без сети: curl подменён."""

    def setUp(self):
        self.env = mock.patch.dict("os.environ", {"TEST_KEY_NOT_SET": "ключ"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.brain = brain(provider="sverk")

    def test_good_answer(self):
        body = json.dumps(reply(json.dumps({"reason": "потому что"}))) + "\n200"
        with mock.patch.object(subprocess, "run", return_value=curl_returns(body)) as run:
            ans = self.brain.explain("тема", {"a": 1})
        self.assertTrue(ans.ok, ans.error)
        self.assertEqual(ans.text, "потому что")
        run.assert_called_once()

    def test_thinking_mode_is_diagnosed(self):
        body = json.dumps(reply("рассуждаю вслух", finish="length")) + "\n200"
        with mock.patch.object(subprocess, "run", return_value=curl_returns(body)):
            ans = self.brain.explain("тема", {})
        self.assertFalse(ans.ok)
        self.assertIn("лимит токенов", ans.error)

    def test_thinking_is_switched_off_every_way_the_gateway_knows(self):
        """Без «reasoning: enabled=false» deepseek тратит весь лимит на размышления."""
        body = json.dumps(reply(json.dumps({"reason": "коротко"}))) + "\n200"
        with mock.patch.object(subprocess, "run", return_value=curl_returns(body)) as run:
            self.brain.explain("тема", {})
        payload = json.loads(run.call_args.kwargs["input"].decode("utf-8"))
        self.assertEqual(payload["reasoning"], {"enabled": False})
        self.assertFalse(payload["enable_thinking"])

    def test_client_error_is_not_retried(self):
        body = '{"error": "bad key"}\n401'
        with mock.patch.object(subprocess, "run", return_value=curl_returns(body)) as run:
            ans = self.brain.explain("тема", {})
        self.assertFalse(ans.ok)
        self.assertIn("401", ans.error)
        run.assert_called_once()  # повторять отказ по существу бессмысленно

    def test_server_error_is_retried_once(self):
        body = "упал\n503"
        with mock.patch.object(subprocess, "run", return_value=curl_returns(body)) as run:
            ans = self.brain.explain("тема", {})
        self.assertFalse(ans.ok)
        self.assertIn("503", ans.error)
        self.assertEqual(run.call_count, 2)

    def test_timeout(self):
        with mock.patch.object(
            subprocess, "run", side_effect=subprocess.TimeoutExpired("curl", 5)
        ):
            ans = self.brain.explain("тема", {})
        self.assertFalse(ans.ok)
        self.assertIn("не ответила", ans.error)

    def test_no_curl_on_the_machine(self):
        with mock.patch.object(subprocess, "run", side_effect=FileNotFoundError):
            ans = self.brain.explain("тема", {})
        self.assertFalse(ans.ok)
        self.assertIn("curl", ans.error)

    def test_garbage_instead_of_json(self):
        with mock.patch.object(subprocess, "run", return_value=curl_returns("<html>\n200")):
            ans = self.brain.explain("тема", {})
        self.assertFalse(ans.ok)
        self.assertIn("не JSON", ans.error)

    def test_picture_goes_as_data_url(self):
        body = json.dumps(reply(json.dumps({"fire": False, "confidence": 0.1, "note": "-"}))) + "\n200"
        with mock.patch.object(subprocess, "run", return_value=curl_returns(body)) as run:
            ans = self.brain.see_fire(b"\xff\xd8jpeg")
        self.assertTrue(ans.ok, ans.error)
        payload = json.loads(run.call_args.kwargs["input"].decode("utf-8"))
        self.assertEqual(payload["model"], "gemma4-vlm")
        parts = payload["messages"][-1]["content"]
        self.assertTrue(parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))

    def test_thinking_is_switched_off_in_the_payload(self):
        body = json.dumps(reply(json.dumps({"reason": "-"}))) + "\n200"
        with mock.patch.object(subprocess, "run", return_value=curl_returns(body)) as run:
            self.brain.explain("тема", {})
        payload = json.loads(run.call_args.kwargs["input"].decode("utf-8"))
        self.assertFalse(payload["enable_thinking"])
        self.assertFalse(payload["chat_template_kwargs"]["enable_thinking"])
        # Схема принуждается грамматикой, а не просьбой ответить JSON-ом.
        self.assertEqual(payload["response_format"]["type"], "json_schema")


class TestVisionBranches(unittest.TestCase):
    """VLM по кадрам в диспетчере: что попадает в лог и чего там быть не должно."""

    def dispatcher(self, tmp: str, **over):
        from city.clock import SimClock
        from city.dispatcher import Dispatcher
        from city.field import Field
        from city.log import Log
        from city.robots.fleet import build_fleet

        cfg = config_mod.load()
        cfg.override("flags.use_llm", True)
        for key, value in over.items():
            cfg.override(f"llm.{key}", value)
        clock = SimClock()
        log = Log(clock, run_dir=tmp, echo=False)
        fleet = build_fleet(cfg, clock)
        disp = Dispatcher(cfg, Field.from_config(cfg), log, clock, fleet)
        return disp, log

    def events(self, log):
        log.close()
        with open(log.path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def with_shot(self, disp, tmp: str) -> None:
        path = tmp + "/shot.jpg"
        with open(path, "wb") as fh:
            fh.write(b"\xff\xd8jpeg")
        disp.fire_shot = path

    def test_person_is_reported_with_its_source_and_model(self):
        answer = mock.Mock(
            use="see", model="gemma4-vlm", ok=True, ms=120, text="человек у окна",
            data={"person": True, "confidence": 0.71, "note": "человек у окна"},
        )
        with tempfile.TemporaryDirectory() as tmp:
            disp, log = self.dispatcher(tmp)
            self.with_shot(disp, tmp)
            with mock.patch.object(disp.brain, "see_person", return_value=answer):
                disp._person_by_monitor()
            events = self.events(log)
        found = next(e for e in events if e["type"] == "PERSON_FOUND")
        self.assertTrue(found["found"])
        self.assertEqual(found["source"], "monitor")
        self.assertEqual(found["model"], "gemma4-vlm")
        self.assertIn("надёжность ниже", found["reason"])

    def test_a_silent_model_does_not_invent_a_detection(self):
        answer = mock.Mock(use="see", model="gemma4-vlm", ok=False, ms=30, text="", data={},
                           error="шлюз отказал")
        with tempfile.TemporaryDirectory() as tmp:
            disp, log = self.dispatcher(tmp)
            self.with_shot(disp, tmp)
            with mock.patch.object(disp.brain, "see_person", return_value=answer):
                disp._person_by_monitor()
            events = self.events(log)
        found = next(e for e in events if e["type"] == "PERSON_FOUND")
        self.assertIsNone(found["found"])
        self.assertIn("не выдумываем", found["reason"])

    def test_without_a_frame_nothing_is_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            disp, log = self.dispatcher(tmp)
            disp._person_by_monitor()  # кадра нет — показывать нечего
            events = self.events(log)
        self.assertFalse([e for e in events if e["type"] == "PERSON_FOUND"])

    def test_confirmed_fire_is_a_second_opinion_only(self):
        """Уверенную находку зрения переспрашивать незачем, спорную — стоит."""
        from city.vision import Scene

        answer = mock.Mock(use="see", model="gemma4-vlm", ok=True, ms=90, text="да",
                           data={"fire": True, "confidence": 0.8, "note": "красная фигурка"})
        with tempfile.TemporaryDirectory() as tmp:
            disp, log = self.dispatcher(tmp)
            self.with_shot(disp, tmp)
            with mock.patch.object(disp.brain, "see_fire", return_value=answer) as ask:
                disp.confirm_fire(Scene(fire_cell=(4, 2), votes=3, total=3))
                self.assertEqual(ask.call_count, 0)  # три согласных кадра — вопросов нет
                disp.confirm_fire(Scene(fire_cell=(4, 2), votes=1, total=1))
                self.assertEqual(ask.call_count, 1)
            events = self.events(log)
        call = next(e for e in events if e["type"] == "LLM")
        self.assertTrue(call["accepted"])
        self.assertIn("Клетку всё равно считает", call["reason"])


class TestReplyParsing(unittest.TestCase):
    def test_json_in_a_fence(self):
        self.assertEqual(_extract_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_json_after_chatter(self):
        self.assertEqual(_extract_json('Вот ответ: {"a": 1}. Готово'), {"a": 1})

    def test_not_an_object(self):
        self.assertIsNone(_extract_json("[1, 2]"))
        self.assertIsNone(_extract_json("совсем не json"))

    def test_body_without_choices(self):
        data, error = _parse_reply({"error": "oops"})
        self.assertIsNone(data)
        self.assertIn("choices", error)


if __name__ == "__main__":
    unittest.main()
