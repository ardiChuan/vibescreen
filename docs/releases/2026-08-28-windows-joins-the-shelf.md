<!-- GitHub-ready v1.0.0 release body. Intentionally starts without an H1. -->

VibePulse v1.0.0 is the moment the shelf screen becomes a two-host product.
The core loop now runs on a real Windows PC as well as macOS: quota stays in
view, live Claude/Codex activity reaches the glass, and a supported Codex
question can travel from the computer to the physical panel and back through
an explicit human tap.

<p align="center">
  <img src="https://raw.githubusercontent.com/niclasvestlund-YT/vibepulse/v1.0.0/docs/img/vibepulse-codex-week.png" width="31%" alt="Codex weekly quota on VibePulse">
  &nbsp;
  <img src="https://raw.githubusercontent.com/niclasvestlund-YT/vibepulse/v1.0.0/docs/img/vibepulse-codex-needs-you.png" width="31%" alt="Codex Needs You alert on VibePulse">
  &nbsp;
  <img src="https://raw.githubusercontent.com/niclasvestlund-YT/vibepulse/v1.0.0/docs/img/vibepulse-needs-you-codex-question.png" width="31%" alt="Codex question with an explicit recommendation on VibePulse">
</p>

## Why 1.0

VibePulse began with one promise: put the state of your coding agents
somewhere you can see it without opening another window. The first major
release now exercises that whole promise on both supported host families:

- see the real Claude and Codex weekly windows without invented zeroes;
- see which agent is working, waiting, done, or stale;
- let the panel take the room with **NEEDS YOU** when the human is the blocker;
- tap into the decision, read the recommended choice, and explicitly answer;
- keep unsupported, ambiguous, oversized, private, or mutating work on the
  computer where it belongs.

The physical Windows proof ended with the exact canonical round trip:
`Ser du APPROVE?` → visible **NEEDS YOU** → visible **APPROVE** → human tap on
`Ja` → returned `answered / option_index 0 / Ja`. Silence, timeout, computer
fallback, and a buttonless private screen remain failures—not consent.

## Windows, for real

This is not a CI-only portability claim. On a real Windows host, exact clean
revision `bee5d8c9c9b47b761b5970c346cc0e641ac82485` passed:

- the complete 788-test tokenserver suite with 11 named skips and no failure;
- PowerShell parsing plus the non-mutating Task Scheduler `-ValidateOnly` gate;
- user-scoped Task Scheduler installation and immediate service start;
- exact-PID watchdog recovery back to the same revision;
- bounded live stdout/stderr logging with one bounded rotated tail;
- the standalone Codex CLI/app-server source and safe Claude source health;
- Codex plugin/MCP setup with the full bounded human-answer window;
- a Private-profile-only TCP 8737 rule and real non-loopback LAN reachability;
- recent physical panel polling throughout the parked interaction;
- the live payload through the same strict C parser shipped in the firmware;
- the physical human answer, with the service still running afterward.

The sanitized evidence is preserved in the
[Windows v1 core and physical report](https://github.com/niclasvestlund-YT/vibepulse/blob/v1.0.0/docs/superpowers/reviews/2026-08-28-windows-v1-core-physical.md).

One boundary stays named: sign-out/sign-in, sleep/resume, and a full reboot
were not performed in that pass. They remain the persistent lifecycle gate in
[#28](https://github.com/niclasvestlund-YT/vibepulse/issues/28). The truthful
v1 claim is **Windows core + physical answer loop verified**, not that three
unrun transitions somehow passed.

## One panel, Mac or Windows

The panel can now discover `_vibepulse._tcp.local` advertisements and stay
pinned to a healthy tokenserver. If that host fails for a bounded interval, it
can move to another advertising Mac or Windows PC and keep the compiled URL as
the fallback for multicast-hostile networks. The advertisement carries only
protocol version and port—never quota values, prompts, account identifiers,
credentials, or a relay address.

The mDNS dependency is locked in the ESP-IDF manifest so a clean firmware
build reproduces the discovery behavior that was tested on the panel.

## Windows hardening since v0.7.1

- Task Scheduler uses Windows-compatible instance policy and updates only its
  own task/process.
- The runner preserves exact arguments, captures stdout/stderr, rotates within
  hard bounds, and handles paths containing spaces and non-ASCII characters.
- Codex discovery prefers OpenAI's standalone per-user CLI and rejects
  `WindowsApps` aliases that fail in background contexts.
- The app-server startup probe has a real bounded Windows deadline instead of
  turning normal startup into stale quota.
- Current Codex plugin provenance is accepted without weakening ownership or
  path checks.
- The MCP tool timeout covers the complete 120-second panel-answer window, so
  Codex no longer abandons a healthy physical question early.
- Setup doctor checks the actual Python 3.11+ probe consistently on Windows.
- The public setup, recovery, and validation runbooks distinguish automated,
  real-host, physical, and persistent-lifecycle evidence.

## Privacy and failure behavior did not loosen

Local mode still requires no VibePulse account. Agent activity and interaction
detail stay on the LAN unless the separate encrypted relay is explicitly
enabled. Installing the Codex plugin enables no provider or cloud transport.
The numbers relay, interaction relay, live-status relay, GitHub page, Claude
bridge, Codex bridge, and detail sharing remain independent choices.

Panel answers are provider-bound, request-bound, view-digest-bound,
short-lived, and authenticated with the paired device key. The device never
receives an OAuth token, refresh token, account identifier, or full session.
Unknown tools and uncertain payloads fail closed to the computer.

## Upgrade

Check out the release, rerun the host setup for the operating system that will
serve the panel, then build/flash through the existing consent-gated path:

```sh
git fetch --tags origin
git switch --detach v1.0.0
python3 tools/vibepulse_setup.py status
```

Windows users should follow the
[Windows host runbook](https://github.com/niclasvestlund-YT/vibepulse/blob/v1.0.0/docs/windows-setup.md)
and run the shipped Task Scheduler installer from the release checkout. The
strict release procedure is in
[Windows validation](https://github.com/niclasvestlund-YT/vibepulse/blob/v1.0.0/docs/windows-validation.md).

This release remains source-only. **Do not attach `torget.bin`**: every local
firmware build contains that installation's Wi-Fi credentials and may contain
its private device key.

Full history:
[v0.7.1...v1.0.0](https://github.com/niclasvestlund-YT/vibepulse/compare/v0.7.1...v1.0.0).
