# Windows current-main validation checkpoint — 2026-08-28

## Outcome

**PARTIAL — not a Windows physical end-to-end GO.** Real Windows evidence now
covers the host service, Task Scheduler installation and immediate start,
bounded logging, and both quota sources on post-v0.7.1 code. The exact current
`main` commit has green automated checks and a real-Windows Codex app-server
probe, but it was not reinstalled for the complete lifecycle before the remote
PC became unavailable.

The unavailable PC is recorded as an evidence boundary, not as a product
failure and never as a pass. Earlier observations remain valid only for the
exact commits named below.

## Sanitized checkpoints

| Checkpoint | Exact revision | Evidence |
|---|---|---|
| Full real-PC baseline | `71ff7a98c8d763da05191edcc20f3ac889226e8f` | Clean checkout; 783 tests, 11 skips, 0 failures/errors; three PowerShell parsers; Windows PowerShell 5.1 and PowerShell 7 `-ValidateOnly`; temporary real-source endpoints; Task Scheduler install and immediate start; bounded log; fresh Claude and Codex sources |
| Installed post-fix task | `e20e8a13f50e39292fdf365f774d32822aea7156` | Clean checkout matched `origin/main`; scheduled task was running the exact revision; pinned standalone Codex executable and `CODEX_HOME` were valid; scheduled API returned a numeric, fresh Codex weekly observation; bounded log remained healthy |
| Current merged main | `7093aff7715fc2e0fbf941db70cdb507c0861c41` | All PR checks passed; the complete tokenserver suite passed with 783 tests and 11 skips; the default-timeout Codex app-server probe passed on real Windows. The complete scheduled-task and physical lifecycle was not rerun on this exact merge commit |

No account identifier, credential, token, session content, prompt payload,
private path, or LAN address is included here.

## Gate status for current `main`

| Gate | Status | Evidence boundary |
|---|---|---|
| Automated Windows suite | PASS | Green Windows matrix and setup-integration checks on the current merge |
| Real Windows Codex app-server probe | PASS | Default production timeout passed on the PR #37 Windows host run |
| Exact current-main clean checkout on the PC | NOT TESTED | The host became unavailable before the final clean clone and reinstall |
| Installer parser and `-ValidateOnly` | PASS on earlier candidate | Real Windows PowerShell 5.1/7 evidence exists for `71ff7a98`; current-main coverage is automated |
| Task install and immediate start | PASS on earlier merged candidate | Exact scheduled revision was observed after the Windows fixes merged |
| Exact-process automatic watchdog restart | NOT TESTED on current main | The pre-fix baseline failed; the watchdog fix is merged and tested in CI, but the final real-process repetition is still required |
| Bounded scheduled-task log | PASS on earlier merged candidate | Current and rotated tails stayed within their bounds with no recent traceback/error |
| Claude source | PASS on earlier merged candidate | Safe probe status and fresh weekly/model observations were recorded |
| Codex source | PASS on earlier merged candidate | Scheduled API was fresh with a numeric observation; task-pinned CLI environment was healthy |
| Private-profile firewall | FAIL | No matching inbound Private TCP 8737 rule was present; the validation process was not elevated and did not change it |
| Second-device LAN reachability | NOT TESTED | Private-address self-check passed; another LAN device was not used |
| Recent panel polling | FAIL | Last safe state was `waiting`, not `ready` |
| Canonical physical question and human answer | NOT TESTED | No visible **APPROVE**, human tap, and returned `answered / 0 / Ja` tuple on Windows |
| Sign-out/sign-in | NOT TESTED | Requires a real user-session transition |
| Sleep/resume | NOT TESTED | Requires the physical PC and panel |
| Reboot | NOT TESTED | Requires the physical PC and panel |

## What can proceed unattended

When the PC is reachable, an agent may use a new clean checkout of the exact
candidate to rerun the suite, installer validation, task install, immediate
start, exact-process watchdog restart, bounded-log inspection, safe provider
health, Private-profile inspection, and LAN self-check. It must preserve only
sanitized evidence.

## What still requires a person

- Elevation for a missing Private-only firewall rule; never open the Public
  profile and never silently grant elevation.
- Review and trust of the exact VibePulse hooks in Codex.
- A real sign-out/sign-in, sleep/resume, and reboot when those transitions
  cannot be performed safely by the validation agent.
- The physical smoke test: visible **APPROVE**, a human tap on `Ja`, and the
  returned `status: answered`, `option_index: 0`, `answer: Ja` result.

Until every required row passes on one exact candidate, Windows host support
may be described as implemented and partially real-host validated. The current
candidate must not be advertised as Windows physical end-to-end validated.
