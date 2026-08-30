# VibePulse stale-recovery physical review — 2026-08-30

## Outcome

**SUSTAINED-RUNTIME FAIL; TRANSIENT RECOVERY ONLY.**
The physical unit `torget-home-01` now runs
`v1.0.0-18-g3a131a2`. The build tree was byte-identical to merged `main`
`f672a14`, which contains the stale-glass diagnostic and runbook changes from
PR #57. No newer OTA version was advertised at the verification checkpoint.

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

## Candidate remediation — not yet a physical pass

The follow-up firmware change disables ESP-IDF's default modem sleep for this
wall-powered live display, closes the encrypted relay client on every failure
exit, and adds a VibePulse-specific recovery policy. The policy arms only
after a real quota success, only while Wi-Fi still reports association, and
only when an independent numbers relay is configured. At 150 seconds without
another quota success it recycles the station transport; a ten-minute cooldown
prevents a real upstream outage from becoming a reconnect loop. Cold start,
LAN-only, disassociated, clock-regression, threshold, and cooldown decisions
pass host tests, and the ESP32-S3 image builds successfully.

This remediation remains **NOT PHYSICALLY VERIFIED**. It must not change the
failure verdict above until the new image stays fresh beyond the stale window,
reports recent direct panel polls, and completes a second canonical physical
question.
