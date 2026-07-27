"""Opt-in survey commerce dashboard contract tests."""

from __future__ import annotations

import os
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@unittest.skipUnless(
    (ROOT / "viz" / "server.py").is_file(),
    "The minimal payment test image intentionally omits dashboard sources",
)
class SurveyCommerceDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.port = _free_port()
        environment = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "agent"),
            "BLACKBOARD": cls.temporary.name,
            "FIXTURES": str(ROOT / "test_fixtures"),
            "TASK": "survey",
            "SCENARIO": "survey-1",
            "PORT": str(cls.port),
        }
        cls.process = subprocess.Popen(
            [os.environ.get("PYTHON", "python"), str(ROOT / "viz" / "server.py")],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(50):
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{cls.port}/healthz", timeout=0.2
                ):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("viz test server did not start")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.process.terminate()
        cls.process.wait(timeout=3)
        cls.temporary.cleanup()

    def get(self, path: str) -> str:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{self.port}{path}", timeout=2
        ) as response:
            self.assertEqual(response.status, 200)
            return response.read().decode("utf-8")

    def test_combined_route_and_local_assets_exist(self) -> None:
        combined = self.get("/survey-commerce")
        script = self.get("/commerce-widget.js")
        style = self.get("/commerce-widget.css")

        self.assertIn("Поиск груза", combined)
        self.assertIn("commerce-widget.js", combined)
        self.assertIn("CommerceWidget", script)
        self.assertIn(".commerce-dock", style)

    def test_widget_is_opt_in_safe_and_easily_disabled(self) -> None:
        survey = self.get("/survey")
        script = self.get("/commerce-widget.js")

        self.assertIn('location.pathname==="/survey-commerce"', survey)
        self.assertIn('searchParams.get("commerce")!=="0"', survey)
        self.assertIn("CommerceWidget.mount", survey)
        self.assertIn("CommerceWidget.handle", survey)
        self.assertIn("commerce-widget-collapsed", script)
        self.assertIn("textContent", script)
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("iframe", script.lower())
        self.assertNotIn("/v1/", script)
        self.assertIn("root=dock", script)
        self.assertIn("main.append(root)", script)

    def test_widget_copy_explains_real_cryptographic_proof(self) -> None:
        script = self.get("/commerce-widget.js")

        for expected in (
            "AP2",
            "x402",
            "Anvil",
            "tx hash",
            "block",
            "gas",
            "Открыть Agent Commerce",
            "Скрыть",
        ):
            self.assertIn(expected, script)


if __name__ == "__main__":
    unittest.main()
