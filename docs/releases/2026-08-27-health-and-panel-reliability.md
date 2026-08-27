<!-- GitHub-ready v0.7.1 release body. Intentionally starts without an H1. -->

VibePulse v0.7.1 is a reliability patch for the path that must never merely
*look* healthy. It warns before the Claude credential readable by VibePulse
expires, proves whether the physical panel is actually polling, fixes missing
project-name glyphs, and records one exact end-to-end Codex panel test.

## What changed

- **Claude credential expiry is visible before Fable goes stale.** Claude can
  remain signed in and working while the separate Keychain credential an
  out-of-process quota reader is allowed to use has stopped refreshing. The
  tokenserver now publishes only a content-free readiness state and whole
  minutes remaining, warns 30 minutes before expiry, and rechecks local
  recovery every 15 seconds. It never returns or logs an access token, refresh
  token, account id, or Keychain body.
- **Startup health distinguishes service from panel.** Two close, non-loopback
  panel polls are required before diagnostics report recent panel contact; one
  curl cannot create a false green. The candidate address stays in process
  memory and is neither returned nor logged. Old evidence expires instead of
  remaining green forever.
- **The Codex smoke test is now deterministic.** The documented payload is
  `Ser du APPROVE?`, with `Ja` as the one explicit recommendation and `Nej` as
  the computer-side alternative. A pass requires visible **APPROVE**, a real
  panel tap, and `status: answered`, `option_index: 0`, `answer: Ja` back in
  Codex. Timeout, silence, **LEAVE IT**, private fallback, and computer
  fallback are not passes.
- **Project names render with the right glyph set.** The Needs You attract
  label used an uppercase-only font even though real project names contain
  lowercase letters, digits, dots, dashes, underscores, and replacement
  question marks. It now uses the existing full-ASCII `plex_ui_21` font.
- **Host startup no longer waits for relay history scans.** The first relay
  producer pass runs immediately but asynchronously, so a large local history
  cannot delay the LAN service binding at login.
- **The Codex plugin advances to 0.1.1.** Its skill includes the canonical
  physical test, strict pass criteria, and the build-versus-OTA version check.

## Upgrade

Pull or check out the eventual `v0.7.1` tag, then restart the tokenserver so
the new root diagnostics and startup behavior are active:

```sh
python3 tools/vibepulse_setup.py status
python3 tools/vibepulse_setup.py doctor
python3 tools/tokenserver/smoke.py
```

Existing Codex users should rerun the transactional guided setup to refresh
`vibepulse@torget`, choosing the same provider/detail options they want to
keep, then restart Codex, review VibePulse in `/hooks` if Codex asks again,
and start a new Codex task:

```sh
python3 tools/vibepulse_setup.py install
```

The release does not silently enable Claude, Codex, detail sharing, either
relay, or any other setting.

The host-side credential/startup fixes do not require a firmware flash. The
project-name glyph fix does. Use the normal consent-gated OTA flow only after
the release tag has green CI and the built image version matches the intended
checkout. Then run the canonical physical smoke test in
[`docs/agent-setup.md`](../agent-setup.md#post-flash-physical-codex-smoke-test).

VibePulse deliberately does not call an undocumented refresh endpoint or
mutate Claude's refresh token. When the readable credential is expiring or
expired, start a new Claude Code CLI turn and send one short message; the
supported client refreshes its own credential and VibePulse notices locally.

## Verified

- The full host gate passed: 778 Python/C tests, the numbers-relay suites,
  29 encrypted interaction-relay tests, and TypeScript type checking.
- The physical panel passed localized `RÄKSMÖRGÅS` rendering and the complete
  Codex question/touch/answer round trip on `torget-home-01` using the
  pre-tag build `v0.7.0-5-ge6feb29-dirty`. The exact evidence and recovery
  table are in the
  [2026-08-27 physical review](../superpowers/reviews/2026-08-27-vibepulse-codex-physical-end-to-end.md).
- A clean `v0.7.1` tag still requires its own green CI before publication.
  This physical evidence does not authorize an unattended flash.

This release remains source-only. Do not attach `torget.bin`: a locally built
image contains the installer's Wi-Fi credentials and device key.
