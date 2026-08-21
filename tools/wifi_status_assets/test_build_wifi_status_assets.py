#!/usr/bin/env python3
"""Regression tests for the native final-size Wi-Fi header marks."""

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("build_wifi_status_assets.py")


class WifiStatusAssetTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), "Wi-Fi asset generator is missing")
        spec = importlib.util.spec_from_file_location("wifi_status_assets", SCRIPT)
        self.build = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(self.build)

    def test_four_native_states_are_distinct_and_progressive(self):
        assets = self.build.build_assets()
        self.assertEqual(tuple(assets), ("offline", "weak", "medium", "strong"))
        self.assertEqual(len(set(assets.values())), 4)
        decoded = {name: self.build.decode_i4(data)[1]
                   for name, data in assets.items()}
        for data in assets.values():
            self.assertEqual(len(data), 64 + 20 * 18 // 2)
        self.assertLess(sum(decoded["weak"]), sum(decoded["medium"]))
        self.assertLess(sum(decoded["medium"]), sum(decoded["strong"]))

    def test_palette_and_transparent_edges_are_exact(self):
        for name, data in self.build.build_assets().items():
            palette, pixels = self.build.decode_i4(data)
            with self.subTest(name=name):
                self.assertEqual(palette[0], (0, 0, 0, 0))
                self.assertEqual(palette[1], (0x92, 0x98, 0xA2, 255))
                self.assertEqual(set(pixels) - {0, 1}, set())
                perimeter = {
                    *range(20),
                    *range(17 * 20, 18 * 20),
                    *(y * 20 for y in range(18)),
                    *(y * 20 + 19 for y in range(18)),
                }
                for index in perimeter:
                    self.assertEqual(pixels[index], 0)

    def test_checked_in_sources_are_exactly_generated(self):
        header, source = self.build.render_sources()
        self.assertEqual(header, self.build.OUT_H.read_text(encoding="utf-8"))
        self.assertEqual(source, self.build.OUT_C.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
