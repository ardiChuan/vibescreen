# VibePulse Wi-Fi Onboarding and Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user add a 2.4 GHz Wi-Fi network by scanning the panel, show unmistakable Wi-Fi state across the panel, suppress Claude's duplicate internal `AskUserQuestion` approval, and prove the new redraw path does not wedge LVGL.

**Architecture:** Keep network ownership in `components/torget_wifi`: a pure QR payload builder and pure setup policy are host-tested, while the ESP adapter owns SoftAP, DNS, HTTP, and trial credentials. Put one neutral connectivity object in the shared platform layer so every app and Needs You screen uses the same icon. Keep Claude deduplication at the tokenserver store boundary, and split Needs You's stable repaint from its ring-only update so the 10 Hz countdown does not rebuild the entire screen.

**Tech Stack:** C11, ESP-IDF 5.5, FreeRTOS, LVGL 9.5 `lv_qrcode`, SDL simulator, Python `unittest`, Pillow raster checks, CMake, GitHub Actions.

---

## File map

### New files

- `cmake/torget_lvgl_qrcode_guard.cmake` — reject target configurations without the official QR widget and explain stale-`sdkconfig` recovery.
- `components/torget_wifi/wifi_qr_payload.h` / `.c` — pure, bounded Wi-Fi QR grammar and escaping.
- `test/test_wifi_qr_payload.c` — host tests for exact and escaped QR payloads.
- `test/test_lvgl_qrcode_config.py` — target/simulator/default/build parity.
- `design/vibepulse/wifi-onboarding-design.json` — accepted 480 x 480 onboarding geometry.
- `test/test_wifi_onboarding_design.py` — schema, bounds, readability, and source-token alignment.

### Main modified files

- `components/torget_wifi/wifi_slots.[ch]` — setup phases, input ownership, retry and reason policy.
- `components/torget_wifi/wifi_setup.[ch]` — immediate STARTING, task notification, trial credentials, delayed NVS commit, `/status`.
- `components/torget_wifi/wifi_setup_ui.[ch]` — QR/manual UI and no-op render guard.
- `platform/torget.h`, `platform/torget_ui.c` — one global neutral Wi-Fi object.
- `main/main.c` — radio hooks, atomic disconnect reason, KEY3 suppression, diagnostics.
- `components/app_tokens/agent_monitor.[ch]` — remove private Wi-Fi copy and split full/ring redraw.
- `tools/tokenserver/interactions.py` — reject the duplicate internal Claude permission.
- `sim/main.c` and exact raster tests — deterministic UI and redraw evidence.
- build defaults/guards, preview manifest, README and Wi-Fi/agent docs.

## Task 1: Reject duplicate Claude `AskUserQuestion` permissions

**Files:**
- Modify: `tools/tokenserver/test_interactions.py`
- Modify: `tools/tokenserver/interactions.py`
- Modify: `docs/agent-setup.md`

- [ ] **Step 1: Write the failing store and HTTP regressions**

```python
def test_internal_question_permission_never_replaces_real_question(self):
    question = self.store.park("question", question_event(), 120)
    self.assertIsNotNone(question)
    before = self.store.pending_public()

    duplicate = approval_event()
    duplicate["tool_name"] = "  ASKUSERQUESTION  "
    duplicate["tool_input"] = {
        "questions": question_event()["tool_input"]["questions"],
    }
    self.assertIsNone(self.store.park("approval", duplicate, 120))
    self.assertEqual(self.store.pending_public(), before)
```

Add an HTTP test that holds `/api/hook/question`, posts the later `/api/hook/permission`, expects no decision promptly, and proves the pending `request_id` did not change.

- [ ] **Step 2: Run RED**

```bash
./.venv/bin/python -m unittest \
  tools.tokenserver.test_interactions.StoreTests.test_internal_question_permission_never_replaces_real_question \
  tools.tokenserver.test_interactions.HttpEndToEndTests.test_internal_question_permission_is_not_parked -v
```

Expected: FAIL because generic approval currently parks `AskUserQuestion`.

- [ ] **Step 3: Implement the store-boundary filter**

```python
def _is_internal_question_permission(kind: str,
                                     event: Dict[str, Any]) -> bool:
    tool = event.get("tool_name")
    return (kind == "approval" and isinstance(tool, str) and
            tool.strip().casefold() == "askuserquestion")
```

At the start of `_park_claude`, after outer shape validation:

```python
if _is_internal_question_permission(kind, event):
    return None
```

- [ ] **Step 4: Run GREEN, update the hook rationale, and commit**

```bash
./.venv/bin/python -m unittest \
  tools.tokenserver.test_interactions tools.tokenserver.test_tokenserver -v
git add tools/tokenserver/interactions.py \
  tools/tokenserver/test_interactions.py docs/agent-setup.md
git commit -m "fix: ignore duplicate Claude question permissions"
```

## Task 2: Enable and guard the official QR path

**Files:**
- Create: `cmake/torget_lvgl_qrcode_guard.cmake`
- Create: `components/torget_wifi/wifi_qr_payload.[ch]`
- Create: `test/test_wifi_qr_payload.c`
- Create: `test/test_lvgl_qrcode_config.py`
- Modify: `CMakeLists.txt`, `sdkconfig.defaults`, `sim/lv_conf.h`
- Modify: `components/torget_wifi/CMakeLists.txt`, `sim/CMakeLists.txt`, `test/run.sh`

- [ ] **Step 1: Write RED grammar/configuration tests**

```c
char payload[TG_WIFI_QR_PAYLOAD_CAP];
check("standard WPA payload",
      tg_wifi_qr_payload(payload, sizeof payload,
                         "VibePulse-setup", "A1B2C3D4E5F6") &&
      strcmp(payload,
             "WIFI:T:WPA;S:VibePulse-setup;P:A1B2C3D4E5F6;H:false;;") == 0);
check("reserved characters escaped",
      tg_wifi_qr_payload(payload, sizeof payload, "Cafe;West", "ab\\cd:12") &&
      strcmp(payload,
             "WIFI:T:WPA;S:Cafe\\;West;P:ab\\\\cd\\:12;H:false;;") == 0);
check("small output fails closed",
      !tg_wifi_qr_payload(payload, 16,
                          "VibePulse-setup", "A1B2C3D4E5F6"));
```

Python tests require disabled/absent QR config to fail with `sdkconfig is stale`, `CONFIG_LV_USE_QRCODE=y`, and `idf.py reconfigure && idf.py build`; target defaults and `sim/lv_conf.h` must agree.

- [ ] **Step 2: Run RED**

```bash
cc -std=c11 -Wall -Wextra -Werror -O1 \
  components/torget_wifi/wifi_qr_payload.c \
  test/test_wifi_qr_payload.c -o /tmp/torget-wifi-qr-test
/tmp/torget-wifi-qr-test
./.venv/bin/python test/test_lvgl_qrcode_config.py -v
```

- [ ] **Step 3: Implement bounded payload and guard**

```c
#define TG_WIFI_QR_PAYLOAD_CAP 192
bool tg_wifi_qr_payload(char *out, size_t cap,
                        const char *ssid, const char *password);
```

Build incrementally; escape `\`, `;`, `,`, `:`, and `"`; validate existing SSID/password caps; clear output on failure.

```cmake
function(torget_require_lvgl_qrcode enabled)
  if(NOT "${enabled}" STREQUAL "y")
    message(FATAL_ERROR
      "LVGL QR support is disabled. The generated sdkconfig is stale: set "
      "CONFIG_LV_USE_QRCODE=y (matching sdkconfig.defaults), then run: "
      "idf.py reconfigure && idf.py build")
  endif()
endfunction()
```

Add `CONFIG_LV_USE_QRCODE=y` and simulator `#define LV_USE_QRCODE 1`.

- [ ] **Step 4: Run GREEN, simulator build, and commit**

```bash
cmake -S sim -B sim/build -G Ninja
cmake --build sim/build -j4
git add cmake/torget_lvgl_qrcode_guard.cmake CMakeLists.txt \
  sdkconfig.defaults sim/lv_conf.h sim/CMakeLists.txt \
  components/torget_wifi/wifi_qr_payload.h \
  components/torget_wifi/wifi_qr_payload.c \
  components/torget_wifi/CMakeLists.txt test/test_wifi_qr_payload.c \
  test/test_lvgl_qrcode_config.py test/run.sh
git commit -m "feat: add guarded WiFi QR payload support"
```

## Task 3: Make KEY3 setup entry immediate and deterministic

**Files:**
- Modify: `components/torget_wifi/wifi_slots.[ch]`
- Modify: `components/torget_wifi/wifi_setup.[ch]`
- Modify: `components/torget_wifi/wifi_setup_ui.h`
- Modify: `main/main.c`
- Modify: `test/test_wifi_slots.c`, `test/test_wifi_setup_wiring.py`

- [ ] **Step 1: Write RED phase/input tests**

```c
check("starting owns KEY3", tg_wifi_setup_owns_input(TG_WIFI_PHASE_STARTING));
check("open owns KEY3", tg_wifi_setup_owns_input(TG_WIFI_PHASE_OPEN));
check("joining owns KEY3", tg_wifi_setup_owns_input(TG_WIFI_PHASE_JOINING));
check("idle leaves KEY3 to apps", !tg_wifi_setup_owns_input(TG_WIFI_PHASE_IDLE));
check("failed is dismissible", tg_wifi_setup_can_close(TG_WIFI_PHASE_FAILED));
check("starting ignores accidental release",
      !tg_wifi_setup_can_close(TG_WIFI_PHASE_STARTING));
```

The wiring test requires request-open to wake the guard, STARTING before `window_open()`, and the starting check before app/OTA/panic actions.

- [ ] **Step 2: Run RED**

```bash
cc -std=c11 -Wall -Wextra -Werror -O1 \
  components/torget_wifi/wifi_slots.c test/test_wifi_slots.c \
  -o /tmp/torget-wifi-slots-test
/tmp/torget-wifi-slots-test
./.venv/bin/python test/test_wifi_setup_wiring.py
```

- [ ] **Step 3: Implement phase ownership and task notification**

```c
typedef enum {
  TG_WIFI_PHASE_IDLE = 0,
  TG_WIFI_PHASE_STARTING,
  TG_WIFI_PHASE_OPEN,
  TG_WIFI_PHASE_JOINING,
  TG_WIFI_PHASE_JOINED,
  TG_WIFI_PHASE_FAILED,
} tg_wifi_setup_phase;
```

Use an atomic phase. Store the guard task handle. `torget_wifi_setup_request_open()` moves IDLE/FAILED to STARTING and calls `xTaskNotifyGive`; the guard waits with `ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(500))`, renders STARTING, then performs slow setup. Consume every KEY3 action while starting; retain release-to-close after OPEN/JOINING/JOINED/FAILED.

- [ ] **Step 4: Run GREEN and commit**

```bash
git add components/torget_wifi/wifi_slots.h \
  components/torget_wifi/wifi_slots.c \
  components/torget_wifi/wifi_setup.h \
  components/torget_wifi/wifi_setup.c \
  components/torget_wifi/wifi_setup_ui.h main/main.c \
  test/test_wifi_slots.c test/test_wifi_setup_wiring.py
git commit -m "fix: make WiFi setup entry deterministic"
```

## Task 4: Trial credentials before remembering and support retry

**Files:**
- Modify: `components/torget_wifi/wifi_setup.[ch]`
- Modify: `components/torget_wifi/wifi_slots.[ch]`
- Modify: `main/main.c`
- Modify: `test/test_wifi_slots.c`, `test/test_wifi_setup_wiring.py`

- [ ] **Step 1: Write RED trial/retry tests**

```c
check("new submission applies once", tg_wifi_join_should_apply(4, 3));
check("same submission deduplicated", !tg_wifi_join_should_apply(4, 4));
check("later retry applies", tg_wifi_join_should_apply(5, 4));
check("wrong password retryable",
      tg_wifi_disconnect_status(204) == TG_WIFI_JOIN_RETRY_PASSWORD);
check("network missing explains 2.4 GHz",
      tg_wifi_disconnect_status(201) == TG_WIFI_JOIN_RETRY_NOT_FOUND);
```

The wiring test proves `tg_wifi_creds_remember` occurs after `have_ip`, never in `join_post`, and a second POST receives a new sequence.

- [ ] **Step 2: Run RED**

Run the slot and wiring commands. Expected: existing code stores credentials before connection and has only a one-shot boolean.

- [ ] **Step 3: Implement synchronized pending trials**

Extend hooks:

```c
bool (*try_credentials)(const char *ssid, const char *password);
void (*credentials_accepted)(const char *ssid);
int (*last_disconnect_reason)(void);
```

Use one setup mutex. POST validates and copies credentials under the mutex, increments an atomic nonzero sequence, and returns joining. The guard applies each sequence once. `main.c` applies a bounded `wifi_config_t` and stores disconnect reason atomically. Only after GOT_IP:

```c
if (tg_wifi_creds_remember(trial.ssid, trial.password))
    s_hooks->credentials_accepted(trial.ssid);
```

Failed/abandoned trials never enter NVS.

- [ ] **Step 4: Add `/status` and retryable phone HTML**

Return one bounded response with no SSID/password:

```json
{"state":"connecting"}
{"state":"connected"}
{"state":"retry","reason":"password"}
{"state":"retry","reason":"not-found"}
{"state":"retry","reason":"connection"}
```

The joining page polls every 750 ms, shows truthful success/retry, and never claims “remembered” before GOT_IP. The form labels the password, says 2.4 GHz only, and disables duplicate submission.

- [ ] **Step 5: Run GREEN and commit**

```bash
./.venv/bin/python test/test_wifi_setup_wiring.py
git add components/torget_wifi/wifi_setup.h \
  components/torget_wifi/wifi_setup.c \
  components/torget_wifi/wifi_slots.h \
  components/torget_wifi/wifi_slots.c main/main.c \
  test/test_wifi_slots.c test/test_wifi_setup_wiring.py
git commit -m "fix: remember WiFi only after a successful join"
```

## Task 5: Build the real 480 x 480 QR screen

**Files:**
- Create: `design/vibepulse/wifi-onboarding-design.json`
- Create: `test/test_wifi_onboarding_design.py`
- Modify: `components/torget_wifi/wifi_setup_ui.[ch]`
- Modify: `sim/main.c`
- Modify: `test/test_vibepulse_visual_landmarks.py`
- Modify: `tools/preview-ui.sh`, `test/test_preview_ui.py`

- [ ] **Step 1: Start Studio and save exact tokens**

```bash
./.venv/bin/python tools/vibepulse_studio/server.py
```

Start at 1:1 with:

```json
{
  "schemaVersion": 1,
  "deviceCapability": "display.amoled",
  "canvas": {"width": 480, "height": 480},
  "wifi": {"x": 418, "y": 38, "size": 28},
  "open": {
    "wordY": 24,
    "instructionY": 82,
    "qrX": 142,
    "qrY": 108,
    "qrSize": 196,
    "ssidY": 316,
    "passwordY": 350,
    "addressY": 404,
    "footerY": 442
  }
}
```

Adjust JSON and C constants together if actual Plex ink overlaps. Validator rejects non-480 canvas, QR below 180, missing quiet-zone room, off-screen content, text below 14 px, or token/source drift.

- [ ] **Step 2: Write RED named-state captures**

Require:
- `torget-wifi-starting.bmp`
- `torget-wifi-setup-qr.bmp`
- `torget-wifi-setup-manual.bmp`
- `torget-wifi-joining.bmp`
- `torget-wifi-joined.bmp`
- `torget-wifi-failed-password.bmp`

The QR test independently asserts the white 196 x 196 canvas, black finder landmarks, quiet zone, no text overlap, and visible SSID/password/address. Manual fallback has no QR block and keeps all values.

- [ ] **Step 3: Run RED**

```bash
./.venv/bin/python test/test_wifi_onboarding_design.py -v
./.venv/bin/python test/test_vibepulse_visual_landmarks.py \
  VibePulseVisualLandmarkTests.test_wifi_onboarding_states -v
```

- [ ] **Step 4: Implement one reusable QR object**

Create one `lv_qrcode` in `torget_wifi_ui_create`, set quiet zone and accepted size once, and hide outside OPEN. Cache the payload and update only when changed:

```c
char payload[TG_WIFI_QR_PAYLOAD_CAP];
bool have_payload = tg_wifi_qr_payload(payload, sizeof payload,
                                       primary, secondary);
lv_result_t result = have_payload
    ? lv_qrcode_update(ui.qr, payload, strlen(payload))
    : LV_RESULT_INVALID;
ui.qr_available = result == LV_RESULT_OK;
```

On failure, show manual-only setup. Never create/destroy the canvas on guard ticks.

- [ ] **Step 5: Run GREEN, inspect 1:1, and commit**

```bash
cmake --build sim/build -j4
tools/preview-ui.sh vibepulse
git add design/vibepulse/wifi-onboarding-design.json \
  components/torget_wifi/wifi_setup_ui.h \
  components/torget_wifi/wifi_setup_ui.c sim/main.c \
  test/test_wifi_onboarding_design.py \
  test/test_vibepulse_visual_landmarks.py \
  tools/preview-ui.sh test/test_preview_ui.py
git commit -m "feat: show phone-first WiFi QR onboarding"
```

## Task 6: Promote Wi-Fi status to one global neutral indicator

**Files:**
- Modify: `platform/torget.h`, `platform/torget_ui.c`
- Modify: `components/app_tokens/agent_monitor.c`
- Modify: `components/torget_wifi/wifi_setup_ui.c`
- Modify: `components/torget_ota/ota_ui.c`
- Modify: `sim/main.c`
- Modify: `test/test_lvgl_layer_safety.py`, `test/test_vibepulse_visual_landmarks.py`

- [ ] **Step 1: Write RED structure and raster tests**

Require exactly one shared 28 x 28 group at `(418,38)`, no `wifi_group` in Needs You, no provider accent in the painter, and 0/1/2/3-bar captures for launcher, Claude, Codex, value, GitHub, Needs You, and a companion app when present.

Assert every arc remains visible; active inner strength is bright; disconnected retains full faint silhouette plus slash; no title/value enters the icon box or 8 px gutter.

- [ ] **Step 2: Run RED**

```bash
./.venv/bin/python test/test_lvgl_layer_safety.py
./.venv/bin/python test/test_vibepulse_visual_landmarks.py \
  VibePulseVisualLandmarkTests.test_global_wifi_status_matrix -v
```

- [ ] **Step 3: Build the shared status object**

```c
typedef enum {
  TG_WIFI_STATUS_NORMAL = 0,
  TG_WIFI_STATUS_SETUP,
  TG_WIFI_STATUS_HIDDEN,
} tg_wifi_status_mode;

void torget_wifi_status_set_mode(tg_wifi_status_mode mode);
void torget_wifi_status_foreground(void);
```

Create one top-layer group with three arcs, dot, and slash. A small LVGL timer compares `(mode,bars)` with the rendered key and mutates only on change. Inactive arcs stay visible in muted low opacity; active arcs are neutral white; slash appears only at normal zero bars; setup shows the complete symbol.

Remove Needs You’s Wi-Fi objects and key field. Setup/OTA move their overlay first, then foreground the single icon under the existing UI lock.

- [ ] **Step 4: Run GREEN and commit**

```bash
git add platform/torget.h platform/torget_ui.c \
  components/app_tokens/agent_monitor.c \
  components/torget_wifi/wifi_setup_ui.c components/torget_ota/ota_ui.c \
  sim/main.c test/test_lvgl_layer_safety.py \
  test/test_vibepulse_visual_landmarks.py
git commit -m "feat: show global WiFi signal status"
```

## Task 7: Prove and remove redundant Needs You redraws

**Files:**
- Modify: `components/app_tokens/agent_monitor.[ch]`
- Modify: `main/main.c`, `sim/main.c`
- Modify: `test/test_vibepulse_visual_landmarks.py`, `test/test_lvgl_layer_safety.py`
- Modify: `docs/lessons.md`

- [ ] **Step 1: Add content-free diagnostics**

Hypothesis: `ring_permille` in `needs_you_key` makes every 10 Hz countdown tick repeat group hiding, provider styles, label assignment, and foreground movement.

```c
typedef struct {
  uint32_t full_repaints;
  uint32_t ring_updates;
  uint32_t unchanged_ticks;
} tk_agent_render_stats;

void tk_agent_monitor_render_stats(tk_agent_render_stats *out);
```

Add simulator mode `--vibepulse-needs-you-render-qa` that applies one pending item, advances twenty 100 ms ticks, and prints only counters.

- [ ] **Step 2: Capture diagnostic RED evidence**

```bash
./sim/build/torget-sim --vibepulse-needs-you-render-qa
```

Expected before fix: full repaint count grows with ring ticks. If not, stop and return to lock instrumentation.

- [ ] **Step 3: Write failing counter test**

```python
self.assertEqual(stats["full_repaints"], 1)
self.assertGreaterEqual(stats["ring_updates"], 2)
self.assertGreater(stats["unchanged_ticks"], 0)
```

- [ ] **Step 4: Split stable paint from ring-only update**

Remove `ring_permille` from the stable key. On stable match, update only the visible ring when its value changes; do not hide/show groups, restyle providers, set labels, or foreground the root. Log/reset counters in the existing 10-second target heap diagnostic without content or IDs.

- [ ] **Step 5: Run GREEN and commit**

```bash
git add components/app_tokens/agent_monitor.h \
  components/app_tokens/agent_monitor.c main/main.c sim/main.c \
  test/test_vibepulse_visual_landmarks.py test/test_lvgl_layer_safety.py \
  docs/lessons.md
git commit -m "fix: avoid full Needs You redraws on ring ticks"
```

## Task 8: Full verification, physical gate, and release

**Files:**
- Modify: `README.md`, `docs/wifi.md`
- Modify: `docs/img/vibepulse-wifi-*.png`
- Modify: `tools/preview-ui.sh`, `test/test_preview_ui.py`

- [ ] **Step 1: Update docs and real images**

Document phone scan, manual fallback, expected local `Not Secure` label, 2.4 GHz, retries, immutable fallback, NVS exposure, and what the icon does/does not mean. Use real 480 x 480 renderer captures or physical photos with fake credentials.

- [ ] **Step 2: Run host and simulator gates**

```bash
PYTHON_BIN="$PWD/.venv/bin/python" ./test/run.sh
cmake -S sim -B sim/build -G Ninja
cmake --build sim/build -j4
tools/preview-ui.sh vibepulse
```

Inspect every new frame at 1:1.

- [ ] **Step 3: Measure memory**

Record before/create/update/close LVGL pool free/largest, internal free/low-water, largest DMA, QR canvas, and peak encode delta. Acceptance: effective pool at least 256 KiB; no assert/spin; DMA at least 31,232 bytes before admission and at least two flush blocks after APSTA/portal. QR failure shows manual fallback.

- [ ] **Step 4: Build target**

```bash
idf.py reconfigure
idf.py build
```

No generated `sdkconfig`, secrets, dependency-lock drift, debug probe, or simulator BMP may be staged.

- [ ] **Step 5: Stop for fresh flash authorization**

Report candidate SHA, target build, image offset `0x520000`, and intended `ota_1` operation. Never touch `ota_0`.

- [ ] **Step 6: Run supervised physical matrix on `ota_1`**

1. Prove candidate version.
2. Verify recognizable Wi-Fi states.
3. Double hold KEY3; STARTING appears without app switching.
4. Scan QR and join `VibePulse-setup`.
5. Join home 2.4 GHz and phone hotspot.
6. Enter wrong password, see retry, then correct it.
7. Reboot and prove remembered networks plus compiled fallback.
8. Exercise rotation, data arrival, setup, long Claude/Codex Needs You, pending replacement, and OTA takeover.
9. Repeat twenty transitions under TLS stress while recording redraw, flush, memory, DMA, and lock errors.

Acceptance: no wedge, WDT, sustained lock-failure flood, dead KEY3 state, false success, credential log, or stale data after recovery.

- [ ] **Step 7: Final docs commit, review, PR, CI, merge, draft release**

```bash
git add README.md docs/wifi.md docs/img/vibepulse-wifi-*.png \
  tools/preview-ui.sh test/test_preview_ui.py
git commit -m "docs: explain phone-first WiFi setup"
```

Run `git diff --check`, perform spec and quality review, push branch, update PR, merge only with green CI, and update the existing unpublished release draft with plain-English notes and real QR/status/Claude/Codex images.

## Final acceptance checklist

- [ ] QR scan joins temporary setup AP.
- [ ] Manual setup remains available.
- [ ] Wrong credentials are not remembered and can be retried.
- [ ] KEY3 cannot switch apps during STARTING.
- [ ] One recognizable neutral Wi-Fi icon appears across normal screens.
- [ ] The icon means association/RSSI only.
- [ ] Duplicate internal `AskUserQuestion` never appears.
- [ ] QR support is guarded in target and simulator.
- [ ] 256 KiB LVGL pool and DMA floors remain healthy.
- [ ] Ring ticks do not repaint the full Needs You tree.
- [ ] New 480 x 480 captures are inspected at 1:1.
- [ ] Host, simulator, target, physical `ota_1`, PR CI, and draft release pass.
- [ ] `ota_0` remains untouched.
