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
Do not run install, disable, or uninstall without the user's explicit request.
