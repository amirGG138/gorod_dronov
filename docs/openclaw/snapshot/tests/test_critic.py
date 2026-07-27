"""Unit tests for the VLM-critic's pure parts: raster + heuristic scoring.

Run:  python3 -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))

from raster import BG, canvas_stats, hex2rgb, png_bytes, render_events  # noqa: E402


def _square(color="#ff0000", z=1, fill=True, alpha=1.0, a=10, b=60):
    poly = [[a, a], [b, a], [b, b], [a, b], [a, a]]
    return {"kind": "shape", "color": color, "z": z, "alpha": alpha,
            "fill": fill, "polys": [poly]}


class TestRaster(unittest.TestCase):
    def test_empty_canvas_is_background(self):
        img = render_events([], 120, 120, px=60)
        st = canvas_stats(img)
        self.assertEqual(st["painted_px"], 0)
        self.assertEqual(st["coverage"], 0.0)

    def test_filled_square_paints_pixels(self):
        img = render_events([_square()], 120, 120, px=60)
        st = canvas_stats(img)
        self.assertGreater(st["coverage"], 0.10)
        self.assertGreaterEqual(st["colors"], 1)

    def test_z_order_composites_last_on_top(self):
        red_then_blue = render_events(
            [_square("#ff0000", z=1), _square("#0000ff", z=2)], 120, 120, px=60)
        centre = red_then_blue[17][17]  # внутри квадрата
        self.assertGreater(centre[2], centre[0], "верхний (синий) слой должен победить")

    def test_stroke_events_render(self):
        e = {"kind": "stroke", "color": "#00ff00",
             "points": [[0, 0], [119, 119]]}
        st = canvas_stats(render_events([e], 120, 120, px=60))
        self.assertGreater(st["painted_px"], 30)

    def test_png_bytes_valid_header(self):
        img = render_events([_square()], 120, 120, px=32)
        data = png_bytes(img)
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIn(b"IEND", data)

    def test_hex2rgb(self):
        self.assertEqual(hex2rgb("#ff8000"), (255, 128, 0))
        self.assertEqual(hex2rgb("#f80"), (255, 136, 0))
        self.assertEqual(hex2rgb("мусор"), (204, 204, 204))

    def test_alpha_blend_partial(self):
        img = render_events([_square("#ffffff", alpha=0.5)], 120, 120, px=60)
        c = img[17][17]
        self.assertTrue(all(BG[i] < c[i] < 255 for i in range(3)))


class TestHeuristic(unittest.TestCase):
    def _score(self, coverage, colors=4, balance=0.8, ticks=1):
        # воспроизводим формулу критика без ctx: копия инварианта «больше
        # покрытие/разнообразие -> не меньше балл» проверяется через raster+critic
        from roles import critic
        critic._T["ticks"] = ticks

        class _BB:
            @staticmethod
            def read_decision():
                return {"subject": "тест"}

        class _Ctx:
            agent_id = "critic"
            bb = _BB()

        s, _ = critic._heuristic(_Ctx(), {"coverage": coverage, "colors": colors,
                                          "balance": balance}, final=False)
        return s

    def test_score_grows_with_coverage(self):
        self.assertLess(self._score(0.02), self._score(0.7))

    def test_score_bounds(self):
        for cov in (0.0, 0.5, 1.0):
            s = self._score(cov)
            self.assertTrue(1 <= s <= 100)

    def test_deterministic_per_tick(self):
        self.assertEqual(self._score(0.4, ticks=7), self._score(0.4, ticks=7))


if __name__ == "__main__":
    unittest.main()
