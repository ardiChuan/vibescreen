# VibePulse stale-recovery physical review — 2026-08-30

## Outcome

**REMEDIATION PARTIAL PASS; END-TO-END STILL FAIL.**
The physical unit `torget-home-01` now runs
`v1.0.0-24-ga16512a`, built from the stale-recovery branch for PR #58. The
previous `v1.0.0-18-g3a131a2` checkpoint was byte-identical to merged `main`
`f672a14` and contained the stale-glass diagnostic and runbook changes from
PR #57.

The firmware flash, initial wall-powered network recovery, local service
discovery, fresh Claude/Fable/Codex payloads, touch input, and one canonical
physical local-LAN APPROVE round trip passed. The user also confirmed that the literal
`STALE` label disappeared immediately after recovery. That was not durable:
after several minutes the panel became `STALE` again. At the failure
checkpoint the host and the ESP32-compatible numbers relay still served fresh
data, the ESP32 still answered ICMP, but direct application polling was more
than five minutes old and a new panel interaction timed out. The evidence
therefore proves a live network interface with stalled device-side HTTP work;
it does not prove a reliable stale recovery.

The new watchdog image was then written with NVS preserved and booted with the
expected version. Under bounded serial observation its quota fetch succeeded
repeatedly through approximately 6 minutes 19 seconds of uptime, including
successes after the old roughly 5-minute failure point, with stable internal
heap. That is a physical PASS for the candidate's computer-USB diagnostic
window, but not yet the dedicated-power acceptance gate. The immediate
canonical interaction still timed out. Simultaneous DNS-SD browsing found two
different VibePulse hosts on the LAN; the flashed image had the encrypted
interaction relay disabled, so a healthy first DNS-SD result could bind the
direct question path to the wrong computer. Numbers recovery and question
delivery are therefore recorded as two distinct issues.

No credential, account identifier, quota value, private address, relay route,
device key, or private URL is recorded here.

## Flash evidence

| Gate | Result | Sanitized evidence |
|---|---|---|
| Explicit authorization | PASS | The user explicitly said to flash the connected ESP32 |
| Target identity | PASS | The resolved USB target identified as ESP32-S3 with 8 MB embedded PSRAM and USB Serial/JTAG |
| Build identity | PASS | App descriptor and image strings reported `v1.0.0-18-g3a131a2`; discovery strings were present |
| Main-tree equivalence | PASS | The build commit tree and merged `main` tree had the same Git tree object |
| Safe write scope | PASS | Bootloader, partition table, OTA initial data, and app were written; NVS was not included |
| Image verification | PASS | Esptool verified the hash of every written image and exited successfully |
| Recovery behavior | PASS | Automatic reset could not enter the ROM loader; the documented BOOT + RESET sequence did, before any write occurred |
| Watchdog image flash | PASS | `v1.0.0-24-ga16512a` booted after a hash-verified write of bootloader, partition table, OTA initial data, and app; NVS remained outside the write ranges |

## Runtime evidence

| Gate | Result | Sanitized evidence |
|---|---|---|
| Computer-USB runtime | FAIL as operating mode | No direct panel poll appeared inside the bounded 90-second window |
| Dedicated-power startup | PASS | After moving to a dedicated 5 V supply, the panel completed a signed local-LAN interaction and later resumed direct LAN polling |
| Sustained dedicated-power runtime | **FAIL** | After several minutes the panel became stale again although the ESP32 still answered ICMP and both host and relay payloads remained fresh |
| Service discovery | PASS | Host discovery reported `ready` |
| Initial direct panel contact | PASS | Root health changed from `waiting` to `ready` after two confirmed panel polls |
| Sustained direct panel contact | **FAIL** | The last confirmed `/api/agent-status` poll aged past five minutes and was not renewed |
| Provider freshness | PASS | Claude weekly, Fable/model-week, and Codex weekly stale flags were all false |
| Physical APPROVE | PASS | Exact question `Ser du APPROVE?`; visible-state instruction required APPROVE; human tapped `Ja`; returned `answered`, option index 0, answer `Ja` |
| Initial literal `STALE` absence | PASS, transient | Computer fallback was discarded; the user then directly inspected the main view and confirmed that `STALE` was gone |
| Repeated physical interaction | **FAIL** | The follow-up panel request timed out; silence and computer fallback were not counted as approval |
| Sustained literal `STALE` absence | **FAIL** | The user later confirmed that `STALE` had returned |
| New watchdog diagnostic runtime | PASS, bounded | Quota HTTP completed repeatedly beyond the former failure point, through approximately 6 minutes 19 seconds, without a heap collapse |
| New watchdog dedicated-power runtime | **NOT TESTED** | The new image has not yet completed the same window on the dedicated 5 V supply |
| Multi-host question routing | **FAIL** | Two VibePulse DNS-SD services were present; the relay-disabled image could select a different healthy host, and the canonical question timed out |

## Lessons locked in

1. Fresh host and relay data do not prove fresh glass; require panel-contact
   evidence or a human glass check.
2. A failed esptool connection before erase/write is recoverable and must not
   be described as a partial flash.
3. This unit needs the silent BOOT button held across RESET to enter the ROM
   loader when automatic reset fails.
4. Computer USB is suitable for download mode but is not a valid runtime-power
   acceptance setup for AMOLED plus Wi-Fi.
5. Interaction success and a fresh data payload are separate gates from the
   literal stale-label visual check.
6. One successful round trip after boot is not a sustained-runtime pass. A
   release gate must cover at least the panel's stale window plus recovery
   margin and must include a second interaction.
7. ICMP reachability does not prove that application HTTP tasks are making
   progress. Record both network-interface liveness and last successful panel
   request.
8. Fresh numbers do not prove correct question routing. On a LAN with several
   VibePulse hosts, first-result DNS-SD selection is not user intent; use the
   encrypted interaction relay for a shared panel.

## Candidate remediation — partially verified

The follow-up firmware change disables ESP-IDF's default modem sleep for this
wall-powered live display, closes the encrypted relay client on every failure
exit, and adds a VibePulse-specific recovery policy. The policy arms only
after a real quota success, only while Wi-Fi still reports association, and
only when an independent numbers relay is configured. At 150 seconds without
another quota success it recycles the station transport; a ten-minute cooldown
prevents a real upstream outage from becoming a reconnect loop. Cold start,
LAN-only, disassociated, clock-regression, threshold, and cooldown decisions
pass host tests, and the ESP32-S3 image builds successfully.

The HTTP part is **PHYSICALLY VERIFIED ONLY IN A BOUNDED COMPUTER-USB
DIAGNOSTIC WINDOW**. It must not change the end-to-end failure verdict above
until the image passes the same window on dedicated power and completes a
second canonical physical question. Because two VibePulse hosts are advertised
on this LAN, the next image must also enable the already deployed encrypted
interaction relay; direct LAN discovery alone cannot prove which host owns the
question.
