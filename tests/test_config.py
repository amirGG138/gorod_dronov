import unittest

from city import config as config_mod
from city.config import Config, ConfigError, parse_mini_yaml


class TestMiniYaml(unittest.TestCase):
    """Фолбэк-парсер обязан читать наш config.yaml так же, как PyYAML.

    Если он начнёт расходиться, на площадке без интернета мы получим тихо
    другую конфигурацию — худший вид отказа из возможных.
    """

    def test_matches_pyyaml_on_the_real_config(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML не установлен, сверять не с чем")
        with open(config_mod.CONFIG_PATH, encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual(parse_mini_yaml(text), yaml.safe_load(text))

    def test_scalars(self):
        data = parse_mini_yaml(
            "a: 1\n"
            "b: 0.8\n"
            "c: true\n"
            "d: false\n"
            "e: строка\n"
            'f: "в кавычках"\n'
        )
        self.assertEqual(data, {"a": 1, "b": 0.8, "c": True, "d": False, "e": "строка", "f": "в кавычках"})

    def test_nested_and_lists(self):
        data = parse_mini_yaml("field:\n  size: [6, 6]\n  pads: [[1, 1], [4, 4]]\n")
        self.assertEqual(data, {"field": {"size": [6, 6], "pads": [[1, 1], [4, 4]]}})

    def test_comment_inside_quotes_survives(self):
        self.assertEqual(parse_mini_yaml('color: "#00FF00"  # зелёный'), {"color": "#00FF00"})

    def test_unknown_syntax_fails_loudly(self):
        with self.assertRaises(ConfigError):
            parse_mini_yaml("pads:\n  - [1, 1]\n  - [4, 4]\n")

    def test_url_with_a_colon_stays_whole(self):
        """Адрес шлюза содержит «:» — разделитель ключа берётся только первый."""
        data = parse_mini_yaml("llm:\n  base: https://ai.sverk.tech/v1\n")
        self.assertEqual(data["llm"]["base"], "https://ai.sverk.tech/v1")


class TestConfigAccess(unittest.TestCase):
    def setUp(self):
        self.cfg = config_mod.load()

    def test_dotted_access(self):
        self.assertEqual(list(self.cfg.field.size), [6, 6])
        self.assertEqual(self.cfg.get("rules.water_dwell"), 3.0)
        self.assertIsNone(self.cfg.get("nothing.here"))

    def test_override(self):
        self.cfg.override("scenario.fire.level", 3)
        self.assertEqual(self.cfg.scenario.fire.level, 3)

    def test_missing_key_is_an_error(self):
        with self.assertRaises(AttributeError):
            _ = self.cfg.nope

    def test_defaults_match_the_regulations(self):
        self.assertEqual(self.cfg.get("rules.water_dwell"), 3.0)
        self.assertEqual(self.cfg.field.cell, 0.8)
        self.assertEqual(list(self.cfg.field.size), [6, 6])
        self.assertFalse(self.cfg.get("flags.use_vup"))  # микродрона у нас нет

    def test_llm_section_is_readable(self):
        # По умолчанию модель отвечает без сети: на площадке ключа может не быть,
        # и система обязана работать, а не молча притворяться.
        self.assertEqual(self.cfg.get("llm.provider"), "mock")
        self.assertEqual(self.cfg.get("llm.base"), "https://ai.sverk.tech/v1")
        self.assertEqual(self.cfg.get("llm.key_env"), "SVERK_API_KEY")
        # Таймаут с запасом на зрение: живой VLM смотрел на кадр 17-22 с (29.07.2026).
        self.assertEqual(self.cfg.get("llm.timeout"), 40)
        # Модели ограничены нашим ключом: qwen35 из docs/openclaw ему закрыт (403).
        self.assertEqual(self.cfg.get("llm.model"), "deepseek-v4-pro")
        self.assertEqual(self.cfg.get("llm.vlm_model"), "gemma4-vlm")
        self.assertFalse(self.cfg.get("flags.use_llm"))  # включается ключом --llm

    def test_pads_match_our_field_map(self):
        # docs/field-map/map.txt: id 50/60/62/7, сторона 0,25 м, DICT_4X4_1000
        self.assertEqual(self.cfg.aruco.size, 0.25)
        self.assertEqual(self.cfg.aruco.dict, "DICT_4X4_1000")
        pads = {k: list(v) for k, v in self.cfg.aruco.pads.items()}
        self.assertEqual(pads, {"50": [1, 4], "60": [4, 4], "62": [1, 1], "7": [4, 1]})


if __name__ == "__main__":
    unittest.main()
