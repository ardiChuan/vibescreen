#!/usr/bin/env python3
"""Bridge tests that need no Bluetooth radio and no phone.

Everything worth getting wrong here is testable over a plain socketpair: the
framing (which is what silently truncates a 3.5 KB agent-status body if it is
wrong) and the path allowlist (which is the bridge's entire security value).
"""
import json
import socket
import struct
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bt_bridge  # noqa: E402


class _Stub(BaseHTTPRequestHandler):
    """Stands in for the tokenserver."""

    def log_message(self, format, *args):  # noqa: A002 - base signature
        pass

    def _reply(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/agent-status":
            # Deliberately large: a framing bug shows up here and nowhere else.
            self._reply(200, {"v": 2, "seq": 1, "agents": {},
                              "filler": "x" * 4000})
        elif self.path == "/api/tokens":
            self._reply(200, {"v": 2, "dayTokens": 1})
        else:
            self._reply(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        sent = json.loads(self.rfile.read(length) or b"{}")
        if self.path.startswith("/api/interaction/"):
            # Echo the verdict so the test can prove the body survived intact.
            self._reply(200, {"ok": True, "verdict": sent.get("verdict")})
        else:
            self._reply(409, {"ok": False, "reason": "signature rejected"})


class FrameTests(unittest.TestCase):
    def test_roundtrip_over_a_real_socket(self):
        a, b = socket.socketpair()
        try:
            bt_bridge.write_frame(a, {"method": "GET", "path": "/api/tokens"})
            self.assertEqual(
                bt_bridge.read_frame(b), {"method": "GET", "path": "/api/tokens"})
        finally:
            a.close()
            b.close()

    def test_large_payload_survives_short_reads(self):
        """The case that matters: a body far past one recv()."""
        a, b = socket.socketpair()
        try:
            payload = {"body": "y" * 60000}
            threading.Thread(
                target=bt_bridge.write_frame, args=(a, payload), daemon=True).start()
            self.assertEqual(bt_bridge.read_frame(b), payload)
        finally:
            a.close()
            b.close()

    def test_two_frames_back_to_back_do_not_merge(self):
        a, b = socket.socketpair()
        try:
            bt_bridge.write_frame(a, {"n": 1})
            bt_bridge.write_frame(a, {"n": 2})
            self.assertEqual(bt_bridge.read_frame(b), {"n": 1})
            self.assertEqual(bt_bridge.read_frame(b), {"n": 2})
        finally:
            a.close()
            b.close()

    def test_absurd_length_is_refused_before_allocating(self):
        a, b = socket.socketpair()
        try:
            a.sendall(struct.pack(">I", bt_bridge.MAX_FRAME + 1))
            with self.assertRaises(ValueError):
                bt_bridge.read_frame(b)
        finally:
            a.close()
            b.close()

    def test_truncated_frame_raises_rather_than_returning_partial_json(self):
        a, b = socket.socketpair()
        try:
            a.sendall(struct.pack(">I", 100) + b"{}")
            a.close()
            with self.assertRaises((ConnectionError, OSError)):
                bt_bridge.read_frame(b)
        finally:
            b.close()


class AllowlistTests(unittest.TestCase):
    def test_panel_paths_allowed(self):
        for path in ("/", "/api/tokens", "/api/agent-status",
                     "/api/max-tracker", "/api/github"):
            self.assertTrue(bt_bridge.path_allowed("GET", path), path)

    def test_no_write_route_exists_at_all(self):
        """The panel is informational, so nothing may be POSTed through here."""
        for path in ("/api/interaction/abc", "/api/panic", "/api/tokens",
                     "/api/hook/permission", "/"):
            self.assertFalse(bt_bridge.path_allowed("POST", path), path)

    def test_hook_routes_are_not_reachable_over_bluetooth(self):
        """These are loopback-only on the server; the bridge must not widen them."""
        for path in ("/api/hook/question", "/api/hook/permission",
                     "/api/codex/question", "/api/codex/permission"):
            self.assertFalse(bt_bridge.path_allowed("POST", path), path)

    def test_method_and_shape_confusion_is_refused(self):
        self.assertFalse(bt_bridge.path_allowed("GET", "/api/panic"))
        self.assertFalse(bt_bridge.path_allowed("DELETE", "/api/tokens"))
        self.assertFalse(bt_bridge.path_allowed("GET", "/../secrets.h"))


class ForwardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Stub)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_get_is_forwarded_verbatim(self):
        result = bt_bridge.forward(
            self.base, {"method": "GET", "path": "/api/tokens"})
        self.assertEqual(result["status"], 200)
        self.assertEqual(json.loads(result["body"])["dayTokens"], 1)

    def test_large_body_is_forwarded_whole(self):
        result = bt_bridge.forward(
            self.base, {"method": "GET", "path": "/api/agent-status"})
        self.assertEqual(result["status"], 200)
        self.assertEqual(len(json.loads(result["body"])["filler"]), 4000)

    def test_an_answer_never_reaches_the_server(self):
        """Even a well-formed answer is refused before the HTTP call."""
        result = bt_bridge.forward(self.base, {
            "method": "POST", "path": "/api/interaction/abc",
            "body": json.dumps({"verdict": "approve", "ts": 1, "hmac": "ff"}),
        })
        self.assertEqual(result["status"], 403)

    def test_blocked_path_never_reaches_the_server(self):
        result = bt_bridge.forward(
            self.base, {"method": "POST", "path": "/api/hook/question", "body": "{}"})
        self.assertEqual(result["status"], 403)

    def test_unreachable_server_is_reported_not_raised(self):
        result = bt_bridge.forward(
            "http://127.0.0.1:1", {"method": "GET", "path": "/api/tokens"})
        self.assertEqual(result["status"], 0)
        self.assertIn("error", json.loads(result["body"]))


if __name__ == "__main__":
    unittest.main()
