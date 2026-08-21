# VibePulse Wi-Fi Onboarding and Status Design

**Date:** 2026-08-21

**Status:** Proposed for final review

**Scope:** ESP32-S3 panel Wi-Fi onboarding, global Wi-Fi status, Claude question-hook deduplication, and render-health verification

## Plain-English outcome

Adding a Wi-Fi network should feel like setting up a small consumer device:

1. The user starts Wi-Fi setup with the existing KEY3 gesture.
2. The panel responds immediately instead of appearing stuck.
3. The panel shows a real QR code plus a manual fallback.
4. Scanning the QR joins the phone to the temporary `VibePulse-setup` network.
5. The phone opens a simple local page where the user chooses home Wi-Fi, a phone hotspot, or another 2.4 GHz network and enters its password.
6. The panel joins that network, remembers it, and returns to the normal dashboard.

A recognizable Wi-Fi symbol then remains in the top-right corner of normal panel screens. The symbol reports the panel's Wi-Fi connection and signal strength only. It does not claim that the internet, tokenserver, Mac, Cloudflare relay, Claude, or Codex is reachable.

This is a local, router-independent setup flow. It does not require an account, Bluetooth, a destination-network password in the QR code, or changes to the user's router.

## Goals

- Make first-time setup and adding another Wi-Fi simple enough to complete with a phone.
- Give immediate, deterministic feedback after the KEY3 gesture.
- Keep a manual setup path for phones that do not open captive portals automatically.
- Show clear Wi-Fi state on all normal app pages without covering app content.
- Prevent Claude's internal `AskUserQuestion` permission event from appearing as a second, broken approval screen.
- Preserve the existing truthful approval rule: altered, truncated, missing-glyph, or physically overbound content is not remotely approvable.
- Prove that QR rendering and Wi-Fi/status redraws do not recreate an LVGL lock wedge.
- Preserve the untouched `ota_0` v0.5.0 rollback image.

## Non-goals

- Bluetooth provisioning.
- 5 GHz Wi-Fi support; the ESP32-S3 panel uses 2.4 GHz Wi-Fi.
- Automatically changing router settings or bypassing client isolation.
- Cloud storage or synchronization of Wi-Fi passwords.
- Putting the destination Wi-Fi password in the QR code.
- A touch keyboard on the panel.
- Treating Wi-Fi association as proof that the internet or tokenserver works.
- Changing the independent, default-off Claude/Codex interaction switches.

## Hardware posture

The selected path uses hardware that is already present and verified:

- The ESP32-S3 Wi-Fi radio is silicon-capable, board-wired, enabled by the firmware, and physically verified on the target panel.
- The 480 x 480 CO5300 display is board-wired, enabled, and physically verified.
- KEY3 is active-low on GPIO18 and has been exercised on the physical panel.
- No external hardware is required.

BLE is silicon-capable and board-wired, but it is disabled and not physically verified for this product flow. SoftAP onboarding is preferred because it is already enabled, physically proven, works with an ordinary phone camera, and avoids Bluetooth coexistence, memory, permission, and privacy complexity.

## Entry and gesture behavior

The existing KEY3 double-hold gesture remains the explicit way to request Wi-Fi setup.

The current request is asynchronous and can take roughly four seconds while OTA ownership is released, networks are scanned, and the portal starts. The new behavior must make that delay visible:

- The first accepted request immediately displays `STARTING WI-FI SETUP`.
- Further KEY3 presses are consumed while setup is starting. They must not switch apps, dismiss another overlay, or cancel the request accidentally.
- Setup becomes dismissible only after it reaches the open portal state or a clear failure state.
- The existing OTA overlay retains ownership when an OTA operation is actually active. Wi-Fi setup must not steal port 80 or the top layer from an active update.
- If setup cannot start, the screen explains that normal saved-network retry continues and offers a safe retry/exit path. It must never leave the device with dead input.

## Panel onboarding states

The setup UI remains one bounded top-layer tree with explicit states:

### 1. Starting

- `WIFI SETUP`
- `STARTING...`
- Short explanation: the panel is preparing a private temporary connection for the phone.
- No QR is shown until the SoftAP password and portal are actually ready.

### 2. Scan QR

- A large, native black-on-white QR code with a complete quiet zone.
- Primary instruction: `SCAN WITH YOUR PHONE`.
- Secondary instruction: choose this panel's setup network, then follow the phone's Wi-Fi prompt.
- Compact manual fallback remains visible:
  - network: `VibePulse-setup`
  - the current 12-character temporary password
  - address: `192.168.4.1`
- `tools/wifi-here.sh` may remain in developer documentation, but it is not the primary consumer instruction.

The QR payload uses the standard Wi-Fi QR form:

```text
WIFI:T:WPA;S:VibePulse-setup;P:<temporary-panel-password>;H:false;;
```

The SSID and password are escaped according to the Wi-Fi QR grammar before encoding. The QR contains only the temporary setup-network credential. It never contains the password for the selected home, hotspot, or cafe network.

### 3. Joining

- `CONNECTING TO`
- The selected SSID, safely bounded for display.
- A clear wait state.
- Repeated form submission is disabled or deduplicated.
- KEY3 cannot accidentally switch apps while the join result is pending.

### 4. Joined

- `ON THE NET`
- The joined SSID.
- A success symbol and a short message that the network was remembered.
- The setup overlay closes after the panel has a valid IP address and the success state has been visible long enough to understand.

### 5. Failed

- An honest reason when one is available, such as wrong password, network unavailable, unsupported 5 GHz-only network, or setup memory unavailable.
- The portal stays available when retry is possible.
- The user can choose another network or correct the password without restarting the whole panel.
- Existing compiled fallback networks remain immutable and available; onboarding credentials extend the remembered network set instead of replacing the fallback floor.

## Phone portal behavior

The portal remains local at `192.168.4.1` over HTTP. A phone may label this page `Not Secure`; that is expected for a short-lived local setup network and must be explained in the user documentation.

The phone flow is:

1. Scan the QR with the phone camera.
2. Accept joining `VibePulse-setup`.
3. Use the automatically opened captive portal, or browse to `192.168.4.1` if it does not open.
4. Pick one of the strongest discovered 2.4 GHz networks.
5. Enter its password, or leave the field empty for an open network.
6. Tap `Join` once.
7. See `Connecting`, then an honest success or retry result.

The page must not log, echo in diagnostics, or retain the destination password beyond the existing NVS credential path. The existing storage security posture is unchanged: credentials are stored locally in NVS, and flash encryption is not newly enabled by this feature.

A cafe captive portal can allow Wi-Fi association while still blocking internet or tokenserver access. The panel's Wi-Fi icon therefore reports association and RSSI only.

## Global Wi-Fi indicator

Wi-Fi status becomes a platform-level primitive rather than a Needs You-only decoration.

### Geometry and ownership

- One shared 28 x 28 object group occupies the reserved top-right lane at `(418, 38)` on normal 480 x 480 screens.
- Existing per-screen Wi-Fi copies are removed or routed through the shared primitive so two icons can never overlap.
- App metadata that currently reaches the top-right lane shifts left. The icon never covers a title, value, clock, or action.
- Full-screen setup and OTA states use the same connectivity state or an explicit setup/update variant under one visibility policy.
- The Wi-Fi event task never calls LVGL. It publishes a packed atomic state; the LVGL task applies a change only when that state differs from the last rendered state.

### Visual language

The current weak-signal state draws only a tiny inner arc and dot, which is easy to mistake for a stray mark. The replacement always draws the complete Wi-Fi silhouette faintly and highlights the active strength:

- **Three bars:** all arcs and dot are bright.
- **Two bars:** two inner arcs and dot are bright; the outer arc remains faint.
- **One bar:** the inner arc and dot are bright; the other arcs remain faint.
- **Disconnected:** the complete faint silhouette remains recognizable and gains a clear slash/disconnected mark.
- **Setup SoftAP:** the complete symbol uses a static setup variant. Animation is not required for this change.

The indicator uses a neutral connectivity palette, not Claude orange or Codex blue, because it represents the panel rather than an agent provider.

Signal updates retain the existing generation ordering protection: event-group association state is published before the packed icon state, stale sampler results cannot overwrite a newer event, and generation saturation cannot create an ABA wrap.

## Claude `AskUserQuestion` deduplication

The attached physical screen showing:

- `CLAUDE NEEDS YOU`
- chip `askuserquestion`
- title `AskUserQuestion`
- only `LEAVE IT`

is a real duplicate-hook defect, not intended UI.

Claude sends the real question to the dedicated `/api/hook/question` route. A catch-all `PermissionRequest` hook can later send the internal `AskUserQuestion` tool to `/api/hook/permission`, especially after the question hook times out or is answered on the computer.

The server contract becomes:

- The dedicated question hook exclusively owns `AskUserQuestion`.
- A generic Claude permission event whose normalized tool name is `AskUserQuestion` is ignored and never parked.
- The filter is enforced at the tokenserver/store boundary. Correctness must not depend on every open-source user's local regex or Claude settings.
- Ignoring the duplicate does not consume, replace, or resolve a real pending question.
- Other permission tools retain the existing safe-command classification and computer-fallback behavior.

The exact live sequence is a required regression: park a real question, receive a later generic permission for internal `AskUserQuestion`, and prove that no second pending approval appears.

## QR implementation and memory contract

Use LVGL 9.5's official QR widget and bundled `qrcodegen` library. Do not create one LVGL object per QR module and do not scale a static bitmap at runtime.

The widget uses:

- one persistent 1-bit indexed canvas for the displayed QR;
- a small palette and draw-buffer descriptor;
- two short-lived version-sized buffers while encoding;
- the existing LVGL allocator.

One QR object is created and reused by the Wi-Fi setup tree. It is updated only when the temporary setup credential changes. It must not be recreated every guard tick or repaint.

The target and simulator configurations both enable `LV_USE_QRCODE`. Configuration checks must fail at configure/build time if target or simulator support drifts. The error must explain how to regenerate an existing `sdkconfig`, because `sdkconfig.defaults` does not overwrite an already-generated `sdkconfig`.

Memory acceptance:

- The effective LVGL pool remains pinned to at least 256 KiB.
- The QR canvas and peak encode buffers are measured on the simulator and target; estimates are not accepted as proof.
- The QR allocation must not reduce the largest internal DMA block below the current setup-open floor of 31,232 bytes.
- Existing double 480 x 50 partial display buffers and flush behavior remain unchanged.
- QR creation/update failure produces an honest manual-only setup screen; it must not enter `LV_ASSERT_MALLOC` or hold the LVGL lock forever.

Exact QR size and final band coordinates are fixed in Studio and simulator before firmware acceptance. The intended range is approximately 192-196 pixels so a phone can scan it easily at arm's length while the manual fallback remains readable.

## Render and LVGL lock health

The current physical run showed repeated `Failed to acquire LVGL lock` messages during interaction redraws. Networking and value updates continued, so this was not the old permanent 96 KiB-pool malloc-assert wedge, but it is still a real render-health warning.

This work must investigate it rather than hide it by increasing lock timeouts.

Rules:

- Unchanged Wi-Fi state, setup state, and pending interaction state do not invalidate objects.
- QR data is encoded only when its payload changes.
- No periodic task performs a full-screen invalidate.
- No network/event task touches LVGL.
- Debug instrumentation measures LVGL lock hold time, repaint count, invalidated area, and state transitions without logging question text, commands, passwords, or secrets.
- The partial-buffer target path is exercised; a full-buffer single-threaded simulator result alone is insufficient.

Physical acceptance on `ota_1` includes:

1. normal data arrival;
2. rotation and restoration;
3. open and close Wi-Fi setup;
4. show and scan the QR;
5. join a different Wi-Fi or phone hotspot;
6. show long Claude and Codex Needs You states;
7. clear/replace a pending interaction;
8. exercise OTA takeover without flashing `ota_0`.

Acceptance requires no hard wedge, no WDT reset, no permanent lock-failure flood, correct touch/KEY3 behavior, and continued data refresh after every transition. Any occasional lock miss must be measured and bounded; the implementation cannot claim success while a sustained timeout sequence remains unexplained.

## Error and privacy behavior

- Destination Wi-Fi passwords appear only in the phone password field and existing local credential storage path.
- Logs, tests, screenshots, releases, and diagnostics use fake credentials.
- The setup AP password is temporary and may be seen by a person physically viewing/scanning the panel.
- QR generation failure falls back to SSID, temporary password, and `192.168.4.1`.
- Portal/DNS/HTTP start failure shows a clear failure state and releases resources cleanly.
- Wrong destination credentials keep the user in a retryable flow and never display `ON THE NET`.
- No interaction content is added to the existing numbers-only public relay by this feature.
- Claude and Codex host interaction support remains separately selectable and default-off.

## Open-source behavior

Wi-Fi onboarding and the global Wi-Fi icon are device-platform features and do not require Claude, Codex, GitHub, the Mac tokenserver, or the Cloudflare relay.

Users can continue to use only the panel apps they want. The existing independent host switches remain:

- numbers publishing;
- Claude interactions;
- Codex interactions;
- interaction detail;
- GitHub data.

Adding Wi-Fi does not opt the user into agent activity publishing. Disabling Claude or Codex interactions removes their approval path without disabling Wi-Fi setup or status.

## Verification contract

Implementation begins with failing regressions and is complete only when all applicable gates pass.

### Host and integration tests

- KEY3 setup transition and input-suppression policy.
- QR Wi-Fi payload escaping and credential binding.
- QR target/simulator build configuration parity.
- Portal form bounds, duplicate-submit handling, and honest success/failure states.
- Compiled fallback credentials remain preserved.
- Wi-Fi packed-state event/sampler ordering and terminal generation behavior.
- Generic Claude `AskUserQuestion` permission deduplication.
- Unchanged state produces no redundant render invalidation.
- QR allocation/update failure safely selects the manual fallback.

### Exact 480 x 480 simulator captures

- Starting setup.
- QR plus manual fallback.
- Joining.
- Joined.
- Retry/failure.
- Global Wi-Fi disconnected/one/two/three bars on every normal app family.
- Needs You question and approval with the global icon.
- OTA/setup ownership states.
- Long and missing-glyph content remains aligned, unclipped, and non-approvable when altered.

Every new capture is inspected at 1:1. Automated landmarks must bind to the named state rather than pass through unrelated pixels elsewhere in the image.

### Build and physical gates

- Full repository test runner.
- Simulator configure/build and exact preview manifest.
- ESP-IDF 5.5 target build with the real 256 KiB pool configuration.
- QR/LVGL/DMA memory measurements.
- USB-Serial/JTAG monitoring during the physical transition matrix.
- A fresh explicit user authorization before flashing the new candidate to `ota_1`.
- `ota_0` is never erased, flashed, selected for test mutation, or otherwise changed.

## Release-facing explanation

In plain English, the finished feature will be described as:

> Scan the QR on VibePulse, choose a 2.4 GHz Wi-Fi network on your phone, and the panel remembers it. A clear Wi-Fi symbol is visible across the panel so you can tell whether it is connected and how strong the signal is. Claude questions no longer turn into a second broken `AskUserQuestion` approval screen.

Release images must be real 480 x 480 renderer captures or physical-device photos, not design mockups. They must not contain real Wi-Fi passwords, interaction secrets, or private question content.
