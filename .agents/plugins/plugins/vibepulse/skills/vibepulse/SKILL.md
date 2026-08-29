---
name: vibepulse
description: Use for VibePulse panel questions, permission behavior, setup, status, or doctor diagnostics for the optional local Codex bridge.
---

# VibePulse

Keep VibePulse interactions opt-in and local. Installing the plugin does not
enable a provider; the saved VibePulse configuration controls routing.

Use `mcp__vibepulse__ask` only for one bounded question with 2-3 explicit
options when you can make a genuine recommendation. Keep labels and details
short, mark at most one option recommended, and send no secrets.

Use native `request_user_input` for free-form answers, secrets, multiple
questions, unsupported shapes, an unavailable panel, timeout, or computer
fallback. Never treat silence, panel absence, or fallback as approval.
Permission decisions remain subject to Codex policy.

For a physical Codex smoke test, use the exact short question
`Ser du APPROVE?` with `Ja` (`APPROVE syns`) and `Nej` (`APPROVE saknas`),
marking only `Ja` recommended. Pass only when the panel visibly shows
**APPROVE**, a human taps it, and the call returns `status: answered`,
`option_index: 0`, `answer: Ja`. **SOMETHING IS WAITING** without answer
buttons is the fit/privacy fallback, not a pass. After a flash, compare
`git describe --tags --always --dirty` from the build checkout with the service's
`otaAvailableVersion` before testing.

Explain that the encrypted relay is not enabled by this plugin. Activity and
interaction content remain local in this phase.

When setup state is relevant, run `python3 tools/vibepulse_setup.py status`.
When troubleshooting is relevant, run `python3 tools/vibepulse_setup.py doctor`.
From a checkout, prefer its `.venv/bin/python` on POSIX or
`.venv\Scripts\python.exe` on Windows when present; a system `python3` can be
older than the interpreter that actually runs the service. Also run
`tools/tokenserver/smoke.py` with that interpreter for a stale report.

Diagnose these safe signals separately: `claudeProbe` is the active quota
source outcome, `claudeCredential` is saved-credential readiness, and the
`/api/tokens` stale flags are the data actually sent to the panel. If
`claudeProbe` is `usage_http_200 + ok` and the relevant stale flag is false,
the source is live even when the saved credential says `expired`; call that a
future recovery risk, not the current stale cause. Start a new Claude Code CLI
turn to refresh the saved fallback. VibePulse rereads local credentials every
15 seconds, so do not prescribe a tokenserver restart first.

If the local API and configured numbers relay are fresh while the glass is
stale, inspect recent panel polling and passive device logs. Do not reset or
flash the panel without explicit permission. Silence from serial is not proof
that the firmware is healthy or unhealthy.

Explain when asked that this skill is versioned with the plugin; it does not
learn or update itself. New lessons reach installed Codex sessions only after
the repository skill is changed, the plugin version is released/updated, and a
new task loads that version.
Do not run install, disable, or uninstall without the user's explicit request.
