# Contributing to VibePulse

Thanks for helping. Keep changes small, evidence-backed, and honest about which
layer was tested: Python host, simulator, firmware build, real host, or physical
panel.

## Before changing code

- Read [docs/agent-setup.md](docs/agent-setup.md) for a fresh setup and
  [AGENTS.md](AGENTS.md) for maintainer constraints.
- Read [docs/lessons.md](docs/lessons.md) before touching pollers, parsers,
  staleness, persistence, or service-manager setup.
- Read [docs/platform-support.md](docs/platform-support.md) before changing a
  platform claim.
- Never commit `secrets.h`, credentials, device/OTA/relay keys, session
  content, or production payloads.
- Never flash a user's device without their explicit permission.

## Verification

The complete local host gate is:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt \
  -r requirements-interaction-relay.txt
./test/run.sh
```

CI also builds the ESP32-S3 firmware and runs the tokenserver suite on Ubuntu,
macOS, and Windows. A green platform runner is automated portability evidence,
not by itself a real-host or physical-panel validation.

For Windows changes, follow
[docs/windows-validation.md](docs/windows-validation.md). Linux remains
unsupported until [issue #2](https://github.com/niclasvestlund-YT/vibepulse/issues/2)
and every gate in the platform matrix are complete.

UI changes must use the exact 480×480 simulator captures and the AMOLED review
workflow described in `AGENTS.md`. Simulator approval never authorizes a flash.

## Pull requests

Explain the user-visible outcome, the root cause, the exact commands/tests that
passed, and anything not tested. Link real-host or physical evidence when the
change affects a public support claim. Keep release artifacts free of
`torget.bin`: it contains local Wi-Fi and device material.
