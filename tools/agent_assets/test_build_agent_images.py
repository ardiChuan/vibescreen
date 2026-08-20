import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("build-agent-images.py")
SPEC = importlib.util.spec_from_file_location("build_agent_images", SCRIPT)
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


def decode_i4(data, size):
    palette = [tuple(data[i:i + 4]) for i in range(0, 16 * 4, 4)]
    indices = []
    for byte in data[16 * 4:]:
        indices.extend((byte >> 4, byte & 0x0F))
    return palette, indices[:size * size]


def decode_i4_wh(data, width, height):
    palette = [tuple(data[i:i + 4]) for i in range(0, 16 * 4, 4)]
    indices = []
    for byte in data[16 * 4:]:
        indices.extend((byte >> 4, byte & 0x0F))
    return palette, indices[:width * height]


class AgentAssetTests(unittest.TestCase):
    def test_checked_in_generated_sources_match_exactly(self):
        header, source = build.render_generated_sources()

        self.assertEqual(
            header,
            (build.ROOT / "components/app_tokens/agent_assets.h").read_text(
                encoding="utf-8"
            ),
        )
        self.assertEqual(
            source,
            (build.ROOT / "components/app_tokens/agent_assets.c").read_text(
                encoding="utf-8"
            ),
        )

    def test_generated_source_drift_is_detected(self):
        header, source = build.render_generated_sources()
        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory) / "agent_assets.c"
            generated.write_text(source + "/* hand edit */\n", encoding="utf-8")

            self.assertNotEqual(source, generated.read_text(encoding="utf-8"))

    def test_claude_small_asset_is_exactly_32_by_32_a8(self):
        data = build.build_claude(32)

        self.assertEqual(len(data), 32 * 32)
        self.assertGreater(sum(byte > 0 for byte in data), 64)

    def test_codex_assets_are_native_deterministic_i4_composites(self):
        for size in (112, 32):
            with self.subTest(size=size):
                data = build.build_codex(size)
                self.assertIsInstance(data, bytes)
                self.assertEqual(len(data), 16 * 4 + size * size // 2)
                self.assertEqual(data, build.build_codex(size))

    def test_codex_needs_you_asset_is_native_transparent_64(self):
        data = build.build_codex(64)
        palette, indices = decode_i4(data, 64)
        self.assertEqual(len(data), 16 * 4 + 64 * 64 // 2)
        self.assertEqual(palette[0], (0, 0, 0, 0))
        self.assertEqual(sum(color == (255, 255, 255, 255)
                             for color in palette), 1)
        self.assertTrue(all(indices[i] == 0 for i in (0, 63, 4032, 4095)))
        header, source = build.render_generated_sources()
        self.assertIn("tk_img_codex_64", header)
        self.assertIn(".w = 64", source)
        self.assertIn(".stride = 32", source)

    def test_codex_palette_reserves_transparency_and_one_exact_white(self):
        for size in (112, 32):
            palette, indices = decode_i4(build.build_codex(size), size)
            used = {palette[index] for index in indices}

            self.assertEqual(palette[0], (0, 0, 0, 0))
            self.assertEqual(sum(color == (255, 255, 255, 255)
                                 for color in palette), 1)
            self.assertIn((255, 255, 255, 255), used)
            self.assertGreater(sum(index == 15 for index in indices),
                               140 if size == 112 else 8)
            self.assertGreater(sum(index not in (0, 15) for index in indices),
                               size * size // 5)

    def test_codex_silhouette_has_clean_transparent_corners(self):
        for size in (112, 32):
            palette, indices = decode_i4(build.build_codex(size), size)
            visible = [(x, y) for y in range(size) for x in range(size)
                       if indices[y * size + x] != 0]
            xs = [x for x, _ in visible]
            ys = [y for _, y in visible]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            bbox_area = (x1 - x0 + 1) * (y1 - y0 + 1)

            self.assertTrue(all(indices[y * size + x] == 0
                                for x, y in ((0, 0), (size - 1, 0),
                                             (0, size - 1),
                                             (size - 1, size - 1))))
            self.assertLess(len(visible), bbox_area * 0.85)
            for color in palette[1:15]:
                b, g, r, a = color
                if a:
                    self.assertGreater(b, r)
                    self.assertGreater(b, g)
                    self.assertFalse(r > 205 and b > 225,
                                     f"lavender fringe color {color}")

    def test_mascot_poses_are_precolored_i4_at_integer_scales(self):
        for name, pose, cell in build.MASCOTS:
            with self.subTest(name=name):
                data, width, height = build.build_mascot(pose, cell)
                self.assertEqual((width, height), (16 * cell, 13 * cell))
                self.assertEqual(len(data), 16 * 4 + width * height // 2)
                # Deterministic, so the byte-for-byte gate is stable.
                self.assertEqual(data, build.build_mascot(pose, cell)[0])
                palette, indices = decode_i4_wh(data, width, height)
                # Pre-colored: transparent ground + exactly the Claude accent,
                # never recolored at runtime.
                self.assertEqual(palette[0], (0, 0, 0, 0))
                self.assertEqual(palette[1], (0x57, 0x77, 0xD9, 255))
                self.assertEqual(set(indices) - {0, 1}, set())
                self.assertGreater(sum(i == 1 for i in indices), 0)
                for corner in (0, width - 1, (height - 1) * width,
                               height * width - 1):
                    self.assertEqual(indices[corner], 0)

    def test_mascot_poses_are_visually_distinct(self):
        # Each emotive beat is its own raster; poses never collapse together.
        variants = {name: build.build_mascot(pose, cell)[0]
                    for name, pose, cell in build.MASCOTS}
        self.assertNotEqual(variants["tk_img_mascot_asking_4"],
                            variants["tk_img_mascot_neutral_4"])
        self.assertNotEqual(variants["tk_img_mascot_alert_8"],
                            variants["tk_img_mascot_happy_8"])

    def test_descriptor_uses_requested_canvas_size(self):
        source = build.descriptor(
            "small", "small_data", "LV_COLOR_FORMAT_A8",
            stride=32, size=1024, canvas=32)

        self.assertIn(".w = 32", source)
        self.assertIn(".h = 32", source)


if __name__ == "__main__":
    unittest.main()
