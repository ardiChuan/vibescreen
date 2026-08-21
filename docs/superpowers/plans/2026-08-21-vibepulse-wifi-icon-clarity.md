# VibePulse Wi-Fi Icon Clarity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the physical one-bar Wi-Fi state read as a complete familiar Wi-Fi symbol while preserving the existing global geometry and 0–3 RSSI semantics.

**Architecture:** Keep the existing three LVGL arcs, dot, slash, platform ownership, and packed signal state. Raise only the inactive-arc contrast to the already approved neutral grey and pin it with exact simulator pixels and cross-surface captures.

**Tech Stack:** C11, LVGL 9.5, SDL simulator, Pillow visual regression tests.

---

### Task 1: Pin the physical-contrast regression

**Files:**
- Modify: `test/test_vibepulse_visual_landmarks.py`
- Modify: `test/test_wifi_onboarding_design.py`

- [ ] **Step 1: Write the failing tests**

Change the Wi-Fi inactive color contract to `(146, 152, 162)` / `#9298A2` and require inactive ink in every 0/1/2-bar capture:

```python
inactive = self._count(image, box, self.NY_MUTED)
if bars < 3:
    self.assertGreater(inactive, 10)
```

Pin the design JSON assertion to:

```python
"inactiveColor": "#9298A2"
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```sh
PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python \
  test/test_vibepulse_visual_landmarks.py -k global_wifi_icon -v
./.venv/bin/python test/test_wifi_onboarding_design.py -v
```

Expected: failure because the renderer/design still use `#5C687B`.

- [ ] **Step 3: Commit the RED tests only if the repository convention requires a checkpoint**

Do not include captures or production changes in this checkpoint.

### Task 2: Raise inactive-arc contrast without changing behavior

**Files:**
- Modify: `platform/torget_ui.c`
- Modify: `design/vibepulse/studio-design.json`

- [ ] **Step 1: Apply the minimal renderer change**

Use the existing neutral UI grey:

```c
#define COL_WIFI_MUTED lv_color_hex(0x9298A2)
```

Keep `wifi_status_render()`, all sizes/positions, active-white mapping, and the disconnected slash unchanged. Align the design JSON `inactiveColor` with the same value.

- [ ] **Step 2: Build the simulator and regenerate exact Wi-Fi captures**

Run:

```sh
cmake -S sim -B sim/build
cmake --build sim/build -j4
TORGET_CAPTURE_DIR=/tmp/vibepulse-wifi-contrast \
  ./sim/build/torget-sim --vibepulse-static-qa
```

Expected: build succeeds and all `torget-wifi-global-*-{0,1,2,3}.bmp` files exist.

- [ ] **Step 3: Run GREEN tests**

Run:

```sh
PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python test/test_vibepulse_visual_landmarks.py -v
./.venv/bin/python test/test_lvgl_layer_safety.py
./.venv/bin/python test/test_wifi_onboarding_design.py -v
./.venv/bin/python tools/vibepulse_studio/design.py --check
```

Expected: all pass; the four signal signatures remain distinct and provider colors are absent.

- [ ] **Step 4: Inspect at 1:1**

Inspect the one-bar launcher, Claude, Codex, GitHub/value, and OTA captures. Confirm the complete outer silhouette is visible, the icon remains within `(418,38)..(446,66)`, and the ten-pixel header gap stays black.

- [ ] **Step 5: Commit**

```sh
git add platform/torget_ui.c design/vibepulse/studio-design.json \
  test/test_vibepulse_visual_landmarks.py test/test_wifi_onboarding_design.py
git commit -m "fix: clarify weak WiFi signal icon"
```
