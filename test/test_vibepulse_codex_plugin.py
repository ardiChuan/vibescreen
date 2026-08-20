#!/usr/bin/env python3
"""Security and transcript tests for the local VibePulse Codex bridge."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".agents/plugins/plugins/vibepulse/scripts"
MAX_HOOK_INPUT = 64 * 1024

PERMISSION = {
    "hook_event_name": "PermissionRequest",
    "session_id": "session-123",
    "turn_id": "turn-456",
    "cwd": "/tmp/project",
    "tool_name": "Read",
    "tool_input": {"path": "README.md"},
}
ALLOW = {
    "hookSpecificOutput": {
        "hookEventName": "PermissionRequest",
        "decision": {"behavior": "allow"},
    }
}
DENY = {
    "hookSpecificOutput": {
        "hookEventName": "PermissionRequest",
        "decision": {
            "behavior": "deny",
            "message": "Denied from VibePulse",
        },
    }
}
QUESTION = {
    "question": "How should Codex handle approvals?",
    "header": "Approvals",
    "options": [
        {
            "label": "Use the trusted hook",
            "description": "Desktop and CLI",
            "recommended": True,
        },
        {"label": "Keep computer only", "description": "No panel decisions"},
    ],
}


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.requests.append((self.path, dict(self.headers), body))
        behavior = self.server.behavior
        if behavior.get("delay_headers"):
            time.sleep(behavior["delay_headers"])
        status = behavior.get("status", 200)
        payload = behavior.get("body", b"{}")
        self.send_response(status)
        if "location" in behavior:
            self.send_header("Location", behavior["location"])
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        first = behavior.get("first_bytes")
        if first is not None:
            self.wfile.write(payload[:first])
            self.wfile.flush()
            time.sleep(behavior.get("delay_body", 0))
            self.wfile.write(payload[first:])
        else:
            if behavior.get("delay_body"):
                time.sleep(behavior["delay_body"])
            self.wfile.write(payload)

    def log_message(self, _format, *_args):
        pass


class LocalServer:
    def __init__(self, **behavior):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.behavior = behavior
        self.httpd.requests = []
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def port(self):
        return self.httpd.server_address[1]

    @property
    def requests(self):
        return self.httpd.requests

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)


def closed_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def run_script(name, stdin=b"", *, port=None, env=None, timeout=4):
    process_env = os.environ.copy()
    for key in tuple(process_env):
        if key.lower().endswith("_proxy") or key.lower() == "no_proxy":
            process_env.pop(key)
    if port is not None:
        process_env["VIBEPULSE_PORT"] = str(port)
    if env:
        process_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name)], input=stdin,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=process_env,
        cwd=ROOT, timeout=timeout, check=False,
    )


def rpc(method, request_id=1, params=None):
    value = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        value["params"] = params
    return value


def run_mcp(messages, *, port=None, env=None):
    wire = b"".join(
        message if isinstance(message, bytes)
        else compact(message).encode("utf-8") + b"\n"
        for message in messages
    )
    completed = run_script("mcp_server.py", wire, port=port, env=env)
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    return completed, responses


def load_loopback():
    path = SCRIPTS / "loopback.py"
    spec = importlib.util.spec_from_file_location("vibepulse_loopback_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LoopbackTests(unittest.TestCase):
    def test_url_parser_accepts_only_explicit_canonical_loopback_http(self):
        loopback = load_loopback()
        accepted = (
            "http://127.0.0.1:8737/api",
            "http://127.255.2.3:1/api",
            "http://localhost:65535/api",
            "http://localhost.:8737/api",
            "http://[::1]:8737/api",
        )
        rejected = (
            "https://127.0.0.1:8737/api",
            "http://127.0.0.1/api",
            "http://user@127.0.0.1:8737/api",
            "http://127.0.0.1:8737/api#fragment",
            "http://127.0.0.1:8737/api?query=1",
            "http://example.com:8737/api",
            "http://127.0.0.1.example:8737/api",
            "http://127.1:8737/api",
            "http://2130706433:8737/api",
            "http://0x7f000001:8737/api",
            "http://[::1%25lo0]:8737/api",
            "http://127.0.0.1:0/api",
            "http://127.0.0.1:65536/api",
            "http://127.0.0.1:notaport/api",
            "http:///api",
        )
        for url in accepted:
            with self.subTest(url=url):
                self.assertTrue(loopback.is_loopback_http_url(url))
        for url in rejected:
            with self.subTest(url=url):
                self.assertFalse(loopback.is_loopback_http_url(url))

    def test_post_uses_compact_json_content_type_and_no_proxy(self):
        loopback = load_loopback()
        response = compact({"ok": True}).encode()
        with LocalServer(body=response) as target, LocalServer(body=b"{}") as proxy:
            old_proxy = os.environ.get("HTTP_PROXY")
            os.environ["HTTP_PROXY"] = f"http://127.0.0.1:{proxy.port}"
            try:
                result = loopback.post_json(
                    f"http://127.0.0.1:{target.port}/api", {"word": "räv"})
            finally:
                if old_proxy is None:
                    os.environ.pop("HTTP_PROXY", None)
                else:
                    os.environ["HTTP_PROXY"] = old_proxy
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(proxy.requests), 0)
        path, headers, body = target.requests[0]
        self.assertEqual(path, "/api")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(body, compact({"word": "räv"}).encode("utf-8"))

    def test_request_and_response_caps_are_limit_plus_one(self):
        loopback = load_loopback()
        with LocalServer(body=b"{}") as server:
            base = f"http://127.0.0.1:{server.port}/api"
            self.assertEqual(loopback.post_json(base, {"x": "a" * 4088}), {})
            self.assertIsNone(loopback.post_json(base, {"x": "a" * 4089}))
            self.assertEqual(len(server.requests), 1)
        exact = compact({"x": "a" * 4088}).encode()
        oversized = compact({"x": "a" * 4089}).encode()
        self.assertEqual(len(exact), 4096)
        with LocalServer(body=exact) as server:
            self.assertEqual(loopback.post_json(
                f"http://127.0.0.1:{server.port}/api", {}),
                {"x": "a" * 4088})
        with LocalServer(body=oversized) as server:
            self.assertIsNone(loopback.post_json(
                f"http://127.0.0.1:{server.port}/api", {}))

    def test_connect_timeout_is_replaced_by_longer_read_timeout(self):
        loopback = load_loopback()
        with LocalServer(delay_headers=0.12, body=b'{"ok":true}') as server:
            started = time.monotonic()
            result = loopback.post_json(
                f"http://127.0.0.1:{server.port}/api", {},
                connect_timeout=0.03, read_timeout=0.5)
        self.assertEqual(result, {"ok": True})
        self.assertGreaterEqual(time.monotonic() - started, 0.1)

    def test_read_timeout_and_bad_responses_return_none(self):
        loopback = load_loopback()
        with LocalServer(body=b'{"ok":true}', first_bytes=1,
                         delay_body=0.2) as server:
            started = time.monotonic()
            result = loopback.post_json(
                f"http://127.0.0.1:{server.port}/api", {}, read_timeout=0.04)
        self.assertIsNone(result)
        self.assertLess(time.monotonic() - started, 1.5)
        for body in (b"\xff", b"{", b"[]", b'{"x":NaN}',
                     b'{"x":1,"x":2}'):
            with self.subTest(body=body), LocalServer(body=body) as server:
                self.assertIsNone(loopback.post_json(
                    f"http://127.0.0.1:{server.port}/api", {}))

    def test_foreign_redirect_is_rejected_without_dns_lookup(self):
        loopback = load_loopback()
        with LocalServer(status=302, body=b"", location="http://example.invalid/x") as server:
            self.assertIsNone(loopback.post_json(
                f"http://127.0.0.1:{server.port}/api", {}))
        self.assertEqual(len(server.requests), 1)


class PermissionHookTests(unittest.TestCase):
    def test_allow_and_deny_are_forwarded_semantically_unchanged(self):
        for decision in (ALLOW, DENY):
            with self.subTest(decision=decision), LocalServer(
                    body=compact(decision).encode()) as server:
                completed = run_script(
                    "permission_hook.py", compact(PERMISSION).encode(),
                    port=server.port)
                self.assertEqual(completed.returncode, 0)
                self.assertEqual(json.loads(completed.stdout), decision)
                self.assertEqual(completed.stderr, b"")
                path, headers, body = server.requests[0]
                self.assertEqual(path, "/api/codex/permission")
                self.assertEqual(headers["Content-Type"], "application/json")
                self.assertEqual(json.loads(body), PERMISSION)

    def test_invalid_port_fails_silent_without_using_default(self):
        for port in ("", "0", "65536", "+8737", " 8737", "eight"):
            with self.subTest(port=port):
                completed = run_script(
                    "permission_hook.py", compact(PERMISSION).encode(),
                    env={"VIBEPULSE_PORT": port})
                self.assertEqual((completed.returncode, completed.stdout), (0, b""))

    def test_invalid_or_oversized_input_is_empty_success(self):
        invalid = (b"", b"\xff", b"{", b"[]", b"{} trailing",
                   b" " * (MAX_HOOK_INPUT + 1))
        for body in invalid:
            with self.subTest(size=len(body)):
                completed = run_script("permission_hook.py", body,
                                       port=closed_port())
                self.assertEqual((completed.returncode, completed.stdout), (0, b""))

    def test_nonstandard_or_duplicate_json_never_reaches_http(self):
        with LocalServer(body=compact(ALLOW).encode()) as server:
            for body in (b'{"value":NaN}', b'{"value":1,"value":2}'):
                with self.subTest(body=body):
                    completed = run_script("permission_hook.py", body,
                                           port=server.port)
                    self.assertEqual((completed.returncode, completed.stdout),
                                     (0, b""))
        self.assertEqual(server.requests, [])

    def test_transport_http_and_response_failures_are_empty_success(self):
        completed = run_script("permission_hook.py", compact(PERMISSION).encode(),
                               port=closed_port())
        self.assertEqual((completed.returncode, completed.stdout), (0, b""))
        bad_responses = (
            {"status": 500, "body": b"{}"},
            {"body": b"\xff"},
            {"body": b"{"},
            {"body": b"[]"},
            {"body": b"{" + b" " * 4096 + b"}"},
            {"body": compact({"decision": "allow"}).encode()},
            {"body": compact({"hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "approve"}}}).encode()},
        )
        for behavior in bad_responses:
            with self.subTest(behavior=behavior), LocalServer(**behavior) as server:
                completed = run_script(
                    "permission_hook.py", compact(PERMISSION).encode(),
                    port=server.port)
                self.assertEqual((completed.returncode, completed.stdout), (0, b""))

    def test_timeout_and_foreign_redirect_are_empty_success(self):
        with LocalServer(delay_headers=0.2, body=compact(ALLOW).encode()) as server:
            completed = run_script(
                "permission_hook.py", compact(PERMISSION).encode(), port=server.port,
                env={"_VIBEPULSE_TEST_READ_TIMEOUT": "0.04"})
            self.assertEqual((completed.returncode, completed.stdout), (0, b""))
        with LocalServer(status=302, body=b"",
                         location="http://example.invalid/decision") as server:
            completed = run_script(
                "permission_hook.py", compact(PERMISSION).encode(), port=server.port)
            self.assertEqual((completed.returncode, completed.stdout), (0, b""))


class SessionStartTests(unittest.TestCase):
    def test_context_is_bounded_provider_correct_and_fail_safe(self):
        payload = {"hook_event_name": "SessionStart", "session_id": "s"}
        completed = run_script("session_start.py", compact(payload).encode())
        self.assertEqual(completed.returncode, 0)
        body = json.loads(completed.stdout)
        self.assertEqual(body["hookSpecificOutput"]["hookEventName"], "SessionStart")
        context = body["hookSpecificOutput"]["additionalContext"]
        self.assertLessEqual(len(context), 1400)
        self.assertIn("mcp__vibepulse__ask", context)
        self.assertIn("2–3 option questions", context)
        self.assertIn("request_user_input", context)
        self.assertIn("unavailable, times out, or reports computer fallback", context)
        self.assertIn("Never treat silence, panel absence, or fallback as approval", context)
        self.assertIn("Permission decisions remain subject to Codex policy", context)
        self.assertNotIn(str(ROOT), context)

    def test_invalid_or_oversized_input_is_empty_success(self):
        for body in (b"", b"\xff", b"[]", b"{", b'{"x":NaN}',
                     b'{"x":1,"x":2}', b" " * (MAX_HOOK_INPUT + 1)):
            with self.subTest(size=len(body)):
                completed = run_script("session_start.py", body)
                self.assertEqual((completed.returncode, completed.stdout), (0, b""))


class McpServerTests(unittest.TestCase):
    def test_initialize_notification_ping_and_list_protocol(self):
        messages = [
            rpc("initialize", 1, {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            }),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            rpc("ping", "ping-id"),
            rpc("tools/list", 3),
        ]
        completed, responses = run_mcp(messages)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, b"")
        self.assertEqual([r["id"] for r in responses], [1, "ping-id", 3])
        initialized = responses[0]["result"]
        self.assertEqual(initialized["protocolVersion"], "2025-06-18")
        self.assertEqual(initialized["serverInfo"]["name"], "vibepulse")
        self.assertEqual(initialized["capabilities"], {"tools": {"listChanged": False}})
        self.assertEqual(responses[1]["result"], {})
        tools = responses[2]["result"]["tools"]
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["name"], "ask")
        schema = tools[0]["inputSchema"]
        self.assertEqual(schema["required"], ["question", "options"])
        self.assertFalse(schema["additionalProperties"])
        options = schema["properties"]["options"]
        self.assertEqual((options["minItems"], options["maxItems"]), (2, 3))
        item = options["items"]
        self.assertEqual(item["required"], ["label"])
        self.assertFalse(item["additionalProperties"])
        self.assertEqual(item["properties"]["recommended"]["type"], "boolean")

    def test_initialize_rejects_unknown_or_control_bearing_fields(self):
        base = {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        }
        messages = [
            rpc("initialize", 1, {**base, "unknown": True}),
            rpc("initialize", 2, {**base,
                "clientInfo": {"name": "bad\u0001", "version": "1"}}),
        ]
        _, responses = run_mcp(messages)
        self.assertEqual([response["error"]["code"] for response in responses],
                         [-32602, -32602])

    def test_answered_call_returns_identical_text_and_structured_content(self):
        answered = {"status": "answered", "option_index": 0,
                    "answer": "Use the trusted hook"}
        with LocalServer(body=compact(answered).encode()) as server:
            completed, responses = run_mcp([
                rpc("tools/call", 7, {"name": "ask", "arguments": QUESTION})
            ], port=server.port, env={
                "VIBEPULSE_CWD": "/tmp/project",
                "VIBEPULSE_SESSION_ID": "session-123",
                "VIBEPULSE_TURN_ID": "turn-456",
            })
        self.assertEqual(completed.stderr, b"")
        result = responses[0]["result"]
        self.assertNotIn("isError", result)
        self.assertEqual(result["structuredContent"], answered)
        self.assertEqual(json.loads(result["content"][0]["text"]), answered)
        path, headers, body = server.requests[0]
        self.assertEqual(path, "/api/codex/question")
        self.assertEqual(headers["Content-Type"], "application/json")
        expected = dict(QUESTION)
        expected.update(cwd="/tmp/project", session_id="session-123",
                        turn_id="turn-456")
        self.assertEqual(json.loads(body), expected)

    def test_transport_and_invalid_server_response_use_explicit_computer_fallback(self):
        completed, responses = run_mcp([
            rpc("tools/call", 1, {"name": "ask", "arguments": QUESTION})
        ], port=closed_port())
        self.assertEqual(completed.returncode, 0)
        fallback = responses[0]["result"]["structuredContent"]
        self.assertEqual(fallback["status"], "computer")
        self.assertIn("request_user_input", fallback["instruction"])
        self.assertNotIn("approve", compact(fallback).lower())
        self.assertEqual(
            json.loads(responses[0]["result"]["content"][0]["text"]), fallback)
        for body in (b"[]", b"{", b"\xff", b"{" + b" " * 4096 + b"}"):
            with self.subTest(body=body), LocalServer(body=body) as server:
                _, responses = run_mcp([
                    rpc("tools/call", 1, {"name": "ask", "arguments": QUESTION})
                ], port=server.port)
                self.assertEqual(
                    responses[0]["result"]["structuredContent"]["status"],
                    "computer")

    def test_held_response_timeout_returns_computer_fallback_quickly(self):
        with LocalServer(delay_headers=0.6, body=b'{}') as server:
            started = time.monotonic()
            _, responses = run_mcp([
                rpc("tools/call", 1, {"name": "ask", "arguments": QUESTION})
            ], port=server.port,
               env={"_VIBEPULSE_TEST_READ_TIMEOUT": "0.04"})
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.4)
        self.assertEqual(
            responses[0]["result"]["structuredContent"]["status"], "computer")

    def test_invalid_tool_calls_are_errors_and_never_reach_http(self):
        bad_calls = (
            {"name": "other", "arguments": QUESTION},
            {"name": "ask", "arguments": []},
            {"name": "ask", "arguments": {**QUESTION, "extra": True}},
            {"name": "ask", "arguments": {**QUESTION, "question": " "}},
            {"name": "ask", "arguments": {**QUESTION, "question": "x" * 97}},
            {"name": "ask", "arguments": {**QUESTION, "question": "bad\u0001"}},
            {"name": "ask", "arguments": {**QUESTION, "options": [
                {"label": "Only"}]}},
            {"name": "ask", "arguments": {**QUESTION, "options": [
                {"label": "a", "recommended": True},
                {"label": "b", "recommended": True}]}},
            {"name": "ask", "arguments": {**QUESTION, "options": [
                {"label": "a", "unknown": 1}, {"label": "b"}]}},
            {"name": "ask", "arguments": {**QUESTION, "options": [
                {"label": "x" * 65}, {"label": "b"}]}},
        )
        with LocalServer(body=b'{}') as server:
            _, responses = run_mcp([
                rpc("tools/call", index, params)
                for index, params in enumerate(bad_calls)
            ], port=server.port)
        self.assertEqual(len(server.requests), 0)
        self.assertEqual(len(responses), len(bad_calls))
        self.assertTrue(all(response["result"]["isError"] for response in responses))

    def test_bad_params_unknown_methods_and_notifications_handle_ids_exactly(self):
        messages = [
            rpc("tools/list", 1, {"cursor": "not-supported"}),
            rpc("unknown", 2),
            {"jsonrpc": "2.0", "method": "unknown"},
            {"jsonrpc": "2.0", "method": "ping"},
            {"jsonrpc": "1.0", "id": 3, "method": "ping"},
            {"jsonrpc": "2.0", "id": {"bad": "id"}, "method": "ping"},
            {"jsonrpc": "2.0", "id": "bad\u0001", "method": "ping"},
            {"jsonrpc": "2.0", "id": 4, "method": "bad\u0001"},
        ]
        _, responses = run_mcp(messages)
        self.assertEqual(len(responses), 6)
        self.assertEqual(responses[0]["error"]["code"], -32602)
        self.assertEqual(responses[1]["error"]["code"], -32601)
        self.assertEqual(responses[2]["error"]["code"], -32600)
        self.assertIsNone(responses[2]["id"])
        self.assertEqual(responses[3]["error"]["code"], -32600)
        self.assertEqual(responses[4]["error"]["code"], -32600)
        self.assertEqual(responses[5]["error"]["code"], -32600)

    def test_bad_lines_are_bounded_and_server_survives_for_next_message(self):
        oversized = b'{' + b'"x":' + b'"' + b'a' * (MAX_HOOK_INPUT + 1) + b'"}\n'
        messages = [b"not json\n", b"\xff\n", b'{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}\n',
                    b'{"jsonrpc":"2.0","id":3,"method":"ping","params":NaN}\n',
                    oversized, rpc("ping", 9)]
        completed, responses = run_mcp(messages)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(len(responses), 6)
        self.assertTrue(all(r["error"]["code"] == -32600 for r in responses[:5]))
        self.assertEqual(responses[5], {"jsonrpc": "2.0", "id": 9, "result": {}})

    def test_deep_objects_context_overflow_and_secrets_never_reach_server_or_stdout(self):
        deep = {"label": "a"}
        for _ in range(20):
            deep = {"nested": deep}
        bad = dict(QUESTION)
        bad["options"] = [deep, {"label": "b"}]
        secret = "SECRET_MCP_NOISE_6f425c"
        with LocalServer(body=b"{}") as server:
            completed, responses = run_mcp([
                rpc("tools/call", 1, {"name": "ask", "arguments": bad}),
                rpc("tools/call", 2, {"name": "ask", "arguments": QUESTION}),
            ], port=server.port, env={
                "VIBEPULSE_CWD": "x" * 4097,
                "UNRELATED_SECRET": secret,
            })
        self.assertEqual(len(server.requests), 0)
        self.assertTrue(responses[0]["result"]["isError"])
        self.assertTrue(responses[1]["result"]["isError"])
        self.assertNotIn(secret.encode(), completed.stdout)
        self.assertEqual(completed.stderr, b"")

    def test_only_numeric_loopback_port_is_honored(self):
        for port in ("https://example.com", "0", "+8737", "65536"):
            completed, responses = run_mcp([
                rpc("tools/call", 1, {"name": "ask", "arguments": QUESTION})
            ], env={"VIBEPULSE_PORT": port})
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(
                responses[0]["result"]["structuredContent"]["status"],
                "computer")


if __name__ == "__main__":
    unittest.main()
