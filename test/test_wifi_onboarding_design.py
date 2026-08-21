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
            {"schemaVersion", "deviceCapability", "canvas", "wifi", "open", "fonts"},
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
                "states": ["offline", "weak", "medium", "strong"],
                "hiddenDuringBoot": True,
            },
        )
        opened = design["open"]
        self.assertGreaterEqual(opened["qrSize"], 180)
        self.assertGreaterEqual(opened["qrX"], 8)
        self.assertGreaterEqual(opened["qrY"], 8)
        self.assertLessEqual(opened["qrX"] + opened["qrSize"], 472)
        self.assertLessEqual(opened["qrY"] + opened["qrSize"], opened["ssidY"] - 8)
        ys = [
            opened["wordY"], opened["instructionY"], opened["qrY"],
            opened["ssidY"], opened["passwordY"], opened["addressY"],
            opened["footerY"],
        ]
        self.assertEqual(ys, sorted(ys))
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
            (("open", "ssidY"), 290),
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
            "SSID_Y": opened["ssidY"],
            "PASSWORD_Y": opened["passwordY"],
            "ADDRESS_Y": opened["addressY"],
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

    def test_repository_runner_wires_contract(self):
        runner = (ROOT / "test/run.sh").read_text(encoding="utf-8")
        self.assertEqual(runner.count("test_wifi_onboarding_design.py"), 1)


if __name__ == "__main__":
    unittest.main()
