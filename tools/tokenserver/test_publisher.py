"""The relay publisher's two contracts: write economy, and honesty.

Write economy because the mailbox's free tier allows 1 000 writes/day and
a naive 30-second cadence would burn 2 880.  Honesty because every send
must name its publisher (the mailbox merges freshest-per-source) and wear
the project's own User-Agent, not somebody else's.
"""

import unittest

try:
    from .publisher import (Publisher, HEARTBEAT_EVERY_S,
                            payload_fingerprint, should_send, USER_AGENT)
except ImportError:
    from publisher import (Publisher, HEARTBEAT_EVERY_S,
                           payload_fingerprint, should_send, USER_AGENT)


class FingerprintTests(unittest.TestCase):
    def test_key_order_is_irrelevant(self):
        a = payload_fingerprint({"x": 1, "y": [1, 2]})
        b = payload_fingerprint({"y": [1, 2], "x": 1})
        self.assertEqual(a, b)

    def test_value_changes_are_visible(self):
        self.assertNotEqual(payload_fingerprint({"pct": 73.0}),
                            payload_fingerprint({"pct": 73.1}))


class ShouldSendTests(unittest.TestCase):
    def test_a_fresh_start_sends(self):
        self.assertTrue(should_send(None, 0.0, "abc", 1000.0))

    def test_unchanged_content_waits(self):
        self.assertFalse(should_send("abc", 1000.0, "abc", 1010.0))

    def test_changed_content_sends_immediately(self):
        self.assertTrue(should_send("abc", 1000.0, "def", 1001.0))

    def test_the_heartbeat_bounds_staleness(self):
        just_before = 1000.0 + HEARTBEAT_EVERY_S - 1
        at = 1000.0 + HEARTBEAT_EVERY_S
        self.assertFalse(should_send("abc", 1000.0, "abc", just_before))
        self.assertTrue(should_send("abc", 1000.0, "abc", at))


class PublisherTests(unittest.TestCase):
    def _publisher(self, producers, results=None):
        sent = []
        outcomes = list(results) if results is not None else None

        def post(url, body):
            sent.append((url, body))
            return True if outcomes is None else outcomes.pop(0)

        clock = {"now": 1000.0}
        p = Publisher("https://relay.example/u/s3cret/", "test-machine",
                      producers, post=post, clock=lambda: clock["now"])
        return p, sent, clock

    def test_publishes_each_endpoint_to_its_path(self):
        p, sent, _ = self._publisher({
            "/api/tokens": lambda: {"weekPct": 73.0},
            "/api/github": lambda: {"stars": 5},
        })
        self.assertEqual(p.publish_once(), 2)
        urls = sorted(url for url, _ in sent)
        # Trailing slash on the configured URL must not double up.
        self.assertEqual(urls, ["https://relay.example/u/s3cret/api/github",
                                "https://relay.example/u/s3cret/api/tokens"])

    def test_unchanged_payloads_are_not_resent(self):
        p, sent, clock = self._publisher({"/api/tokens": lambda: {"pct": 73}})
        p.publish_once()
        clock["now"] += 30
        p.publish_once()
        self.assertEqual(len(sent), 1, "an unchanged payload was resent")

    def test_change_and_heartbeat_both_send(self):
        value = {"pct": 73}
        p, sent, clock = self._publisher({"/api/tokens": lambda: dict(value)})
        p.publish_once()
        value["pct"] = 74
        clock["now"] += 30
        p.publish_once()
        self.assertEqual(len(sent), 2, "a changed payload must send")
        clock["now"] += HEARTBEAT_EVERY_S
        p.publish_once()
        self.assertEqual(len(sent), 3, "the heartbeat must send")

    def test_a_failed_send_retries_next_tick(self):
        p, sent, clock = self._publisher({"/api/tokens": lambda: {"a": 1}},
                                         results=[False, True])
        self.assertEqual(p.publish_once(), 0)
        clock["now"] += 30
        self.assertEqual(p.publish_once(), 1)
        self.assertEqual(len(sent), 2)

    def test_a_broken_producer_does_not_stop_the_others(self):
        def broken():
            raise RuntimeError("boom")

        p, sent, _ = self._publisher({"/api/tokens": broken,
                                      "/api/github": lambda: {"ok": 1}})
        self.assertEqual(p.publish_once(), 1)
        self.assertEqual(len(sent), 1)

    def test_the_user_agent_is_our_own(self):
        # The Anthropic probe imitating claude-cli is a separate, deliberate
        # decision — but OUR mailbox gets OUR name.  If someone changes the
        # constant to imitate anything, this fails.
        self.assertTrue(USER_AGENT.startswith("vibepulse-publisher/"),
                        USER_AGENT)


if __name__ == "__main__":
    unittest.main()
