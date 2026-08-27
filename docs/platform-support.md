# Host platform support

VibePulse has two different platform surfaces:

1. the ESP32-S3 firmware, which runs on the one supported Waveshare panel;
2. the tokenserver, setup tools, and optional Codex bridge running on your
   computer.

When this document says a computer platform is supported, it means the
**host service**. It does not claim that every developer builds or flashes the
firmware from that operating system.

## Current support

| Host | Tokenserver | Autostart | Automated evidence | Real-host evidence | Public status |
|---|---|---|---|---|---|
| macOS | Yes | launchd | Tokenserver matrix + full host gate | Daily development and physical panel reviews | Supported |
| Windows | Yes | Task Scheduler | Tokenserver matrix on `windows-latest`; installer/runner parser and `-ValidateOnly` gate | Windows host validation is required for each public support milestone | Supported; the new persistent-log path remains tracked in [#28](https://github.com/niclasvestlund-YT/vibepulse/issues/28) until it passes a real scheduled-task lifecycle |
| Linux | Not on `main` | Not shipped | The Python suite runs on Ubuntu, but that alone does not exercise a supported Linux installation | No current-main release report | Not supported yet; tracked in [#2](https://github.com/niclasvestlund-YT/vibepulse/issues/2) |

The v0.7.1 tokenserver matrix passed on Windows, macOS, and Ubuntu in the
[release commit's CI run](https://github.com/niclasvestlund-YT/vibepulse/actions/runs/33061186373).
That is strong portability evidence, but it is not a substitute for a real
service-manager, firewall, LAN, credential, and panel test.

A [read-only real-PC report for v0.7.1](superpowers/reviews/2026-08-27-windows-v0.7.1-read-only.md)
passed the complete Windows suite, all endpoint contracts, and the Claude
source. It remained PARTIAL because that PC had no scheduled task, the
app-owned Codex executable could not be invoked from the validation
environment, external LAN reachability was not tested, and the panel never
completed the physical loop.

## What “validated on Windows” means

A Windows claim is release-ready only when all of these are recorded against
an exact clean tag or commit:

- the complete tokenserver suite passes on the PC with Python 3.11 or newer;
- the Task Scheduler installer parses and its non-mutating validation mode
  resolves the expected checkout and interpreter;
- the real service serves safe health plus all three panel endpoints;
- the real Codex source is current, and Claude is either current or reports an
  honest, actionable unavailable/expired state;
- inbound TCP 8737 is allowed on **Private** networks only and another LAN
  device can reach it;
- Task Scheduler starts the service after sign-in and recovers after a forced
  process failure;
- the physical panel reports recent polling, receives the canonical short
  Codex question, visibly renders **APPROVE**, and a human tap returns the
  expected answer;
- sleep/resume and one reboot do not leave the panel silently stale.

Use [Windows release validation](windows-validation.md) for the reproducible
procedure. Silence, a missing panel, **LEAVE IT**, computer fallback, or
**SOMETHING IS WAITING** without answer buttons is never a pass.

## What remains before Linux can be announced

Green Ubuntu unit tests do not make the current release a Linux product. On
current `main`, Linux still falls into macOS-shaped state/log paths, the Claude
credential-file source is not selected, and no systemd user-service installer
ships. Linux needs all of the following before the README or GitHub description
may call it supported:

- XDG-compatible state and log paths;
- Claude credential-file lookup, including `CLAUDE_CONFIG_DIR`, without
  macOS-only commands;
- reliable Codex executable discovery under systemd's reduced `PATH`;
- an idempotent systemd **user** service install/validate/uninstall flow;
- safe firewall and host-address instructions;
- automated service-definition validation in CI;
- the complete host suite on Ubuntu;
- a real Linux host report covering Codex, Claude, autostart, LAN reachability,
  restart/reboot, and the physical panel loop.

The older combined Windows/Linux work in
[PR #13](https://github.com/niclasvestlund-YT/vibepulse/pull/13) is useful
reference material, not merge-ready code: Windows landed independently and the
pull request now conflicts with `main`. Extract and re-test the Linux-specific
parts rather than merging the stale branch wholesale.

## Claim discipline

- **Automated:** a CI runner executed the code. This proves repeatability, not
  a household LAN, real credentials, Task Scheduler/systemd, or the panel.
- **Real-host:** the released code ran on the named operating system with real
  local sources. This still does not prove the physical interaction loop.
- **Physical end to end:** computer source → tokenserver → LAN/relay → panel →
  human touch → originating agent all completed with explicit evidence.

Release notes and social posts should use the narrowest true claim. In
particular, never turn “Ubuntu tests are green” into “Linux is supported.”
