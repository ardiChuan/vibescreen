# VibePulse Codex question — physical end-to-end review (2026-08-27)

## Outcome

**PASS** on `torget-home-01`. The physical panel displayed the recommended
answer and the **APPROVE** action, accepted the touch, and returned the same
answer to the waiting Codex call.

The verified USB flash was built from the main Torget checkout and identified
itself as `v0.7.0-5-ge6feb29-dirty` (ESP-IDF 5.5.2, boot ELF SHA prefix
`ee300ac90`). Display, touch, Wi-Fi and the first token fetch all initialized
without an immediate OTA takeover.

## What failed before the pass

1. A successful build from an older worktree flashed
   `v0.6.0-114-gdf04327-dirty`. The server already advertised
   `v0.6.0-150-g052ac77`, so **UPDATE READY** immediately took over the screen.
2. The project attract label used the uppercase-only `plex_text_21` font.
   Swedish lowercase characters became boxes. It now uses `plex_ui_21`; the
   physical `RÄKSMÖRGÅS` fixture rendered correctly.
3. A question without exactly one explicit recommendation could only offer
   **LEAVE IT**. A longer question that failed the firmware's physical fit gate
   deliberately became the private **SOMETHING IS WAITING** screen with no
   answer buttons. Neither state is approval.

## Canonical physical smoke test

Use this exact short payload after a VibePulse/Codex setup change or firmware
flash:

- header: `Test`
- question: `Ser du APPROVE?`
- option 1: `Ja`, description `APPROVE syns`, `recommended: true`
- option 2: `Nej`, description `APPROVE saknas`

Expected sequence on the panel:

1. the waiting/attract screen appears;
2. a tap opens the decision;
3. the recommended `Ja` card, **APPROVE**, and **LEAVE IT** are visible;
4. the other option remains available on the computer by design;
5. tapping **APPROVE** closes the physical flow;
6. the waiting tool call returns `status: answered`, `option_index: 0`,
   `answer: Ja`.

`DENY` belongs to readable permission cards; it is not the second button for
a recommended question. The verified request was
`dql6ESFSyAY49W4b6EKd9w` and the tokenserver recorded verdict `approve` at
00:21:35 local time. The human observer also confirmed the visible result.

Silence, timeout, **LEAVE IT**, panel absence, computer fallback, or the private
fit-gate screen are all failures of this smoke test. Never reinterpret them as
approval.

## Mandatory flash guards

Before flashing:

1. run `git describe --tags --always --dirty` in the checkout being built;
2. compare that version with the service's `otaAvailableVersion`;
3. preview, test, build, and flash from the same checkout;
4. include a Swedish text fixture in the preview when fonts changed.

After flashing:

1. verify the written image hash and the booted firmware version;
2. wait through the first Wi-Fi and token poll — an immediate
   **UPDATE READY** usually means the wrong or older checkout was flashed;
3. run the canonical smoke test above;
4. require both the physical observation and the returned tool result to agree.

## Recovery table

| Symptom | Meaning | Recovery |
|---|---|---|
| Immediate **UPDATE READY** after USB flash | Flashed image is older than the advertised OTA build, commonly due to the wrong worktree | Stop testing, compare both versions, rebuild and flash from the intended checkout |
| Only **LEAVE IT** is visible | No single option was explicitly marked recommended | Resend one short question with 2–3 options and exactly one genuine recommendation |
| **SOMETHING IS WAITING** with no answer buttons | Text/detail did not pass the physical fit/privacy gate | Continue on the computer; shorten only a non-secret diagnostic prompt and retry |
| Boxes instead of letters | The selected font lacks those glyphs | Use `plex_ui_21` for mixed-case/localized UI and rerun the Swedish fixture |
| Tool reports computer fallback or timeout | The panel path did not complete | Use the computer prompt; do not count the run as passed |
| Tool reports `answered`, but the observer saw something else | UI/result mismatch | Treat as a failed end-to-end test and inspect the request ID in tokenserver logs |

This review records evidence; it does not authorize future flashes, change
interaction opt-ins, or weaken Codex permission policy.
