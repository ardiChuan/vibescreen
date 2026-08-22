# Wi-Fi Setup Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify the panel QR screen and make the phone password field unambiguous.

**Architecture:** Keep the existing setup overlay and captive portal. Add one
local QR/manual presentation toggle, retain the automatic manual fallback, and
carry the scan authentication mode through the existing form boundary so both
the browser and firmware enforce the same rule.

**Tech Stack:** ESP-IDF 5.5, LVGL 9.5, ESP HTTP server, Python raster/static tests.

---

### Task 1: Lock the panel contract

**Files:**
- Modify: `design/vibepulse/wifi-onboarding-design.json`
- Modify: `test/test_wifi_onboarding_design.py`
- Modify: `test/test_vibepulse_visual_landmarks.py`
- Modify: `sim/main.c`

- [ ] Add failing assertions for the 90 px manual/back control and the absence
  of password/address ink on the primary QR view.
- [ ] Run the focused design and raster tests and confirm they fail on the old
  crowded screen.
- [ ] Add deterministic primary and manual captures.

### Task 2: Implement the two panel views

**Files:**
- Modify: `components/torget_wifi/wifi_setup_ui.c`
- Modify: `components/torget_wifi/wifi_setup_ui.h`

- [ ] Add the reusable outlined control and QR/manual event callbacks.
- [ ] Render secrets and the fallback address only in manual mode; enter manual
  mode automatically when QR generation fails.
- [ ] Clear manual state and credential buffers when the overlay closes.
- [ ] Run the focused design, layer-safety, simulator, and raster tests green.

### Task 3: Make the phone form exact

**Files:**
- Modify: `components/torget_wifi/wifi_setup.c`
- Modify: `test/test_wifi_setup_wiring.py`

- [ ] Add failing tests for secured required-password copy, open-network field
  hiding, per-option authentication metadata, and server-side enforcement.
- [ ] Preserve each scanned network's authentication mode through sorting and
  HTML generation.
- [ ] Update the browser label dynamically and validate the selected network
  again in `POST /join`.
- [ ] Run the focused wiring and host tests green.

### Task 4: Verify the complete change

**Files:**
- Modify only if required by verified output: preview manifest or checked-in
  Wi-Fi onboarding documentation image.

- [ ] Run `python3 tools/vibepulse_studio/design.py --check`.
- [ ] Build the simulator and inspect exact 480 x 480 QR/manual captures at 1:1.
- [ ] Run `tools/preview-ui.sh vibepulse` and `./test/run.sh` with the repository
  Python environment.
- [ ] Run a fresh ESP-IDF target build, review the scoped diff, and stop before
  flashing until the user explicitly authorizes it.
