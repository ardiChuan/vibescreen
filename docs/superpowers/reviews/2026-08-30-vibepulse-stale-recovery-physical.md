# VibePulse stale-recovery physical review — 2026-08-30

## Outcome

**FULL STALE-RECOVERY PASS.**
The physical unit `torget-home-01` now runs
`v1.0.0-18-g3a131a2`. The build tree was byte-identical to merged `main`
`f672a14`, which contains the stale-glass diagnostic and runbook changes from
PR #57. No newer OTA version was advertised at the verification checkpoint.

The firmware flash, wall-powered network recovery, local service discovery,
direct panel polling, fresh Claude/Fable/Codex payloads, touch input, the
canonical physical APPROVE round trip, and absence of the literal `STALE`
label on the main view all passed. The first dedicated visual question
returned computer fallback with reason `leave_it` and was not counted; the
user then inspected the main view directly and confirmed that `STALE` was
gone.

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
| Dedicated-power runtime | PASS | After moving to a dedicated 5 V supply, the panel completed an encrypted interaction and later resumed direct LAN polling |
| Service discovery | PASS | Host discovery reported `ready` |
| Direct panel contact | PASS | Root health changed from `waiting` to `ready` after two confirmed panel polls |
| Provider freshness | PASS | Claude weekly, Fable/model-week, and Codex weekly stale flags were all false |
| Physical APPROVE | PASS | Exact question `Ser du APPROVE?`; visible-state instruction required APPROVE; human tapped `Ja`; returned `answered`, option index 0, answer `Ja` |
| Literal `STALE` absent on glass | PASS | Computer fallback was discarded; the user then directly inspected the main view and confirmed that `STALE` was gone |

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
