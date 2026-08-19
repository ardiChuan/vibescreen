import dataclasses
import json
import unittest

from tools.tokenserver import interactions
from tools.tokenserver.interaction_types import (
    InteractionProvider,
    InteractionResult,
)
from tools.tokenserver.codex_interactions import (
    codex_permission_response,
    codex_question_result,
    normalize_codex_permission,
    normalize_codex_question,
)


class InteractionTypeTests(unittest.TestCase):
    def test_result_is_provider_neutral_and_immutable(self):
        result = InteractionResult(verdict="approve", option_index=1)
        self.assertEqual(result.verdict, "approve")
        self.assertEqual(result.option_index, 1)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.verdict = "deny"

    def test_provider_wire_values_are_stable(self):
        self.assertEqual(InteractionProvider.CLAUDE.value, "claude")
        self.assertEqual(InteractionProvider.CODEX.value, "codex")

    def test_result_rejects_unsupported_verdict(self):
        with self.assertRaisesRegex(ValueError, "unsupported verdict"):
            InteractionResult(verdict="maybe")

    def test_result_rejects_negative_option_index(self):
        with self.assertRaisesRegex(ValueError, "negative option index"):
            InteractionResult(verdict="approve", option_index=-1)


def codex_question(**overrides):
    payload = {
        "question": "Which auth approach?",
        "header": "Auth",
        "options": [
            {"label": "Keep existing auth", "description": "Smaller change"},
            {"label": "New auth layer", "description": "Cleaner architecture",
             "recommended": True},
        ],
    }
    payload.update(overrides)
    return payload


def codex_permission(**overrides):
    event = {
        "hook_event_name": "PermissionRequest",
        "session_id": "session-123",
        "turn_id": "turn-456",
        "cwd": "/Users/niclas/vibepulse",
        "tool_name": "Read",
        "tool_input": {"command": "cat README.md"},
    }
    event.update(overrides)
    return event


class CodexNormalizationTests(unittest.TestCase):
    def normalize_question(self, payload=None):
        return normalize_codex_question(
            payload if payload is not None else codex_question(),
            cwd="/Users/niclas/vibepulse",
            session_id="session-123", turn_id="turn-456")

    def test_explicit_recommendation_has_a_safe_approvable_view(self):
        normalized = self.normalize_question()

        self.assertEqual(normalized["provider"], "codex")
        self.assertEqual(normalized["kind"], "question")
        self.assertEqual(normalized["project"], "vibepulse")
        self.assertEqual(normalized["recommended_index"], 1)
        self.assertEqual(normalized["view"], {
            "kind": "question", "options_total": 2, "marked": True,
            "prompt": "Which auth approach?", "title": "New auth layer",
            "subtitle": "Cleaner architecture", "can_approve": True,
        })
        self.assertNotIn("session_id", normalized["view"])
        self.assertNotIn("turn_id", normalized["view"])

    def test_unmarked_question_is_alert_only_without_a_guess(self):
        payload = codex_question(options=[
            {"label": "Keep existing auth", "description": "Smaller change"},
            {"label": "New auth layer", "description": "Cleaner architecture"},
        ])

        normalized = self.normalize_question(payload)

        self.assertIsNone(normalized["recommended_index"])
        self.assertEqual(normalized["view"], {
            "kind": "question", "options_total": 2, "marked": False,
            "prompt": "Which auth approach?", "can_approve": False,
        })

    def test_missing_description_is_accepted_as_no_subtitle(self):
        payload = codex_question(options=[
            {"label": "Keep existing auth"},
            {"label": "New auth layer", "recommended": True},
        ])

        normalized = self.normalize_question(payload)

        self.assertEqual(normalized["view"]["title"], "New auth layer")
        self.assertIsNone(normalized["view"]["subtitle"])

    def test_three_options_allow_one_explicit_recommendation(self):
        normalized = self.normalize_question(codex_question(options=[
            {"label": "first"},
            {"label": "second", "recommended": True},
            {"label": "third"},
        ]))

        self.assertEqual(normalized["recommended_index"], 1)
        self.assertEqual(normalized["view"]["options_total"], 3)
        self.assertTrue(normalized["view"]["can_approve"])

    def test_question_requires_question_and_options_separately(self):
        missing_question = codex_question()
        missing_question.pop("question")
        missing_options = codex_question()
        missing_options.pop("options")

        self.assertIsNone(self.normalize_question(missing_question))
        self.assertIsNone(self.normalize_question(missing_options))

    def test_optional_header_is_bounded_clean_text_when_present(self):
        self.assertIsNotNone(self.normalize_question(codex_question(header="Auth")))
        for header in (3, "Auth\x00", "x" * 65):
            with self.subTest(header=header):
                self.assertIsNone(self.normalize_question(
                    codex_question(header=header)))

    def test_options_reject_malformed_objects_labels_and_descriptions(self):
        invalid_options = (
            ["not an option", {"label": "b"}],
            [{}, {"label": "b"}],
            [{"label": 3}, {"label": "b"}],
            [{"label": "a", "description": 3}, {"label": "b"}],
            [{"label": "a", "description": "bad\x00"}, {"label": "b"}],
        )

        for options in invalid_options:
            with self.subTest(options=options):
                self.assertIsNone(self.normalize_question(
                    codex_question(options=options)))

    def test_display_text_uses_utf8_byte_boundaries_without_truncation(self):
        prompt_exact = "é" * 48
        prompt_over = prompt_exact + "a"
        label_exact = "é" * 32
        label_over = label_exact + "a"
        description_exact = "é" * 32
        description_over = description_exact + "a"
        exact_payloads = (
            codex_question(question=prompt_exact),
            codex_question(options=[{"label": label_exact}, {"label": "b"}]),
            codex_question(options=[
                {"label": "a", "description": description_exact}, {"label": "b"},
            ]),
        )
        over_payloads = (
            codex_question(question=prompt_over),
            codex_question(options=[{"label": label_over}, {"label": "b"}]),
            codex_question(options=[
                {"label": "a", "description": description_over}, {"label": "b"},
            ]),
        )

        for payload in exact_payloads:
            with self.subTest(exact=payload):
                self.assertIsNotNone(self.normalize_question(payload))
        for payload in over_payloads:
            with self.subTest(over=payload):
                self.assertIsNone(self.normalize_question(payload))

    def test_question_rejects_non_dict_payload(self):
        self.assertIsNone(self.normalize_question([]))

    def test_question_rejects_structural_and_option_shape_errors(self):
        cases = [
            codex_question(extra="unknown"),
            codex_question(options=[{"label": "only one"}]),
            codex_question(options=[{"label": str(i)} for i in range(4)]),
            codex_question(options=[
                {"label": "a", "recommended": True},
                {"label": "b", "recommended": True},
            ]),
            codex_question(options=[
                {"label": "a", "recommended": "yes"},
                {"label": "b"},
            ]),
            codex_question(options=[
                {"label": "a", "unknown": 1}, {"label": "b"},
            ]),
        ]

        for payload in cases:
            with self.subTest(payload=payload):
                self.assertIsNone(self.normalize_question(payload))

    def test_question_rejects_empty_controls_and_overlong_display_text(self):
        invalid_payloads = [
            codex_question(question="   "),
            codex_question(question="Question\x00"),
            codex_question(question="Question\u202e"),
            codex_question(question="x" * 97),
            codex_question(options=[{"label": "\x7f"}, {"label": "b"}]),
            codex_question(options=[{"label": "x" * 65}, {"label": "b"}]),
            codex_question(options=[
                {"label": "a", "description": "x" * 65}, {"label": "b"},
            ]),
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                self.assertIsNone(self.normalize_question(payload))

    def test_unicode_controls_never_reach_an_approvable_permission_view(self):
        normalized = normalize_codex_permission(
            codex_permission(tool_input={"command": "cat \u202eREADME.md"}),
            reveal=True)

        self.assertIsNone(normalized)

    def test_permission_uses_the_documented_response_shapes(self):
        self.assertEqual(codex_permission_response("approve"), {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "allow"},
            },
        })
        self.assertIsNone(codex_permission_response("leave_it"))
        self.assertEqual(codex_permission_response("deny"), {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {
                    "behavior": "deny", "message": "Denied from VibePulse",
                },
            },
        })
        with self.assertRaises(ValueError):
            codex_permission_response("maybe")

    def test_permission_applies_readability_and_tool_safety_gates(self):
        read_only = normalize_codex_permission(codex_permission(), reveal=True)
        hidden_read = normalize_codex_permission(codex_permission(), reveal=False)
        patch = normalize_codex_permission(
            codex_permission(tool_name="apply_patch", tool_input={}), reveal=True)

        self.assertTrue(read_only["view"]["can_approve"])
        self.assertFalse(hidden_read["view"]["can_approve"])
        self.assertFalse(patch["view"]["can_approve"])

    def test_permission_rejects_wrong_event_and_malformed_required_fields(self):
        invalid_events = [
            codex_permission(hook_event_name="PreToolUse"),
            codex_permission(session_id=""),
            codex_permission(turn_id=3),
            codex_permission(cwd=None),
            codex_permission(tool_name=[]),
            codex_permission(tool_input=[]),
        ]

        for event in invalid_events:
            with self.subTest(event=event):
                self.assertIsNone(normalize_codex_permission(event, reveal=True))

    def test_dangerous_shell_commands_are_never_approvable(self):
        commands = (
            "npm test; rm -rf build", "echo hi > notes.txt", "npm install",
            "./deploy.sh", "git push", "rm old.txt", "curl example.com",
        )

        for command in commands:
            with self.subTest(command=command):
                normalized = normalize_codex_permission(
                    codex_permission(tool_name="Shell",
                                     tool_input={"command": command}), reveal=True)
                self.assertFalse(normalized["view"]["can_approve"])

    def test_shell_command_families_are_strictly_positive(self):
        safe_commands = (
            "make", "make all", "make test",
            "ninja", "ninja all", "ninja test",
            "cmake --build build", "cmake --build build --parallel 4",
            "cmake --build build --target all", "npm test", "npm run test",
            "npm run build", "npm run build --silent", "pytest",
            "python -m unittest", "cargo test", "cargo build", "go test",
            "ctest", "./test/run.sh", "idf.py build", "git status", "git log",
            "git show install", "git branch", "git branch --show-current",
            "git diff", "git diff --stat", "ls", "cat installer-notes.txt",
            "head README", "tail README", "wc README", "grep value README",
            "rg value README",
        )
        unsafe_commands = (
            "npm run build -- --deploy", "npm run build -- --install",
            "npm run build -- --delete", "git branch new-feature",
            "git branch -D old-feature", "git diff --output=result.patch",
            "make install-strip", "make clean-all", "make deploy-prod",
            "ninja install/strip", "cmake --build b --target install/strip",
            "make npm up package", "make npm x package", "make uvx package",
            "make installer", "make -j4", "ninja -C build",
            "cmake --build build --output=result.patch", "npm install",
            "npm run deploy", "git diff --ext-diff", "git -c x=y status",
            "idf.py build flash",
            "./test/run.sh deploy", "./test/run.sh install",
            "./test/run.sh delete", "./test/run.sh push",
            "./test/run.sh publish", "./test/run.sh network",
            "./test/run.sh foo",
            "./TEST/RUN.SH", "./Test/run.sh",
            "make CC='touch /tmp/pwn' all",
            "make CC='rm -f /tmp/pwn' build",
            "make FETCH='curl https://example.test' test",
            "make ACTION=deploy all", "make TARGET=install build",
            "ninja CC='touch /tmp/pwn' all",
        )

        for command in safe_commands:
            with self.subTest(safe=command):
                normalized = normalize_codex_permission(
                    codex_permission(tool_name="Shell",
                                     tool_input={"command": command}), reveal=True)
                self.assertTrue(normalized["view"]["can_approve"])
        for command in unsafe_commands:
            with self.subTest(unsafe=command):
                normalized = normalize_codex_permission(
                    codex_permission(tool_name="Shell",
                                     tool_input={"command": command}), reveal=True)
                self.assertFalse(normalized["view"]["can_approve"])

    def test_question_result_only_answers_the_explicit_recommendation(self):
        normalized = self.normalize_question()

        self.assertEqual(codex_question_result("approve", normalized), {
            "status": "answered", "option_index": 1,
            "answer": "New auth layer",
        })
        self.assertEqual(codex_question_result("deny", normalized), {
            "status": "computer", "reason": "deny",
        })
        unmarked = self.normalize_question(codex_question(options=[
            {"label": "a"}, {"label": "b"},
        ]))
        self.assertEqual(codex_question_result("approve", unmarked), {
            "status": "computer", "reason": "approve",
        })


class Clock:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class CodexInteractionStoreTests(unittest.TestCase):
    SECRET = "a" * 64

    def setUp(self):
        self.clock = Clock()
        self.wall = Clock(50_000.0)
        self.store = interactions.InteractionStore(
            secret=self.SECRET, reveal_detail=True, now=self.clock,
            wall=self.wall)

    def normalized_question(self):
        return normalize_codex_question(
            codex_question(), cwd="/Users/niclas/vibepulse",
            session_id="session-123", turn_id="turn-456")

    def answer_v2(self, entry, verdict="approve", *, provider=None,
                  digest=None, stamp=None, mac=None):
        provider = provider if provider is not None else entry.provider.value
        digest = digest if digest is not None else entry.view_sha256
        stamp = int(self.wall()) if stamp is None else stamp
        if mac is None:
            mac = interactions.sign_answer_v2(
                self.SECRET, provider, entry.request_id, digest, verdict,
                stamp)
        return self.store.resolve(
            entry.request_id, verdict, stamp, mac, provider=provider,
            view_sha256=digest)

    def test_codex_public_view_is_provider_bound_private_free_and_immutable(self):
        normalized = self.normalized_question()
        entry = self.store.park_normalized(normalized, 120)
        normalized["view"]["title"] = "tampered after park"
        public = self.store.pending_public()

        self.assertEqual(public["provider"], "codex")
        self.assertEqual(public["title"], "New auth layer")
        self.assertEqual(public["view_sha256"],
                         interactions.view_digest(public))
        serialized = json.dumps(public)
        for private in ("session-123", "turn-456", "session_id", "turn_id",
                        "event"):
            self.assertNotIn(private, serialized)
        with self.assertRaises(TypeError):
            entry.view["title"] = "mutate stored view"

    def test_v1_cannot_resolve_codex_and_does_not_consume_it(self):
        entry = self.store.park_normalized(self.normalized_question(), 120)
        stamp = int(self.wall())
        mac = interactions.sign_answer(
            self.SECRET, entry.request_id, "approve", stamp)

        ok, reason = self.store.resolve(
            entry.request_id, "approve", stamp, mac)

        self.assertEqual((ok, reason), (False, "v2 verdict required"))
        self.assertEqual(self.store.pending_public()["request_id"],
                         entry.request_id)
        for provider, digest in (("codex", None),
                                 (None, entry.view_sha256)):
            with self.subTest(provider=provider, digest=digest):
                ok, reason = self.store.resolve(
                    entry.request_id, "approve", stamp, "0" * 64,
                    provider=provider, view_sha256=digest)
                self.assertEqual((ok, reason),
                                 (False, "v2 verdict required"))
                self.assertEqual(self.store.pending_public()["request_id"],
                                 entry.request_id)

    def test_v2_exact_binding_returns_codex_recommended_option(self):
        entry = self.store.park_normalized(self.normalized_question(), 120)

        self.assertEqual(self.answer_v2(entry), (True, "ok"))
        result = self.store.await_result(entry)

        self.assertEqual(result, InteractionResult(
            verdict="approve", option_index=1))

    def test_codex_permission_keeps_raw_event_private_and_has_no_option(self):
        normalized = normalize_codex_permission(
            codex_permission(), reveal=True)
        entry = self.store.park_normalized(normalized, 120)
        public = self.store.pending_public()

        self.assertEqual(public["provider"], "codex")
        self.assertEqual(public["kind"], "approval")
        self.assertNotIn("session-123", json.dumps(public))
        self.assertNotIn("turn-456", json.dumps(public))
        self.assertEqual(self.answer_v2(entry), (True, "ok"))
        self.assertEqual(self.store.await_result(entry), InteractionResult(
            verdict="approve", option_index=None))

    def test_dangerous_codex_event_cannot_borrow_an_approvable_read_view(self):
        dangerous = normalize_codex_permission(
            codex_permission(
                tool_name="Bash", tool_input={"command": "rm -rf build"}),
            reveal=True)
        safe = normalize_codex_permission(codex_permission(), reveal=True)
        self.assertFalse(dangerous["view"]["can_approve"])
        self.assertTrue(safe["view"]["can_approve"])
        forged = {**dangerous, "view": dict(safe["view"])}

        entry = self.store.park_normalized(forged, 120)

        self.assertIsNone(entry)
        self.assertIsNone(self.store.pending_public())

    def test_wrong_v2_bindings_and_bad_signatures_never_consume(self):
        entry = self.store.park_normalized(self.normalized_question(), 600)
        stamp = int(self.wall())
        wrong_digest = "0" * 64
        attempts = [
            ("claude", entry.view_sha256, stamp,
             interactions.sign_answer_v2(
                 self.SECRET, "claude", entry.request_id,
                 entry.view_sha256, "approve", stamp)),
            ("codex", wrong_digest, stamp,
             interactions.sign_answer_v2(
                 self.SECRET, "codex", entry.request_id, wrong_digest,
                 "approve", stamp)),
            ("CODEX", entry.view_sha256, stamp, "0" * 64),
            ("codex", "short", stamp, "0" * 64),
            ("codex", entry.view_sha256, stamp, "0" * 64),
        ]
        for provider, digest, attempted_stamp, mac in attempts:
            with self.subTest(provider=provider, digest=digest, mac=mac):
                ok, _ = self.store.resolve(
                    entry.request_id, "approve", attempted_stamp, mac,
                    provider=provider, view_sha256=digest)
                self.assertFalse(ok)
                self.assertEqual(self.store.pending_public()["request_id"],
                                 entry.request_id)

        stale_mac = interactions.sign_answer_v2(
            self.SECRET, "codex", entry.request_id, entry.view_sha256,
            "approve", stamp)
        self.wall.advance(interactions.FRESHNESS_S + 1)
        ok, _ = self.store.resolve(
            entry.request_id, "approve", stamp, stale_mac,
            provider="codex", view_sha256=entry.view_sha256)
        self.assertFalse(ok)
        self.assertEqual(self.store.pending_public()["request_id"],
                         entry.request_id)

        self.assertEqual(self.answer_v2(entry), (True, "ok"))

    def test_codex_approve_still_requires_can_approve(self):
        normalized = normalize_codex_question(
            codex_question(options=[
                {"label": "first"}, {"label": "second"},
            ]), cwd="/Users/niclas/vibepulse",
            session_id="session-123", turn_id="turn-456")
        entry = self.store.park_normalized(normalized, 120)

        ok, reason = self.answer_v2(entry)

        self.assertFalse(ok)
        self.assertIn("terminal", reason)
        self.assertIsNotNone(self.store.pending_public())

    def test_await_verdict_refuses_codex_without_hook_output(self):
        entry = self.store.park_normalized(self.normalized_question(), 120)
        self.assertEqual(self.answer_v2(entry), (True, "ok"))

        self.assertIsNone(self.store.await_verdict(entry))

    def test_normalized_boundary_rejects_unvalidated_or_private_view_fields(self):
        valid = self.normalized_question()
        cases = [
            None,
            {**valid, "provider": "other"},
            {**valid, "recommended_index": 99},
            {**valid, "view": {**valid["view"],
                                "session_id": "must-not-publish"}},
            {**valid, "view": {**valid["view"], "event": {"raw": True}}},
        ]

        for normalized in cases:
            with self.subTest(normalized=normalized):
                self.assertIsNone(self.store.park_normalized(normalized, 120))

        self.assertIsNone(self.store.pending_public())
