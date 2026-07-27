"""E2E for the PicoClaw MCP shim (drone/picoclaw_bridge_mcp.py) — no Go needed.

Spawns the shim as a real subprocess and speaks its newline JSON-RPC over stdio,
against an in-process HTTP server that plays BOTH the robot bridge and the hub:
  * tools/list exposes the flight AND the board tools;
  * flight tools proxy to the bridge endpoints (/move, /photograph, ...);
  * board tools hit the hub with the Bearer token and the agent identity —
    so a PicoClaw brain is a full citizen of the chat, not just a flyer;
  * without HUB_URL the board tools fail LOUDLY (no silent no-op).

Run:  python3 -m unittest tests.test_picoclaw_shim -v
"""
import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SHIM = Path(__file__).resolve().parents[1] / "drone" / "picoclaw_bridge_mcp.py"

REQS = []          # (method, path, headers-subset, body) seen by the fake server


class _Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def _record(self, body=None):
        REQS.append((self.command, self.path,
                     {"authorization": self.headers.get("authorization", "")},
                     body))

    def do_GET(self):
        self._record()
        out = {"phase": "DEBATE"} if "phase" in self.path else \
              ([{"from": "pilot-a", "type": "ROUTE", "body": "мой маршрут"}]
               if self.path == "/messages" else {"ok": True})
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n).decode() or "{}")
        self._record(body)
        data = json.dumps({"ok": True, "echo": body}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class _Shim:
    """One shim subprocess + a JSON-RPC conversation helper."""

    def __init__(self, env):
        self.p = subprocess.Popen([sys.executable, str(SHIM)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  env={**os.environ, **env}, text=True)
        self._id = 0

    def rpc(self, method, params=None):
        self._id += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self._id,
                                       "method": method,
                                       "params": params or {}}) + "\n")
        self.p.stdin.flush()
        return json.loads(self.p.stdout.readline())

    def call(self, name, args=None):
        return self.rpc("tools/call", {"name": name, "arguments": args or {}})

    def close(self):
        self.p.stdin.close()
        self.p.wait(timeout=5)


class TestPicoclawShim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        REQS.clear()

    def test_tools_list_has_flight_and_board(self):
        s = _Shim({"BRIDGE_URL": self.base})
        try:
            names = {t["name"] for t in
                     s.rpc("tools/list")["result"]["tools"]}
        finally:
            s.close()
        self.assertLessEqual({"fly_to", "photograph_cell", "analyze", "land",
                              "takeoff", "read_board", "post_message",
                              "report_progress", "emit_thought"}, names)

    def test_flight_tool_proxies_to_bridge(self):
        s = _Shim({"BRIDGE_URL": self.base})
        try:
            res = s.call("fly_to", {"cell": [1, 2]})
        finally:
            s.close()
        self.assertIn("result", res)
        self.assertIn(("POST", "/move"), [(m, p) for m, p, *_ in REQS])
        body = [b for m, p, h, b in REQS if p == "/move"][0]
        self.assertEqual(body, {"to": [1, 2]})

    def test_board_tools_use_hub_token_and_identity(self):
        s = _Shim({"BRIDGE_URL": self.base, "HUB_URL": self.base,
                   "HUB_TOKEN": "sekret", "AGENT_ID": "pilot-x"})
        try:
            s.call("post_message", {"type": "REBUTTAL", "to": "all",
                                    "body": "спорю"})
            s.call("emit_thought", {"text": "думаю вслух"})
            board = s.call("read_board", {"last": 5})
        finally:
            s.close()
        posted = [b for m, p, h, b in REQS if p == "/messages" and m == "POST"][0]
        self.assertEqual(posted["from"], "pilot-x")
        self.assertEqual(posted["type"], "REBUTTAL")
        auth = [h["authorization"] for m, p, h, b in REQS if m == "POST"]
        self.assertTrue(all(a == "Bearer sekret" for a in auth), auth)
        text = json.loads(board["result"]["content"][0]["text"])
        self.assertEqual(text["phase"], {"phase": "DEBATE"})
        self.assertTrue(text["messages"])

    def test_board_tools_fail_loudly_without_hub(self):
        s = _Shim({"BRIDGE_URL": self.base})
        try:
            res = s.call("post_message", {"type": "STATUS", "to": "all",
                                          "body": "hi"})
        finally:
            s.close()
        self.assertIn("error", res)
        self.assertIn("HUB_URL", res["error"]["message"])


if __name__ == "__main__":
    unittest.main()
