# Changelog

## Unreleased

### Added

- **The phone panel.** An Android app that shows Claude Code quota, burn rate,
  Max Tracker, GitHub and value on an ordinary phone, with live agent rows and a
  full-screen notice when an agent is waiting on you. Read only: four GETs, no
  key, no signing, no POST.
- **Two transports.** USB via `adb reverse`, which keeps the link off every
  network entirely, and Bluetooth RFCOMM through `tools/btbridge/bt_bridge.py`
  for cable-free use. The bridge forwards GETs only, so neither answer routes
  nor the loopback-only hook routes are reachable through it.
- **Service installer** (`tools/btbridge/install-phone-panel-tasks.ps1`) so the
  tokenserver and bridge survive a reboot.

### Changed

- Forked from [VibePulse](https://github.com/niclasvestlund-YT/vibepulse) and
  reduced to the phone dashboard: the ESP32-S3 firmware, LVGL components,
  simulator, hardware specs, OTA and WiFi-provisioning tooling, and the cloud
  relays are all removed. The tokenserver is kept essentially unchanged.
- Claude Code only; every Codex surface removed.

### Fixed

- The Bluetooth bridge now waits for its configured RFCOMM channel instead of
  falling back immediately. A restart raced the dying previous process, landed
  on a different channel, and silently broke the phone's saved configuration.
