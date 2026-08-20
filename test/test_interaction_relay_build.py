#!/usr/bin/env python3
"""Build-contract tests for the default-off panel interaction relay."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class InteractionRelayBuildTests(unittest.TestCase):
    def test_kconfig_is_explicitly_default_off(self) -> None:
        source = read("main/Kconfig.projbuild")
        match = re.search(
            r"config TK_VIBEPULSE_INTERACTION_RELAY\n(?P<body>.*?)(?=\nconfig |\nendmenu|\Z)",
            source,
            re.S,
        )
        self.assertIsNotNone(match)
        self.assertRegex(match.group("body"), r"(?m)^\s*bool\b")
        self.assertRegex(match.group("body"), r"(?m)^\s*default n\s*$")

    def test_component_is_absent_from_default_build(self) -> None:
        source = read("components/app_tokens/CMakeLists.txt")
        self.assertIn("if(CONFIG_TK_VIBEPULSE_INTERACTION_RELAY)", source)
        guarded = source.split(
            "if(CONFIG_TK_VIBEPULSE_INTERACTION_RELAY)", 1
        )[1].rsplit("endif()", 1)[0]
        for value in (
            "interaction_relay_crypto.c",
            "interaction_relay_net.c",
            "mbedtls",
            "esp_hw_support",
        ):
            self.assertIn(value, guarded)
            self.assertNotIn(value, source.split(
                "if(CONFIG_TK_VIBEPULSE_INTERACTION_RELAY)", 1
            )[0])
        # The pure policy also owns LAN suppression/selection after Task 8;
        # keeping it does not create a relay client or crypto dependency.
        self.assertIn("interaction_relay_policy.c", source.split(
            "if(CONFIG_TK_VIBEPULSE_INTERACTION_RELAY)", 1
        )[0])

    def test_enabled_build_has_fail_closed_secret_guard(self) -> None:
        source = read("components/app_tokens/CMakeLists.txt")
        for macro in (
            "TK_VIBEPULSE_INTERACTION_RELAY_URL",
            "TK_VIBEPULSE_INTERACTION_MAILBOX",
            "TK_VIBEPULSE_INTERACTION_PANEL_TOKEN",
            "TK_VIBEPULSE_DEVICE_KEY",
        ):
            self.assertIn(macro, source)
        self.assertIn("https://", source)
        self.assertIn("[A-Fa-f0-9]{64}", source)
        self.assertIn("vp_[A-Za-z0-9_-]{16}", source)
        self.assertIn("[A-Za-z0-9_-]{43}", source)
        expected = (
            "Encrypted interaction relay is enabled but incomplete.\n"
            "Add URL, mailbox, panel token, and the 64-hex device key to secrets.h,\n"
            "or run: python3 tools/vibepulse_setup.py relay doctor\n"
            "To return to LAN-only: disable TK_VIBEPULSE_INTERACTION_RELAY in menuconfig."
        )
        self.assertIn(expected, source)
        self.assertNotRegex(source, r"message\([^\n]*(?:TOKEN|KEY).*(?:=|VALUE)")

    def test_app_starts_no_dormant_default_off_task(self) -> None:
        source = read("components/app_tokens/app.c")
        start = source.index("tokens_interaction_relay_net_start();")
        before = source[:start]
        self.assertIn("#if CONFIG_TK_VIBEPULSE_INTERACTION_RELAY", before[-300:])
        self.assertIn("#endif", source[start:start + 160])

    def test_example_credentials_are_all_commented(self) -> None:
        source = read("secrets.h.example")
        for macro in (
            "TK_VIBEPULSE_INTERACTION_RELAY_URL",
            "TK_VIBEPULSE_INTERACTION_MAILBOX",
            "TK_VIBEPULSE_INTERACTION_PANEL_TOKEN",
        ):
            self.assertRegex(source, rf"(?m)^/\* #define {macro} ")
        self.assertRegex(
            source,
            r'(?m)^/\* #define TK_VIBEPULSE_DEVICE_KEY "replace-with-64-hex-characters" \*/$',
        )
        self.assertNotIn("workers.dev/v1/mailboxes", source)


if __name__ == "__main__":
    unittest.main()
