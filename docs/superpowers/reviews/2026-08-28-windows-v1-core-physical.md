# Windows v1 core and physical validation — 2026-08-28

## Outcome

**CORE + PHYSICAL PASS; PERSISTENT LIFECYCLE PARTIAL.** A clean Windows host
checkout at exact revision `bee5d8c9c9b47b761b5970c346cc0e641ac82485`
served the real panel and completed the canonical human Codex answer loop.
Sign-out/sign-in, sleep/resume, and reboot were not performed and remain
NOT TESTED. This report therefore supports the narrow claim “Windows core and
physical answer loop verified,” not “every Windows lifecycle row passed.”

No credential, account identifier, prompt payload, session content, quota
value, private address, device key, or relay address is recorded here.

## Sanitized evidence

| Gate | Status | Evidence |
|---|---|---|
| Exact clean host checkout | PASS | Detached host code was exactly `bee5d8c9c9b47b761b5970c346cc0e641ac82485`; status was empty |
| Complete Windows tokenserver suite | PASS | 788 tests, 11 skips, 0 failures/errors; exit 0 |
| PowerShell parser and `-ValidateOnly` | PASS | All three Windows scripts parsed; validation resolved the real interpreter and checkout without installing |
| Task Scheduler install and immediate start | PASS | The user-scoped task installed from the exact checkout and served the expected revision |
| Exact-process watchdog recovery | PASS | Only the verified tokenserver PID was terminated; the task watchdog created a new exact-owned PID serving the same revision |
| Bounded scheduled-task log | PASS | Live log and retained tail stayed inside their documented bounds without traceback or restart churn |
| Claude source health | PASS | Safe probe state was healthy; both weekly observations were fresh and numeric |
| Codex source health | PASS | Standalone CLI login succeeded and the app-server weekly observation was fresh and numeric; no value was printed |
| Codex plugin/MCP | PASS | Setup, doctor, registration, initialize, and tool listing passed with the owned local bridge and the 130-second bounded tool window |
| Private firewall and LAN | PASS | Inbound TCP 8737 was limited to the Private profile; a non-loopback LAN self-check reached the service |
| Mac/Windows host discovery | PASS | The panel moved between advertising Mac and Windows tokenservers after a bounded failure without changing a compiled host address |
| Recent physical panel polling | PASS | Root health reported recent polling on `/api/agent-status` throughout a parked question |
| Firmware/parser contract | PASS | The live bounded status payload contained a valid v2 pending view and the shipped C parser accepted that exact payload |
| Canonical physical answer | PASS | The panel showed the two-stage `NEEDS YOU` → `APPROVE` flow; a human tapped the recommended answer and the host returned `status: answered`, `option_index: 0`, `answer: Ja` |
| Service after the physical check | PASS | The scheduled tokenserver continued serving the same exact revision |
| Sign-out/sign-in | NOT TESTED | Disruptive user-session transition was not authorized during this pass |
| Sleep/resume | NOT TESTED | Disruptive physical lifecycle transition was not authorized during this pass |
| Reboot | NOT TESTED | Full Windows restart was not authorized during this pass |

## Claim boundary

The exact physical product path is proven: Windows source → scheduled local
service → Private LAN → physical panel → visible explicit choice → human tap
→ structured answer returned to the originating call. Silence, fallback, and
the private buttonless screen were not counted as approval.

Issue [#28](https://github.com/niclasvestlund-YT/vibepulse/issues/28) remains
open for persistent lifecycle completion. Those rows must be rerun against an
exact clean release candidate before the broader claim “full Windows release
certification” is used.
