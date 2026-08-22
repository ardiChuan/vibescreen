#!/usr/bin/env python3
"""Exact-size contract for the phone-first 480x480 Wi-Fi screen."""

import json
import re
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = ROOT / "design/vibepulse/wifi-onboarding-design.json"
SOURCE_PATH = ROOT / "components/torget_wifi/wifi_setup_ui.c"
PLATFORM_UI_PATH = ROOT / "platform/torget_ui.c"


class WifiOnboardingDesignTests(unittest.TestCase):
    def setUp(self):
        self.design = json.loads(DESIGN_PATH.read_text(encoding="utf-8"))

    def validate(self, design):
        self.assertEqual(
            set(design),
            {
                "schemaVersion", "deviceCapability", "canvas", "wifi",
                "open", "manual", "fonts",
            },
        )
        self.assertEqual(design["schemaVersion"], 1)
        self.assertEqual(design["deviceCapability"], "display.amoled")
        self.assertEqual(design["canvas"], {"width": 480, "height": 480})

        wifi = design["wifi"]
        self.assertEqual(
            wifi,
            {
                "x": 426,
                "y": 28,
                "width": 20,
                "height": 18,
                "scope": "page-drift-shell",
                "color": "#9298A2",
                "states": ["offline", "connected"],
                "hiddenDuringBoot": True,
            },
        )
        opened = design["open"]
        self.assertEqual(opened["instructionY"], 72)
        self.assertEqual(
            set(opened),
            {
                "wordY", "instructionY", "qrX", "qrY", "qrSize",
                "actionX", "actionY", "actionWidth", "actionHeight",
                "footerY",
            },
        )
        self.assertGreaterEqual(opened["qrSize"], 180)
        self.assertGreaterEqual(opened["qrX"], 8)
        self.assertGreaterEqual(opened["qrY"], 8)
        self.assertLessEqual(opened["qrX"] + opened["qrSize"], 472)
        self.assertLessEqual(opened["qrY"] + opened["qrSize"], opened["actionY"] - 8)
        self.assertGreaterEqual(opened["actionHeight"], 90)
        self.assertGreaterEqual(opened["actionX"], 8)
        self.assertLessEqual(
            opened["actionX"] + opened["actionWidth"], 472,
        )
        ys = [
            opened["wordY"], opened["instructionY"], opened["qrY"],
            opened["actionY"], opened["footerY"],
        ]
        self.assertEqual(ys, sorted(ys))
        manual = design["manual"]
        self.assertEqual(
            set(manual),
            {
                "instructionY", "ssidY", "passwordY", "addressY",
                "actionY",
            },
        )
        self.assertGreaterEqual(opened["actionHeight"], 90)
        self.assertLessEqual(
            manual["actionY"] + opened["actionHeight"], opened["footerY"] - 8,
        )
        self.assertLess(opened["footerY"] + design["fonts"]["footer"], 480)
        for name, size in design["fonts"].items():
            self.assertIs(type(size), int, name)
            self.assertGreaterEqual(size, 14, name)

    def test_contract_is_safe_and_exact_size(self):
        self.validate(self.design)

    def test_unsafe_geometry_is_rejected(self):
        cases = []
        for path, value in (
            (("canvas", "width"), 479),
            (("open", "qrSize"), 179),
            (("open", "qrX"), 300),
            (("open", "actionY"), 290),
            (("open", "actionHeight"), 89),
            (("open", "footerY"), 470),
            (("fonts", "footer"), 13),
        ):
            changed = deepcopy(self.design)
            changed[path[0]][path[1]] = value
            cases.append((path, changed))
        for path, changed in cases:
            with self.subTest(path=path), self.assertRaises(AssertionError):
                self.validate(changed)

    def test_source_matches_saved_tokens(self):
        self.validate(self.design)
        source = SOURCE_PATH.read_text(encoding="utf-8")
        platform = PLATFORM_UI_PATH.read_text(encoding="utf-8")
        macros = {
            name: int(value)
            for name, value in re.findall(
                r"^#define WIFI_OPEN_([A-Z0-9_]+)\s+(\d+)$", source, re.M
            )
        }
        opened = self.design["open"]
        expected = {
            "WORD_Y": opened["wordY"],
            "INSTRUCTION_Y": opened["instructionY"],
            "QR_X": opened["qrX"],
            "QR_Y": opened["qrY"],
            "QR_SIZE": opened["qrSize"],
            "ACTION_X": opened["actionX"],
            "ACTION_Y": opened["actionY"],
            "ACTION_WIDTH": opened["actionWidth"],
            "ACTION_HEIGHT": opened["actionHeight"],
            "FOOTER_Y": opened["footerY"],
        }
        self.assertEqual(macros, expected)
        self.assertIn(
            "strcmp(payload, ui.rendered_qr_payload) == 0", source,
            "the QR canvas must not be regenerated on countdown ticks",
        )
        hidden = source.split("if (state == TG_WIFI_UI_HIDDEN)", 1)[1]
        hidden = hidden.split("lv_label_set_text(ui.word", 1)[0]
        self.assertIn("memset(ui.rendered_qr_payload", hidden)
        self.assertIn("memset(ui.rendered_secondary", hidden)
        self.assertIn('lv_label_set_text(ui.secondary, "")', hidden)
        self.assertIn('lv_label_set_text(ui.action_label, "MANUAL SETUP")', source)
        self.assertIn('lv_label_set_text(ui.action_label, "BACK TO QR")', source)
        self.assertIn("LV_EVENT_CLICKED", source)
        self.assertIn("torget_wifi_ui_set_manual_details", source)
        manual_toggle = source.split(
            "void torget_wifi_ui_set_manual_details(bool visible)", 1
        )[1].split("void torget_wifi_ui_set(", 1)[0]
        self.assertIn("lv_obj_invalidate(ui.overlay)", manual_toggle)
        qr_render = source.split("if (qr_open && !ui.manual_details)", 1)[1]
        qr_render = qr_render.split("} else {", 1)[0]
        for secret_copy in (
            "PASSWORD", "192.168.4.1", "ui.rendered_primary",
            "ui.rendered_secondary",
        ):
            self.assertNotIn(secret_copy, qr_render)
        wifi = self.design["wifi"]
        self.assertIn(
            f"lv_obj_set_pos(tg.wifi_group, {wifi['x']}, {wifi['y']})",
            platform,
        )
        self.assertIn(
            "lv_obj_set_size(tg.wifi_group, "
            f"{wifi['width']}, {wifi['height']})",
            platform,
        )
        self.assertIn("tg.wifi_group = bare(tg.shift)", platform)
        self.assertIn("lv_image_create(tg.wifi_group)", platform)
        self.assertNotIn("LV_SYMBOL_WIFI", platform)
        self.assertIn("TG_WIFI_STATUS_SETUP", platform)
        self.assertIn(
            "connected ? &tg_img_wifi_strong : &tg_img_wifi_offline",
            platform,
        )
        self.assertNotIn("&tg_img_wifi_weak", platform)
        self.assertNotIn("&tg_img_wifi_medium", platform)

    def test_repository_runner_wires_contract(self):
        runner = (ROOT / "test/run.sh").read_text(encoding="utf-8")
        self.assertEqual(runner.count("test_wifi_onboarding_design.py"), 1)


if __name__ == "__main__":
    unittest.main()
