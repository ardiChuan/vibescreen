# Windows v1 full lifecycle validation — 2026-08-28

## Outcome

**FULL WINDOWS v1 PASS.** The previously verified Windows v1 host completed
the three deliberately deferred persistent transitions: real
sign-out/sign-in, real sleep/resume, and one full Windows reboot. Task
Scheduler, the local service, safe Claude/Codex source health, and recent
physical-panel polling all recovered within a bounded readiness window.

The installed runtime remained exact host revision
`bee5d8c9c9b47b761b5970c346cc0e641ac82485`. Release tag `v1.0.0` resolves to
`ab3ce92a069b4cc66312b6043e3715829d1bb763`; the eight changed files between
those revisions are documentation/tests only, with zero runtime files. This
continuation therefore validates the runtime shipped by v1.0.0 without
pretending that a later runtime was exercised.

No credential, account identifier, prompt payload, session content, quota
value, private address, device key, relay address, or private route is recorded
here.

## Persistent lifecycle evidence

| Gate | Result | Sanitized evidence |
|---|---|---|
| Pre-transition health | PASS | The scheduled task was running; the service revision was present; Claude and Codex weekly observations were numeric and fresh |
| Sleep entered | PASS | Windows recorded a Kernel-Power sleep transition after the saved baseline |
| Resume occurred | PASS | Windows recorded a Power-Troubleshooter resume event on the same boot |
| Service after resume | PASS | The task remained running and the local service returned successfully |
| Sources after resume | PASS | Claude returned immediately; Codex converged within the bounded three-minute readiness window and the final checkpoint was fresh |
| Sign-out/sign-in | PASS | A real user sign-out and sign-in occurred; the logon trigger ran after the saved baseline and the service was healthy afterward |
| Stable sources after sign-in | PASS | Claude and Codex were fresh for 12 of 12 consecutive five-second samples after initialization |
| Full reboot occurred | PASS | The post-check boot identifier differed from the saved pre-reboot identifier |
| Task Scheduler after reboot | PASS | The task ran after the new boot and remained in the running state |
| Service after reboot | PASS | The local service returned successfully with a revision present |
| Sources after reboot | PASS | Claude was fresh; Codex converged inside the bounded three-minute readiness window |
| Stable sources after reboot | PASS | Codex was fresh for 12 of 12 consecutive five-second samples |
| Physical panel after reboot | PASS | Panel status was `ready`, polling age was numeric and inside the 120-second recent window, and the service remained healthy |

## Combined Windows v1 verdict

This continuation completes the earlier
[core and physical report](2026-08-28-windows-v1-core-physical.md). Together,
the two reports cover the clean checkout, full suite, parser and
`-ValidateOnly`, real Task Scheduler installation, immediate start, exact-PID
watchdog recovery, bounded logs, real providers, Private-only firewall and LAN
reachability, discovery, recent polling, the canonical visible human answer,
sign-out/sign-in, sleep/resume, and reboot.

Every required row in [Windows release validation](../../windows-validation.md)
is PASS for the recorded v1 runtime. Silence, fallback, and a buttonless screen
were never counted as approval. This evidence is exact-revision evidence, not
a permanent waiver for future releases.
