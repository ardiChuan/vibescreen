"""Contract test: /api/agent-status still fits after "Needs You".

The agent fetch task is all-or-nothing exactly like the token fetch — past
TK_AGENT_HTTP_BODY_CAP (components/app_tokens/agent_net_policy.h) the device
discards the WHOLE body, which would take the agent list down with it. The
pending interaction is a new optional root key on that same payload, so it is
the field most able to break a screen that works today.

Two things are asserted, and the second is the one that matters: the ceiling
the server enforces must remain inside the firmware's explicit 4096-byte
envelope, and a genuinely worst-case snapshot plus a worst-case pending item
must retain meaningful headroom inside it.

Standalone, invoked from test/run.sh:
    python3 test/test_agent_status_body_capacity.py
(the stdlib `test` package shadows this directory for -m unittest).
"""

import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_H = (REPO_ROOT / "components" / "app_tokens" /
            "agent_net_policy.h")
AGENT_STATUS_H = (REPO_ROOT / "components" / "app_tokens" /
                  "agent_status.h")

sys.path.insert(0, str(REPO_ROOT / "tools" / "tokenserver"))

import interactions  # noqa: E402

# Provider and view binding make 75 % unattainable without shortening the
# established display fields.  The field-wise maximum must still stay within
# 80 % of the firmware envelope, leaving more than 800 bytes of headroom.
WORST_CASE_MAX_FRACTION = 0.80


def read_body_cap() -> int:
    source = POLICY_H.read_text(encoding="utf-8")
    matches = re.findall(r"^#define\s+TK_AGENT_HTTP_BODY_CAP\s+(\d+)\s*$",
                         source, flags=re.MULTILINE)
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one TK_AGENT_HTTP_BODY_CAP define in "
            f"{POLICY_H}, found {len(matches)}")
    return int(matches[0])


def read_pending_id_cap() -> int:
    source = AGENT_STATUS_H.read_text(encoding="utf-8")
    matches = re.findall(r"^#define\s+TK_PENDING_ID_CAP\s+(\d+)", source,
                         flags=re.MULTILINE)
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one TK_PENDING_ID_CAP define in "
            f"{AGENT_STATUS_H}, found {len(matches)}")
    return int(matches[0])


def worst_case_job() -> dict:
    """Field-wise maxima for one job, per agent_status.py's own bounds."""
    return {
        "task_id": "f" * 64,        # sha256 hex
        "event_id": "e" * 32,       # stable_event_id truncates to 32
        "state": "waiting",
        "project": "w" * 16,        # sanitize_project bounds to 16 bytes
        "activity": "waiting_approval",   # longest ACTIVITY
        "model": "m" * 24,          # normalize_model bounds to 24 bytes
        "effort": "e" * 12,         # normalize_effort bounds to 12 bytes
        "updated_ms": 0xFFFFFFFF,
    }


def worst_case_snapshot() -> dict:
    jobs = [worst_case_job() for _ in range(4)]  # PUBLIC_JOB_LIMIT
    return {
        "v": 2,
        "seq": 0xFFFFFFFF,
        "agents": {
            "claude": {"active_count": 9999, "jobs": jobs},
            "codex": {"active_count": 9999, "jobs": list(jobs)},
        },
    }


def worst_case_pending() -> dict:
    """The largest pending item the store can publish.

    Built through the real store rather than hand-written, so the bound
    tracks the code instead of a copy of it.
    """
    store = interactions.InteractionStore(secret="a" * 64,
                                          reveal_detail=True)
    store.park("question", {
        "session_id": "s" * 64,
        "cwd": "/Users/someone/" + "w" * 40,
        "tool_name": "AskUserQuestion",
        "tool_input": {"questions": [{
            "question": "q" * 400,
            "header": "h" * 40,
            "multiSelect": False,
            "options": [{"label": "l" * 400, "description": "d" * 400},
                        {"label": "second", "description": "other"}],
        }]},
    }, 600)
    pending = store.pending_public()
    assert pending is not None, "the store published nothing to measure"
    return pending


class AgentStatusBodyCapacityTests(unittest.TestCase):
    def test_pending_ids_fit_and_preserve_the_legacy_32_hex_envelope(self):
        store = interactions.InteractionStore(secret="a" * 64,
                                              reveal_detail=True)
        entry = store.park("approval", {
            "session_id": "s", "cwd": "/tmp/project",
            "tool_name": "Read", "tool_input": {},
        }, 60)
        cap = read_pending_id_cap()

        self.assertEqual(cap, 33)  # legacy 32 hex chars plus NUL
        self.assertEqual(len(entry.request_id), 22)
        self.assertLess(len(entry.request_id), cap)
        self.assertEqual(len("f" * 32) + 1, cap)

    def test_server_ceiling_stays_inside_the_firmware_envelope(self):
        cap = read_body_cap()
        self.assertLess(
            interactions.RESPONSE_CEILING_BYTES, cap,
            f"RESPONSE_CEILING_BYTES={interactions.RESPONSE_CEILING_BYTES} "
            f"does not fit inside TK_AGENT_HTTP_BODY_CAP={cap}")

    def test_pending_item_respects_its_own_budget(self):
        pending = worst_case_pending()
        encoded = len(json.dumps(pending).encode())
        self.assertIn(pending["provider"], ("claude", "codex"))
        self.assertRegex(pending["view_sha256"], r"^[0-9a-f]{64}$")
        self.assertLessEqual(
            encoded, interactions.PENDING_BUDGET_BYTES,
            f"worst-case pending item is {encoded} bytes, budget is "
            f"{interactions.PENDING_BUDGET_BYTES}")

    def test_worst_case_snapshot_plus_pending_fits_the_device(self):
        payload = worst_case_snapshot()
        payload["pending"] = worst_case_pending()
        encoded = len(json.dumps(payload).encode())
        cap = read_body_cap()
        self.assertTrue(
            interactions.response_fits(payload),
            f"worst case is {encoded} bytes against a "
            f"{interactions.RESPONSE_CEILING_BYTES}-byte ceiling")
        self.assertLessEqual(
            encoded, int(cap * WORST_CASE_MAX_FRACTION),
            f"worst case is {encoded} bytes, over "
            f"{WORST_CASE_MAX_FRACTION:.0%} of "
            f"the device's {cap}-byte buffer")

    def test_the_agent_list_survives_when_pending_would_not_fit(self):
        """The existing contract wins: an oversized pending item is dropped,
        never allowed to take the agent list with it."""
        payload = worst_case_snapshot()
        payload["pending"] = {"request_id": "x" * 4000}
        self.assertFalse(interactions.response_fits(payload))
        del payload["pending"]
        self.assertTrue(interactions.response_fits(payload))


if __name__ == "__main__":
    unittest.main(verbosity=2)
