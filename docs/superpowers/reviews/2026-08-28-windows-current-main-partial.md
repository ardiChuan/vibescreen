# Windows current-main validation checkpoint — 2026-08-28

## Outcome

**PARTIAL — not a Windows physical end-to-end GO.** Real Windows evidence now
covers the exact `7c204f9` current-main checkout, PowerShell 5.1/7 validation,
the complete host suite, Task Scheduler installation and immediate task start,
the live service, and fresh Claude/Codex quota sources after the asynchronous
Codex refresh completed. The current rerun also found an unresolved Codex
plugin/MCP registration discrepancy, no Windows interaction device key, no
recent panel polling, and the existing Private-firewall gap. Those findings
prevent a physical end-to-end claim.

The earlier unavailable-PC interval remains an evidence boundary, not a
product failure and never a pass. Observations remain valid only for the exact
commits named below.

## Sanitized checkpoints

| Checkpoint | Exact revision | Evidence |
|---|---|---|
| Full real-PC baseline | `71ff7a98c8d763da05191edcc20f3ac889226e8f` | Clean checkout; 783 tests, 11 skips, 0 failures/errors; three PowerShell parsers; Windows PowerShell 5.1 and PowerShell 7 `-ValidateOnly`; temporary real-source endpoints; Task Scheduler install and immediate start; bounded log; fresh Claude and Codex sources |
| Installed post-fix task | `e20e8a13f50e39292fdf365f774d32822aea7156` | Clean checkout matched `origin/main`; scheduled task was running the exact revision; pinned standalone Codex executable and `CODEX_HOME` were valid; scheduled API returned a numeric, fresh Codex weekly observation; bounded log remained healthy |
| Latest host-code revision | `7093aff7715fc2e0fbf941db70cdb507c0861c41` | All PR #37 checks passed; the complete tokenserver suite passed with 783 tests and 11 skips; the default-timeout Codex app-server probe passed on real Windows. The complete scheduled-task and physical lifecycle was not rerun on this exact host-code revision |
| Checkpoint publication | [PR #38](https://github.com/niclasvestlund-YT/vibepulse/pull/38) | Documentation-only change; both Windows jobs, both full host gates, both ESP32 builds, and all relay/macOS/Ubuntu jobs passed. This adds no new real-PC evidence |
| Exact current-main rerun | `7c204f915ee41744c8a8cac7dbbe1082ff5fd77b` | New clean clone matched `origin/main`; the complete tokenserver suite exited 0; parser and `-ValidateOnly` passed in PowerShell 7.6 and Windows PowerShell 5.1; the runner passed; Task Scheduler installed and entered `Running` with the exact checkout plus pinned Codex bin/home; the live API eventually reported the exact revision and fresh Claude/Codex observations. The Codex refresh was asynchronous and temporarily stale before its app-server child completed |

No account identifier, credential, token, session content, prompt payload,
private path, or LAN address is included here.

## Gate status for current `main`

| Gate | Status | Evidence boundary |
|---|---|---|
| Automated Windows suite | PASS | Green Windows matrix and setup-integration checks on the current merge |
| Real Windows Codex app-server probe | PASS | Default production timeout passed on the PR #37 Windows host run |
| Exact current-main clean checkout on the PC | PASS | Fresh clone was clean, exactly `7c204f9`, and contained the required merge |
| Installer parser and `-ValidateOnly` | PASS | Three scripts parsed with zero errors; `-ValidateOnly` exited 0 in PowerShell 7.6 and Windows PowerShell 5.1 |
| Task install and immediate start | PASS | Installer exited 0; task entered `Running` and pinned the exact checkout, Codex bin, and Codex home. API readiness took longer than the first 45-second observation window but recovered without a change |
| Exact-process automatic watchdog restart | NOT TESTED on current main | The pre-fix baseline failed; the watchdog fix is merged and tested in CI, but the final real-process repetition is still required |
| Bounded scheduled-task log | PARTIAL on current main | The runner's capture/rotation checks passed and the real task created its log; the live file/rotation bounds were not re-measured in the final rerun |
| Claude source | PASS | Safe probe status and fresh weekly/model observations were recorded on the exact current-main service |
| Codex source | PASS | The task-pinned direct probe passed; the scheduled source became fresh with a numeric observation after its asynchronous app-server cycle completed |
| Codex plugin/MCP registration | FAIL / unresolved | Final doctor reported both missing after the setup command had returned success; a later read-only CLI provenance query timed out. Neither state is called PASS |
| Windows interaction device key | FAIL | The exact-current-main service reported that no device key was available, so Windows cannot accept a panel verdict |
| Private-profile firewall | FAIL | No matching inbound Private TCP 8737 rule was present; the validation process was not elevated and did not change it |
| Second-device LAN reachability | NOT TESTED | Private-address self-check passed; another LAN device was not used |
| Recent panel polling | FAIL | Exact-current-main root health reported `waiting`, not `ready` |
| Remote validation follow-ups | BLOCKED | The host remained online, but three consecutive bounded follow-up turns completed without message or tool output. No result was inferred, and no replacement task was created without explicit authorization. This is a validation-transport blocker, not a product PASS or product failure |
| Canonical physical question and human answer | NOT TESTED | No visible **APPROVE**, human tap, and returned `answered / 0 / Ja` tuple on Windows |
| Sign-out/sign-in | NOT TESTED | Requires a real user-session transition |
| Sleep/resume | NOT TESTED | Requires the physical PC and panel |
| Reboot | NOT TESTED | Requires the physical PC and panel |

## What can proceed unattended

When the PC is reachable, an agent may continue with the unresolved
plugin/MCP provenance, exact-process watchdog restart, live log-bound check,
Private-profile inspection, and LAN self-check. It must use bounded CLI probes,
kill only diagnostic children it started, and preserve only sanitized evidence.

## What still requires a person

- Elevation for a missing Private-only firewall rule; never open the Public
  profile and never silently grant elevation.
- Review and trust of the exact VibePulse hooks in Codex.
- Provisioning the same private interaction device key on Windows and the
  panel; the key must never be pasted into an issue, report, or commit.
- A real sign-out/sign-in, sleep/resume, and reboot when those transitions
  cannot be performed safely by the validation agent.
- The physical smoke test: visible **APPROVE**, a human tap on `Ja`, and the
  returned `status: answered`, `option_index: 0`, `answer: Ja` result.

Until every required row passes on one exact candidate, Windows host support
may be described as implemented and partially real-host validated. The current
candidate must not be advertised as Windows physical end-to-end validated.
