# VibePulse Wi-Fi Header Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the physically rejected Wi-Fi overlay with four native 20×18 status assets whose single shared host stays aligned with the page header and burn-in drift.

**Architecture:** Generate four deterministic I4 assets from explicit final-size pixel masks. The platform owns one `lv_image` object: normally it is a child of the translated `tg.shift` shell; OTA and Wi-Fi setup temporarily reparent that same object to `lv_layer_top()` while their full-screen takeover is visible, then return it without duplication. Existing Wi-Fi sampling remains unchanged.

**Tech Stack:** C11, LVGL 9.5, Python 3.11+/`unittest`, deterministic generated C assets, Pillow raster inspection, SDL simulator, ESP-IDF 5.5.

---

## File map

- Create `tools/wifi_status_assets/build_wifi_status_assets.py`: final-size mask definitions and deterministic I4/C generator.
- Create `tools/wifi_status_assets/test_build_wifi_status_assets.py`: asset dimensions, palettes, transparent gaps, state distinction, and byte-for-byte generation.
- Create `platform/wifi_status_assets.h`: four LVGL image descriptors.
- Create `platform/wifi_status_assets.c`: generated flash-only image bytes and descriptors.
- Modify `platform/torget_ui.c`: replace font/clipping/slash tree with one image, translated ownership, and takeover reparenting.
- Modify `platform/torget.h`: declare takeover owners and the attach/detach API.
- Modify `components/torget_wifi/wifi_setup_ui.c`: attach/detach the shared image for setup takeover.
- Modify `components/torget_ota/ota_ui.c`: attach/detach the shared image for OTA takeover.
- Modify `platform/boot_screen.c`: restore the ordinary translated host after boot.
- Modify `sim/main.c`: add deterministic drift captures and update the shared-status description.
- Modify `sim/CMakeLists.txt`, `main/CMakeLists.txt`: compile the generated platform asset source.
- Modify `test/test_lvgl_layer_safety.py`: independently pin ownership, one-object rendering, geometry, assets, and takeover calls.
- Modify `test/test_vibepulse_visual_landmarks.py`: verify exact slot, muted states, physical negative space, overlays, and drift-relative alignment.
- Modify `test/run.sh`: run the new generator suite.
- Modify `platform/fonts/fetch-and-convert.sh`; delete `platform/fonts/torget_wifi_22.c` and `platform/fonts/LICENSE-FONTAWESOME.txt`: remove the superseded one-glyph font path.
- Modify `docs/lessons.md`: record the physical ownership/drift lesson.

### Task 1: Capture the rejected architecture as RED

**Files:**
- Modify: `test/test_lvgl_layer_safety.py`
- Modify: `sim/main.c`
- Modify: `test/test_vibepulse_visual_landmarks.py`

- [ ] **Step 1: Replace the old source assertions with the desired ownership contract**

Replace the current font/top-layer assertions in `test/test_lvgl_layer_safety.py` with:

```python
wifi_assets_header = (root / "platform/wifi_status_assets.h")
wifi_assets_source = (root / "platform/wifi_status_assets.c")

assert wifi_assets_header.exists(), "missing native Wi-Fi status assets"
assert wifi_assets_source.exists(), "missing generated Wi-Fi status source"
assert "tg.wifi_group = bare(tg.shift);" in platform_ui
assert "lv_obj_set_pos(tg.wifi_group, 426, 28)" in platform_ui
assert "lv_obj_set_size(tg.wifi_group, 20, 18)" in platform_ui
assert platform_ui.count("lv_image_create(tg.wifi_group)") == 1
assert "wifi_active_clip" not in platform_ui
assert "LV_SYMBOL_WIFI" not in platform_ui
assert "torget_wifi_22" not in platform_ui
assert "lv_arc_create" not in platform_ui
assert "lv_line_create(tg.wifi_group)" not in platform_ui
assert "lv_obj_set_style_transform" not in platform_ui
assert "tg_wifi_status_takeover_owner" in platform_header
assert "torget_wifi_status_set_takeover" in platform_header
assert "TG_WIFI_TAKEOVER_SETUP" in wifi_setup_ui
assert "TG_WIFI_TAKEOVER_OTA" in ota_ui
```

Keep the existing signal-state and network-task assertions unchanged.

- [ ] **Step 2: Add deterministic drift captures to the simulator harness**

Declare `static void pump_ms(uint32_t ms);` before the static QA functions. Add this helper beside `capture_global_wifi_matrix()`:

```c
static void capture_wifi_drift_matrix(void) {
  static const char *tags[5] = {
      "wifi-drift-0", "wifi-drift-1", "wifi-drift-2",
      "wifi-drift-3", "wifi-drift-return",
  };
  torget_app_show(SIM_APP_VIBEPULSE);
  feed_tokens();
  tokens_show_view(VIEW_CODEX_WEEKLY);
  sim_wifi_signal_bars = 3;
  torget_wifi_status_set_mode(TG_WIFI_STATUS_NORMAL);
  torget_wifi_status_foreground();
  dump_frame(tags[0]);
  for (int i = 1; i < 5; i++) {
    torget_drift_step();
    pump_ms(1300);
    dump_frame(tags[i]);
  }
}
```

Call `capture_wifi_drift_matrix();` immediately after `capture_global_wifi_matrix();` in `run_vibepulse_static_qa()`.

- [ ] **Step 3: Add the physical geometry and drift regression**

In `test/test_vibepulse_visual_landmarks.py`, replace the old `(418,38,446,66)` Wi-Fi assertions with a broad search box and add:

```python
    def test_wifi_header_mark_moves_with_the_header_drift(self):
        muted = self.NY_MUTED
        shifts = ((0, 0), (2, 1), (3, -1), (1, -2), (0, 0))
        for index, (dx, dy) in enumerate(shifts):
            tag = "return" if index == 4 else str(index)
            image = self.image(f"torget-wifi-drift-{tag}.bmp")
            pixels = [
                (x, y) for y in range(20, 64) for x in range(410, 458)
                if image.getpixel((x, y)) == muted
            ]
            with self.subTest(step=index):
                self.assertTrue(pixels)
                self.assertGreaterEqual(min(x for x, _ in pixels), 426 + dx)
                self.assertLessEqual(max(x for x, _ in pixels), 445 + dx)
                self.assertGreaterEqual(min(y for _, y in pixels), 28 + dy)
                self.assertLessEqual(max(y for _, y in pixels), 45 + dy)
                self.assertLess(max(y for _, y in pixels), 63 + dy)
```

Update the state-matrix contract so every state contains muted pixels only,
never white/provider colors, and the four cropped rasters are distinct.

- [ ] **Step 4: Run RED and record the expected failures**

Run:

```sh
PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python test/test_lvgl_layer_safety.py
cmake --build sim/build -j4
PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python \
  test/test_vibepulse_visual_landmarks.py
```

Expected: the source guard fails because the generated assets do not exist;
the independently invoked raster suite also fails because the current image
does not satisfy the new 20×18/muted/drift-relative geometry.

- [ ] **Step 5: Commit the regression only**

```sh
git add test/test_lvgl_layer_safety.py sim/main.c \
  test/test_vibepulse_visual_landmarks.py
git commit -m "test: reproduce WiFi header drift mismatch"
```

### Task 2: Generate four native final-size assets

**Files:**
- Create: `tools/wifi_status_assets/build_wifi_status_assets.py`
- Create: `tools/wifi_status_assets/test_build_wifi_status_assets.py`
- Create: `platform/wifi_status_assets.h`
- Create: `platform/wifi_status_assets.c`
- Modify: `test/run.sh`

- [ ] **Step 1: Write the failing generator test**

Create `tools/wifi_status_assets/test_build_wifi_status_assets.py` with a
clean missing-generator failure followed by the complete contracts:

```python
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("build_wifi_status_assets.py")


class WifiStatusAssetTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), "Wi-Fi asset generator is missing")
        spec = importlib.util.spec_from_file_location("wifi_assets", SCRIPT)
        self.build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.build)

    def test_four_native_states_are_distinct_and_deterministic(self):
        assets = self.build.build_assets()
        self.assertEqual(tuple(assets), ("offline", "weak", "medium", "strong"))
        self.assertEqual(len(set(assets.values())), 4)
        for data in assets.values():
            self.assertEqual(len(data), 64 + 20 * 18 // 2)

    def test_palette_and_transparent_corners_are_exact(self):
        for name, data in self.build.build_assets().items():
            palette, pixels = self.build.decode_i4(data)
            with self.subTest(name=name):
                self.assertEqual(palette[0], (0, 0, 0, 0))
                self.assertEqual(palette[1], (0xA2, 0x98, 0x92, 255))
                self.assertEqual(set(pixels) - {0, 1}, set())
                for index in (0, 19, 17 * 20, 18 * 20 - 1):
                    self.assertEqual(pixels[index], 0)

    def test_connected_states_keep_real_rows_between_bands(self):
        expected_components = {"weak": 2, "medium": 3, "strong": 4}
        for name, count in expected_components.items():
            pixels = self.build.decode_i4(self.build.build_assets()[name])[1]
            rows = [any(pixels[y * 20:(y + 1) * 20]) for y in range(18)]
            runs = sum(on and (y == 0 or not rows[y - 1])
                       for y, on in enumerate(rows))
            with self.subTest(name=name):
                self.assertEqual(runs, count)

    def test_checked_in_sources_are_byte_for_byte_generated(self):
        header, source = self.build.render_sources()
        self.assertEqual(header, self.build.OUT_H.read_text(encoding="utf-8"))
        self.assertEqual(source, self.build.OUT_C.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify clean RED**

Run:

```sh
./.venv/bin/python -m unittest \
  tools.wifi_status_assets.test_build_wifi_status_assets -v
```

Expected: FAIL with `Wi-Fi asset generator is missing`.

- [ ] **Step 3: Implement the deterministic final-pixel masks**

Create `build_wifi_status_assets.py` with the imports and output paths below.
Use these exact 20×18 rows for the
strong state; medium removes rows 1–3, weak also removes rows 6–8. Offline is
the strong mask with a two-pixel diagonal slash separated by a transparent
two-pixel gutter.

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_H = ROOT / "platform/wifi_status_assets.h"
OUT_C = ROOT / "platform/wifi_status_assets.c"
WIDTH, HEIGHT = 20, 18
EMPTY = "." * WIDTH
STRONG_ROWS = (
    EMPTY,
    ".....##########.....",
    "..###..........###..",
    ".##..............##.",
    EMPTY,
    EMPTY,
    "......########......",
    "....##........##....",
    "...##..........##...",
    EMPTY,
    EMPTY,
    "........####........",
    "......##....##......",
    EMPTY,
    EMPTY,
    ".........##.........",
    ".........##.........",
    EMPTY,
)
MUTED_BGRA = bytes((0xA2, 0x98, 0x92, 255))


def rows_for(name):
    rows = [list(row) for row in STRONG_ROWS]
    if name in ("medium", "weak"):
        for y in range(1, 4):
            rows[y] = list(EMPTY)
    if name == "weak":
        for y in range(6, 9):
            rows[y] = list(EMPTY)
    if name == "offline":
        for y in range(1, 17):
            x = y + 1
            for clear_x in range(max(0, x - 2), min(WIDTH, x + 4)):
                rows[y][clear_x] = "."
            for slash_x in (x, x + 1):
                if slash_x < WIDTH:
                    rows[y][slash_x] = "#"
    return tuple("".join(row) for row in rows)


def pack_i4(rows):
    palette = bytearray(64)
    palette[4:8] = MUTED_BGRA
    indices = [1 if pixel == "#" else 0 for row in rows for pixel in row]
    packed = bytearray(
        (indices[i] << 4) | indices[i + 1]
        for i in range(0, len(indices), 2)
    )
    return bytes(palette + packed)


def build_assets():
    return {name: pack_i4(rows_for(name))
            for name in ("offline", "weak", "medium", "strong")}


def decode_i4(data):
    palette = [tuple(data[i:i + 4]) for i in range(0, 64, 4)]
    pixels = []
    for byte in data[64:]:
        pixels.extend((byte >> 4, byte & 0x0F))
    return palette, pixels[:WIDTH * HEIGHT]


def c_array(name, data):
    rows = []
    for offset in range(0, len(data), 16):
        chunk = data[offset:offset + 16]
        rows.append("  " + ", ".join(f"0x{byte:02x}" for byte in chunk) + ",")
    return (f"static const uint8_t {name}[] = {{\n" +
            "\n".join(rows) + "\n};\n")


def descriptor(name, data_name, size):
    return f"""const lv_image_dsc_t {name} = {{
  .header = {{
    .magic = LV_IMAGE_HEADER_MAGIC,
    .cf = LV_COLOR_FORMAT_I4,
    .flags = 0,
    .w = 20,
    .h = 18,
    .stride = 10,
  }},
  .data_size = {size},
  .data = {data_name},
}};
"""


def render_sources():
    assets = build_assets()
    externs = "".join(
        f"extern const lv_image_dsc_t tk_img_wifi_{name};\n"
        for name in assets
    )
    header = f"""#ifndef WIFI_STATUS_ASSETS_H
#define WIFI_STATUS_ASSETS_H

#include "lvgl.h"

{externs}
#endif
"""
    source = '#include "wifi_status_assets.h"\n\n'
    for name, data in assets.items():
        source += c_array(f"tk_img_wifi_{name}_data", data)
    source += "\n"
    for name, data in assets.items():
        source += descriptor(
            f"tk_img_wifi_{name}", f"tk_img_wifi_{name}_data", len(data)
        )
    return header, source


def main():
    header, source = render_sources()
    OUT_H.write_text(header, encoding="utf-8")
    OUT_C.write_text(source, encoding="utf-8")


if __name__ == "__main__":
    main()
```

The generated header declares exactly `tk_img_wifi_offline`,
`tk_img_wifi_weak`, `tk_img_wifi_medium`, and `tk_img_wifi_strong`; every
descriptor is I4, `w=20`, `h=18`, `stride=10`, `data_size=244`.

- [ ] **Step 4: Generate sources and wire the suite once**

Run the generator, then add this line immediately after the agent asset suite
in `test/run.sh`:

```sh
"$PYTHON_BIN" -m unittest tools.wifi_status_assets.test_build_wifi_status_assets -v
```

Run:

```sh
./.venv/bin/python tools/wifi_status_assets/build_wifi_status_assets.py
./.venv/bin/python -m unittest \
  tools.wifi_status_assets.test_build_wifi_status_assets -v
```

Expected: all four asset tests PASS.

- [ ] **Step 5: Commit assets and generator**

```sh
git add tools/wifi_status_assets platform/wifi_status_assets.c \
  platform/wifi_status_assets.h test/run.sh
git commit -m "feat: add native WiFi status assets"
```

### Task 3: Replace the overlay tree with one drift-owned image

**Files:**
- Modify: `platform/torget_ui.c`
- Modify: `platform/torget.h`
- Modify: `components/torget_wifi/wifi_setup_ui.c`
- Modify: `components/torget_ota/ota_ui.c`
- Modify: `platform/boot_screen.c`
- Modify: `sim/CMakeLists.txt`
- Modify: `main/CMakeLists.txt`
- Modify: `test/test_wifi_onboarding_design.py`
- Delete: `platform/fonts/torget_wifi_22.c`
- Delete: `platform/fonts/LICENSE-FONTAWESOME.txt`
- Modify: `platform/fonts/fetch-and-convert.sh`

- [ ] **Step 1: Extend RED to takeover ownership and build wiring**

Before production edits, add source assertions that both CMake targets compile
`wifi_status_assets.c`, setup/OTA call the owner-specific API with `true` when
shown and `false` when hidden, and the Font Awesome Wi-Fi generator/file names
are absent. Run `test/test_lvgl_layer_safety.py`; expected FAIL on all new
contracts.

```python
sim_cmake = (root / "sim/CMakeLists.txt").read_text(encoding="utf-8")
main_cmake = (root / "main/CMakeLists.txt").read_text(encoding="utf-8")
font_generator = (root / "platform/fonts/fetch-and-convert.sh").read_text(
    encoding="utf-8"
)
assert "../platform/wifi_status_assets.c" in sim_cmake
assert "../platform/wifi_status_assets.c" in main_cmake
assert "torget_wifi_status_set_takeover(TG_WIFI_TAKEOVER_SETUP, true)" in wifi_setup_ui
assert "torget_wifi_status_set_takeover(TG_WIFI_TAKEOVER_SETUP, false)" in wifi_setup_ui
assert "torget_wifi_status_set_takeover(TG_WIFI_TAKEOVER_OTA, true)" in ota_ui
assert "torget_wifi_status_set_takeover(TG_WIFI_TAKEOVER_OTA, false)" in ota_ui
assert "torget_wifi_22" not in font_generator
assert not (root / "platform/fonts/torget_wifi_22.c").exists()
assert not (root / "platform/fonts/LICENSE-FONTAWESOME.txt").exists()
```

- [ ] **Step 2: Add the takeover-owner API**

In `platform/torget.h`, retain the existing status-mode enum and add:

```c
typedef enum {
  TG_WIFI_TAKEOVER_SETUP = 1u << 0,
  TG_WIFI_TAKEOVER_OTA = 1u << 1,
} tg_wifi_status_takeover_owner;

void torget_wifi_status_set_takeover(
    tg_wifi_status_takeover_owner owner, bool active);
```

The owner bitmask is required because OTA can cover an already-visible Wi-Fi
setup screen; closing OTA must reveal setup without reparenting the icon behind
it or losing setup's strong-state presentation.

- [ ] **Step 3: Implement the single-image platform tree**

In `platform/torget_ui.c`, include `wifi_status_assets.h`; replace the four old
object pointers with one `wifi_image` and a `uint8_t wifi_takeovers`. Map the
effective state as follows:

```c
static tg_wifi_status_mode wifi_effective_mode(void) {
  if (tg.wifi_mode == TG_WIFI_STATUS_HIDDEN) return TG_WIFI_STATUS_HIDDEN;
  if (tg.wifi_takeovers & TG_WIFI_TAKEOVER_OTA) return TG_WIFI_STATUS_NORMAL;
  if (tg.wifi_takeovers & TG_WIFI_TAKEOVER_SETUP) return TG_WIFI_STATUS_SETUP;
  return tg.wifi_mode;
}

static const lv_image_dsc_t *wifi_asset_for(uint8_t bars) {
  static const lv_image_dsc_t *const assets[4] = {
      &tk_img_wifi_offline, &tk_img_wifi_weak,
      &tk_img_wifi_medium, &tk_img_wifi_strong,
  };
  return assets[bars > 3 ? 3 : bars];
}
```

Create the host with `bare(tg.shift)`, position `(426,28)`, size `20×18`, and
one `lv_image_create(tg.wifi_group)`. Rendering chooses strong for effective
SETUP and otherwise `torget_wifi_signal_bars()`, then calls only
`lv_image_set_src()` when the state changes.

```c
static void wifi_status_create(void) {
  tg.wifi_mode = TG_WIFI_STATUS_HIDDEN;
  tg.wifi_group = bare(tg.shift);
  lv_obj_set_pos(tg.wifi_group, 426, 28);
  lv_obj_set_size(tg.wifi_group, 20, 18);
  tg.wifi_image = lv_image_create(tg.wifi_group);
  lv_obj_remove_style_all(tg.wifi_image);
  lv_obj_set_pos(tg.wifi_image, 0, 0);
  lv_obj_remove_flag(tg.wifi_image, LV_OBJ_FLAG_CLICKABLE);
  wifi_status_render();
  lv_timer_create(wifi_status_timer, 1000, NULL);
}
```

Implement reparenting without recreation:

```c
void torget_wifi_status_set_takeover(
    tg_wifi_status_takeover_owner owner, bool active) {
  if (owner != TG_WIFI_TAKEOVER_SETUP && owner != TG_WIFI_TAKEOVER_OTA) return;
  if (active) tg.wifi_takeovers |= (uint8_t)owner;
  else tg.wifi_takeovers &= (uint8_t)~owner;
  lv_obj_t *parent = tg.wifi_takeovers ? lv_layer_top() : tg.shift;
  if (lv_obj_get_parent(tg.wifi_group) != parent) {
    lv_obj_set_parent(tg.wifi_group, parent);
    lv_obj_set_pos(tg.wifi_group, 426, 28);
  }
  wifi_status_render();
  if (wifi_effective_mode() != TG_WIFI_STATUS_HIDDEN)
    lv_obj_move_foreground(tg.wifi_group);
}
```

- [ ] **Step 4: Convert takeover callers and remove the font path**

Wi-Fi setup calls `torget_wifi_status_set_takeover(TG_WIFI_TAKEOVER_SETUP,
true)` after moving its overlay forward and calls the same API with `false`
after hiding. OTA does the equivalent with `TG_WIFI_TAKEOVER_OTA`. Boot leaves
both bits clear and restores NORMAL. Keep `torget_wifi_status_foreground()` as
a same-parent ordering helper for existing simulator/boot calls.

```c
/* Wi-Fi setup: hidden branch / visible branch. */
torget_wifi_status_set_takeover(TG_WIFI_TAKEOVER_SETUP, false);
/* ... */
lv_obj_move_foreground(ui.overlay);
torget_wifi_status_set_takeover(TG_WIFI_TAKEOVER_SETUP, true);

/* OTA: hidden branch / visible branch. */
torget_wifi_status_set_takeover(TG_WIFI_TAKEOVER_OTA, false);
/* ... */
lv_obj_move_foreground(ui.overlay);
torget_wifi_status_set_takeover(TG_WIFI_TAKEOVER_OTA, true);
```

Delete `torget_wifi_22.c` and the now-unused Font Awesome license; remove
`FA_URL`, `FA_FONT`, the `font_conv` invocation, and its status `echo` from
`fetch-and-convert.sh`.

Add `../platform/wifi_status_assets.c` to both `sim/CMakeLists.txt` and the
`SRCS` list in `main/CMakeLists.txt`.

- [ ] **Step 5: Run focused GREEN**

Run:

```sh
cmake -S sim -B sim/build -G Ninja
cmake --build sim/build -j4
PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python test/test_lvgl_layer_safety.py
PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python \
  test/test_wifi_onboarding_design.py
./.venv/bin/python -m unittest \
  tools.wifi_status_assets.test_build_wifi_status_assets -v
```

Expected: all commands PASS; no compiled or source reference to
`torget_wifi_22`, clipped labels, runtime scaling, arcs, or slash lines remains.

- [ ] **Step 6: Commit the platform integration**

```sh
git add platform components/torget_wifi/wifi_setup_ui.c \
  components/torget_ota/ota_ui.c sim/CMakeLists.txt main/CMakeLists.txt \
  test/test_lvgl_layer_safety.py test/test_wifi_onboarding_design.py
git commit -m "fix: integrate WiFi status into shared header"
```

### Task 4: Prove exact 480×480 geometry and stop for visual approval

**Files:**
- Modify: `test/test_vibepulse_visual_landmarks.py`
- Modify: `sim/main.c`

- [ ] **Step 1: Run the static QA and focused raster suite**

```sh
cmake --build sim/build -j4
PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python \
  test/test_vibepulse_visual_landmarks.py
```

Expected: all existing frames plus four drift frames pass. Connected states
contain only `#9298A2`, fit within translated `(426,28,20,18)`, stay above the
translated divider, and remain distinct on every ordinary surface.

- [ ] **Step 2: Verify overlays and nested takeover behavior**

Add this deterministic simulator sequence after the drift matrix:

```c
static void capture_wifi_takeover_stack(void) {
  torget_wifi_ui_set(TG_WIFI_UI_OPEN, "VibePulse-setup", "panel-test",
                     NULL, 600);
  dump_frame("wifi-takeover-setup");
  torget_ota_ui_set(TG_OTA_UI_NOTICE, 0, 0);
  dump_frame("wifi-takeover-ota-over-setup");
  torget_ota_ui_set(TG_OTA_UI_HIDDEN, 0, 0);
  dump_frame("wifi-takeover-setup-restored");
  torget_wifi_ui_set(TG_WIFI_UI_HIDDEN, NULL, NULL, NULL, 0);
  dump_frame("wifi-takeover-page-restored");
}
```

Call it after `capture_wifi_drift_matrix()`. In the raster test, crop
`(410,20,458,64)` from all four captures and assert that each has exactly one
connected muted status mark; assert that setup, OTA-over-setup, and restored
setup use identical strong crops, while the final page crop equals the current
strong ordinary-state crop at returned drift `(0,0)`. Run the raster test and
expect PASS.

- [ ] **Step 3: Run design and live preview gates**

```sh
PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python \
  tools/vibepulse_studio/design.py --check
PATH="$PWD/.venv/bin:$PATH" ./tools/preview-ui.sh vibepulse
```

Expected: both exit zero and export the exact 480×480 preview set.

- [ ] **Step 4: Inspect and show representative renders**

Inspect at 1:1:

- Codex strong, medium, weak, and offline;
- Claude strong;
- GitHub and Value;
- launcher;
- Wi-Fi setup;
- OTA over setup;
- all four drift positions.

Confirm the mark is subordinate to the 14-pixel context text, has at least 17
black pixels before the divider, preserves transparent band gaps, and never
appears twice. Show the exact strong/weak/offline and takeover images to the
user. Stop here for explicit visual approval; do not build or flash firmware.

- [ ] **Step 5: Commit the visual contracts**

```sh
git add sim/main.c test/test_vibepulse_visual_landmarks.py
git commit -m "test: pin WiFi header placement across drift"
```

### Task 5: Full verification and firmware preparation after visual approval

**Files:**
- Modify: `docs/lessons.md`

- [ ] **Step 1: Record the physical lesson**

Append this exact paragraph to `docs/lessons.md`:

```markdown
- A status mark that belongs visually to a drifting AMOLED header must share
  that header's translated owner. A fixed `lv_layer_top()` object can pass an
  absolute-coordinate simulator test while walking out of alignment with the
  page every minute on the panel. Test relative ownership and spacing across
  every drift step; use the top layer only while a true full-screen takeover
  owns the glass, and reparent the same object back afterward.
```

- [ ] **Step 2: Run the complete repository gate**

```sh
PYTHON_BIN="$PWD/.venv/bin/python" ./test/run.sh
```

Expected: all host C, Python, simulator, asset-regeneration, visual, source,
Worker, and interaction-relay tests PASS.

- [ ] **Step 3: Build one ESP32-S3 artifact without changing partitions**

Use the repository's existing ESP-IDF 5.5 environment and ignored local
configuration:

```sh
source "$HOME/esp/esp-idf/export.sh"
idf.py build
```

Confirm `platform/torget_ui.c` and
`platform/wifi_status_assets.c` compile and `build/torget.bin` links. Do not
invoke esptool, otatool, reset, or any partition switch.

- [ ] **Step 4: Commit the lesson and report the physical gate**

```sh
git add docs/lessons.md
git commit -m "docs: record WiFi header ownership lesson"
git status --short
git diff --check HEAD~1
```

Expected: clean worktree and clean diff check. Report the preview directory,
test totals, firmware path/SHA-256, and exact commit. Ask for explicit
authorization before writing only `ota_1`; never touch `ota_0`.
