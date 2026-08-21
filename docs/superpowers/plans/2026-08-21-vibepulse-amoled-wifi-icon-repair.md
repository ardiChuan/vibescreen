# VibePulse AMOLED Wi-Fi Icon Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the cloud-like physical Wi-Fi mark with a familiar native-size symbol that has AMOLED-safe negative space and a reserved top-right slot on every surface.

**Architecture:** A dedicated 24 px, one-glyph Font Awesome LVGL font supplies the standard Wi-Fi silhouette without runtime scaling or a large general font. The shared platform layer draws one muted base glyph plus a clipped white foreground glyph for 0/1/2/3 strength; every page keeps the existing `(418, 38, 28, 28)` header slot clear.

**Tech Stack:** C11, LVGL 9.5, `lv_font_conv`, Python `unittest`/Pillow raster assertions, CMake/Ninja simulator, ESP-IDF 5.5.

---

### Task 1: Capture the physical silhouette failure

**Files:**
- Modify: `test/test_vibepulse_visual_landmarks.py`
- Modify: `test/test_lvgl_layer_safety.py`

- [ ] **Step 1: Add the failing raster contract**

Replace the old row-gap-only check with a standard-symbol contract that finds
the three white/muted lobes and requires at least two full black pixels between
adjacent lobes on representative diagonal samples. Also assert that every
`WIFI_GLOBAL_SURFACES` capture keeps the ten-pixel lane immediately left of the
icon black.

```python
def test_global_wifi_icon_preserves_amoled_safe_negative_space(self):
    image = self.image("torget-wifi-global-claude-3.bmp")
    # These two interior windows sit between the standard glyph's lobes.
    for box in ((424, 49, 440, 52), (428, 55, 436, 58)):
        black = self._count(image, box, (0, 0, 0))
        self.assertGreaterEqual(black, (box[2] - box[0]) * 2)
```

- [ ] **Step 2: Pin the source architecture before production edits**

Require `torget_wifi_24`, two glyph labels, one foreground clipping object, no
`lv_arc_create`, no transforms, and the unchanged global slot/top layer.

```python
assert "extern const lv_font_t torget_wifi_24;" in platform_ui
assert platform_ui.count("LV_SYMBOL_WIFI") == 2
assert "wifi_active_clip" in platform_ui
assert "lv_arc_create" not in platform_ui
assert "lv_obj_set_style_transform" not in platform_ui
```

- [ ] **Step 3: Run RED and record the expected failure**

Run:

```sh
PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python -m unittest \
  test.test_vibepulse_visual_landmarks.VibePulseVisualLandmarkTests.test_global_wifi_icon_preserves_amoled_safe_negative_space -v
PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python test/test_lvgl_layer_safety.py
```

Expected: the raster assertion fails on the one-pixel arc gaps and the source
guard fails because the old implementation still uses three `lv_arc` objects.

- [ ] **Step 4: Commit the regression only**

```sh
git add test/test_vibepulse_visual_landmarks.py test/test_lvgl_layer_safety.py
git commit -m "test: reproduce AMOLED WiFi icon bloom"
```

### Task 2: Add the one-glyph native font

**Files:**
- Modify: `platform/fonts/fetch-and-convert.sh`
- Create: `platform/fonts/torget_wifi_24.c`
- Create: `platform/fonts/LICENSE-FONTAWESOME.txt`
- Modify: `test/test_lvgl_layer_safety.py`

- [ ] **Step 1: Extend the red source contract to the exact font descriptor**

```python
wifi_font = (root / "platform/fonts/torget_wifi_24.c").read_text(encoding="utf-8")
assert "const lv_font_t torget_wifi_24" in wifi_font
assert ".line_height = 24" in wifi_font
assert "0xF1EB" in (root / "platform/fonts/fetch-and-convert.sh").read_text()
```

- [ ] **Step 2: Run the source guard and verify it fails because the font is absent**

Run: `PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python test/test_lvgl_layer_safety.py`

Expected: FAIL opening `platform/fonts/torget_wifi_24.c`.

- [ ] **Step 3: Generate only U+F1EB at its final size**

Add the stable Font Awesome Free font download and conversion beside the Plex
conversions:

```sh
FA_URL="https://raw.githubusercontent.com/lvgl/lvgl/v9.5.0/scripts/built_in_font/FontAwesome5-Solid+Brands+Regular.woff"
[ -f src/FontAwesome5-Solid+Brands+Regular.woff ] || \
  curl -fsSL "$FA_URL" -o src/FontAwesome5-Solid+Brands+Regular.woff
font_conv --font src/FontAwesome5-Solid+Brands+Regular.woff --size 24 \
  --bpp 4 --format lvgl --no-compress --range 0xF1EB \
  -o torget_wifi_24.c
```

Copy the upstream Font Awesome Free font license text into
`platform/fonts/LICENSE-FONTAWESOME.txt`, run the converter, and ensure the
generated source ends with exactly one newline.

- [ ] **Step 4: Run the source guard and simulator compile**

Run:

```sh
PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python test/test_lvgl_layer_safety.py
cmake -S sim -B sim/build -G Ninja
cmake --build sim/build -j4
```

Expected: the font descriptor guard passes; the source architecture guard
remains red until Task 3; the generated font compiles in the shared simulator.

- [ ] **Step 5: Commit the native font**

```sh
git add platform/fonts/fetch-and-convert.sh platform/fonts/torget_wifi_24.c \
  platform/fonts/LICENSE-FONTAWESOME.txt test/test_lvgl_layer_safety.py
git commit -m "feat: add native WiFi status glyph"
```

### Task 3: Replace arcs with clipped native labels

**Files:**
- Modify: `platform/torget_ui.c`
- Modify: `test/test_vibepulse_visual_landmarks.py`
- Modify: `test/test_lvgl_layer_safety.py`

- [ ] **Step 1: Implement the smallest shared-label tree**

Replace `wifi_arc[3]` with base/active labels and a clip container:

```c
lv_obj_t *wifi_base;
lv_obj_t *wifi_active_clip;
lv_obj_t *wifi_active;
```

Create the base at the exact native font size, create an identically positioned
white child inside a clipping container, and keep the current slash:

```c
extern const lv_font_t torget_wifi_24;

tg.wifi_base = lv_label_create(tg.wifi_group);
lv_label_set_text(tg.wifi_base, LV_SYMBOL_WIFI);
lv_obj_set_style_text_font(tg.wifi_base, &torget_wifi_24, 0);
lv_obj_set_style_text_color(tg.wifi_base, COL_WIFI_MUTED, 0);
lv_obj_center(tg.wifi_base);

tg.wifi_active_clip = bare(tg.wifi_group);
tg.wifi_active = lv_label_create(tg.wifi_active_clip);
lv_label_set_text(tg.wifi_active, LV_SYMBOL_WIFI);
lv_obj_set_style_text_font(tg.wifi_active, &torget_wifi_24, 0);
lv_obj_set_style_text_color(tg.wifi_active, lv_color_white(), 0);
```

For bars 0/1/2/3, set the clip height to 0/8/16/24 px from the bottom and
offset the child upward by the same clip origin. Hide the foreground clip at
zero bars and show the unchanged slash only at zero bars.

- [ ] **Step 2: Run focused GREEN**

Run:

```sh
cmake --build sim/build -j4
PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python test/test_lvgl_layer_safety.py
PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python -m unittest \
  test.test_vibepulse_visual_landmarks.VibePulseVisualLandmarkTests.test_global_wifi_icon_is_neutral_consistent_and_distinct \
  test.test_vibepulse_visual_landmarks.VibePulseVisualLandmarkTests.test_global_wifi_icon_preserves_amoled_safe_negative_space -v
```

Expected: PASS; all four bar states remain distinct and the full symbol has
AMOLED-safe internal black space.

- [ ] **Step 3: Verify the reserved header slot on every surface**

Generate `--vibepulse-static-qa`, then assert each surface has no non-black
pixels in `(408, 38, 418, 66)` and that the icon bounding box stays exactly
inside `(418, 38, 446, 66)`.

- [ ] **Step 4: Commit the render change**

```sh
git add platform/torget_ui.c test/test_vibepulse_visual_landmarks.py \
  test/test_lvgl_layer_safety.py
git commit -m "fix: use native AMOLED WiFi silhouette"
```

### Task 4: Visual and target verification

**Files:**
- Modify: `docs/lessons.md`

- [ ] **Step 1: Record the physical-display lesson**

Document that a simulator-visible one-pixel gap between bright rounded strokes
is not an AMOLED-safe negative space; shared header chrome must also have a
reserved lane on every surface.

- [ ] **Step 2: Run the exact visual workflow**

Run:

```sh
cmake -S sim -B sim/build -G Ninja
cmake --build sim/build -j4
PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python \
  test/test_vibepulse_visual_landmarks.py
PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python test/test_lvgl_layer_safety.py
PATH="$PWD/.venv/bin:$PATH" ./tools/preview-ui.sh vibepulse
```

Expected: all commands exit zero. Inspect the exported 0/1/2/3 captures at
1:1 and confirm the symbol reads as Wi-Fi, the black internal spaces remain
open, and no page text enters the reserved slot.

- [ ] **Step 3: Run the full repository gate**

Run: `PYTHON_BIN="$PWD/.venv/bin/python" ./test/run.sh`

Expected: all host C, Python, simulator, visual, source, and Worker tests pass.

- [ ] **Step 4: Build the ESP32-S3 image without touching rollback state**

Run the repository's ESP-IDF 5.5 build with existing local ignored secrets and
configuration. Do not switch partitions or write flash. Confirm
`platform/torget_ui.c` and `platform/fonts/torget_wifi_24.c` compile and the
final `build/torget.bin` links successfully.

- [ ] **Step 5: Commit documentation and report the flash gate**

```sh
git add docs/lessons.md
git commit -m "docs: record AMOLED icon spacing lesson"
```

Report the 1:1 preview path, test results, firmware artifact, and exact commit.
Ask for explicit authorization before writing only ota_1; never touch ota_0.
