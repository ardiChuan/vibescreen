#!/usr/bin/env python3
"""Static safety contract for the ESP-IDF interaction relay client."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "components/app_tokens/interaction_relay_net.c"


class InteractionRelayNetSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE_PATH.read_text(encoding="utf-8")

    def test_uses_exact_panel_routes_and_role_token(self) -> None:
        for value in (
            "/v1/mailboxes/%s/requests/next",
            "/v1/mailboxes/%s/requests/%s/verdict",
            "TK_VIBEPULSE_INTERACTION_PANEL_TOKEN",
            '"Authorization"',
            '"Bearer %s"',
            '"Cache-Control", "no-store"',
            '"Content-Type", "application/json"',
        ):
            self.assertIn(value, self.source)

    def test_https_is_bounded_complete_and_serialized(self) -> None:
        for value in (
            "TK_IR_MAX_ENVELOPE_BYTES",
            "esp_http_client_is_complete_data_received",
            "esp_crt_bundle_attach",
            "torget_cloud_io_acquire",
            "torget_cloud_io_release",
            "esp_http_client_open",
            "esp_http_client_fetch_headers",
            "esp_http_client_read",
        ):
            self.assertIn(value, self.source)
        self.assertRegex(self.source, r"char\s+response\[TK_IR_MAX_ENVELOPE_BYTES \+ 1u\]")
        self.assertNotIn("esp_http_client_perform", self.source)
        self.assertNotIn("HTTP_EVENT_ON_DATA", self.source)

    def test_response_headers_come_from_response_events(self) -> None:
        """esp_http_client_get_header reads request headers, never response."""
        for value in (
            "HTTP_EVENT_ON_HEADER",
            ".event_handler = relay_http_event",
            ".user_data = &out->headers",
            "strcasecmp(evt->header_key, \"Cache-Control\")",
            "strcasecmp(evt->header_key, \"Content-Type\")",
        ):
            self.assertIn(value, self.source)
        self.assertNotIn("esp_http_client_get_header", self.source)
        self.assertIn("headers->cache_control_count != 1u", self.source)
        self.assertIn("headers->content_type_count > 1u", self.source)

    def test_crypto_and_verdict_retry_are_owned_by_worker(self) -> None:
        for value in (
            "tk_ir_derive_keys",
            "tk_ir_decode_request",
            "tk_ir_encode_verdict_binding",
            "tk_ir_retry_begin",
            "tk_ir_retry_body",
            "tk_ir_retry_note_failure",
            "esp_fill_random",
            "xQueueCreateStatic",
            "xQueueReceive",
        ):
            self.assertIn(value, self.source)
        self.assertRegex(
            self.source,
            r"bool\s+tk_interaction_relay_queue_verdict\s*\(",
        )

    def test_poll_wait_backoff_and_redacted_status_exist(self) -> None:
        for value in (
            "torget_net_wait();",
            "TK_IR_POLL_INTERVAL_MS 5000u",
            "tk_ir_backoff_fail",
            "tk_ir_backoff_wifi_recovered",
            "tokens_interaction_relay_net_status",
        ):
            self.assertIn(value, self.source)

    def test_only_final_validated_apply_takes_ui_lock(self) -> None:
        lock = self.source.index("torget_ui_lock();")
        apply = self.source.index("tk_agent_monitor_apply_relay", lock)
        unlock = self.source.index("torget_ui_unlock();", apply)
        self.assertLess(lock, apply)
        self.assertLess(apply, unlock)
        gate = self.source.index("torget_cloud_io_acquire")
        release = self.source.index("torget_cloud_io_release", gate)
        self.assertNotIn("torget_ui_lock", self.source[gate:release])
        self.assertNotIn("lv_", self.source)
        self.assertNotIn('#include "lvgl.h"', self.source)

    def test_no_sensitive_material_is_logged_or_heap_allocated(self) -> None:
        self.assertNotRegex(self.source, r"\b(?:malloc|calloc|realloc|free)\s*\(")
        for match in re.finditer(r"ESP_LOG[A-Z]+\((?P<call>.*?)\);", self.source, re.S):
            call = match.group("call").lower()
            for forbidden in (
                "token", "mailbox", "url", "cipher", "question",
                "project", "command", "challenge", "key", "hmac",
            ):
                self.assertNotIn(forbidden, call)


if __name__ == "__main__":
    unittest.main()
