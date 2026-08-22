# VibePulse Coordinated Numbers Relay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development to execute this plan task by task.

**Goal:** Keep quota, Max Tracker, and GitHub fresh on any Wi-Fi by replacing
the exhausted KV-list path with a strongly consistent numbers mailbox while
preserving the numbers-only privacy boundary and existing firmware contract.

**Architecture:** The public Worker performs the existing authentication and
validation, then calls one deterministically named `NumbersMailbox` Durable
Object through `NUMBERS_MAILBOX`. The SQLite-backed object transactionally owns
the bounded publisher registry and endpoint documents. Existing KV data and
binding remain untouched only as a rollback safety net.

**Tech stack:** Cloudflare Workers JavaScript, SQLite-backed Durable Objects,
Node/Vitest Worker tests as appropriate, Python boundary tests, Wrangler 4.

## File map

- Modify `tools/relay/worker.js`: public boundary plus Durable Object class.
- Modify `tools/relay/test.mjs`: pure merge and public routing regressions.
- Add only the minimum package/config/test files needed to run a real
  Cloudflare Durable Object test runtime and Wrangler dry build.
- Later modify `tools/relay/README.md`, `docs/relay.md`, and `docs/lessons.md`.
- Preserve `tools/tokenserver/publisher.py` and firmware wire contracts.
- Do not modify secrets, `sdkconfig`, panel partitions, OTA images, or live
  Cloudflare state until all reviews and repository gates pass.

## Task 1: Replace the reviewed KV index with a coordinated mailbox

- [ ] Add RED tests for concurrent first registration, stale/index
  displacement regression, strict ninth rejection, atomic registration plus
  document storage, storage failure, and corrupt-row isolation.
- [ ] Add RED tests showing the public Worker requires the
  `NUMBERS_MAILBOX` binding, selects one deterministic mailbox, preserves all
  old auth/validation responses, and performs no KV request-path operation.
- [ ] Implement `NumbersMailbox` with SQLite storage and synchronous
  transactions. Keep all SQL bounded by the existing eight-publisher limit.
- [ ] Route validated requests through a Durable Object stub using RPC or the
  internal fetch interface. Always await the call and translate unexpected
  mailbox errors to a non-success response without leaking details.
- [ ] Preserve `mergeTokens()` and `newestBody()` semantics exactly.
- [ ] Remove the KV publisher-index code introduced by commit `0e345c1`.
- [ ] Run focused tests to GREEN and commit only implementation/test/config
  files with a plain root-cause commit message.

## Task 2: Independent review loop

- [ ] Spec review against the revised coordinated-mailbox design.
- [ ] Quality/security review focused on Durable Object atomicity, SQL bounds,
  concurrent requests, corrupt storage, binding failure, privacy, response
  compatibility, and free-tier request/row arithmetic.
- [ ] The original implementer fixes every confirmed Important/Critical issue
  with RED-first regressions.
- [ ] Repeat spec review first, then quality review, until both are READY.

## Task 3: Document setup, migration, rollback, and lessons

- [ ] Update `tools/relay/README.md` with a complete Wrangler configuration
  containing the existing KV binding, `NUMBERS_MAILBOX` Durable Object
  binding, and SQLite `NumbersMailbox` export.
- [ ] Explain that the existing KV binding/data are retained only for rollback
  and the new path does not read or write them.
- [ ] Update `docs/relay.md` with all-Wi-Fi behavior, exact daily request/row
  arithmetic, first-deploy empty mailbox, republish/restart procedure, and
  recovery checks.
- [ ] Update `docs/lessons.md` with both failures: independent KV list quota and
  eventual-consistency hazards in dynamic KV indexes.
- [ ] Update any stale operator text that still claims five-minute heartbeat
  behavior for endpoints now capped at thirty minutes.
- [ ] Run docs/privacy tests and commit the docs separately.

## Task 4: Verify before changing Cloudflare

- [ ] Run the focused Worker/Durable Object suite.
- [ ] Run `tools.tokenserver.test_publisher` and
  `test/test_relay_boundary.py`.
- [ ] Run `PYTHON_BIN="$PWD/.venv/bin/python" ./test/run.sh`.
- [ ] Run a Wrangler dry deployment using the repository config/example and
  confirm the SQLite class is provisionable.
- [ ] Review `origin/main..HEAD` for exact scope; no secrets, `.wrangler`,
  generated firmware config, binaries, or panel partition changes.

## Task 5: Deploy and prove live recovery without OTA

- [ ] Capture the current Worker version and exact live bindings without
  printing the relay secret.
- [ ] Build a private temporary Wrangler config outside git using the tested
  source plus the existing KV namespace ID, `NUMBERS_MAILBOX` binding, and
  SQLite `NumbersMailbox` export. Re-read it before deploy.
- [ ] Deploy with preserved secrets/vars and inspect the new version bindings.
- [ ] Restart the existing launchd tokenserver so it republishes all three
  documents into the empty mailbox. Do not change launch arguments.
- [ ] Wait for local `usage_http_200 + ok` and non-stale Claude fields.
- [ ] Compare only non-secret local/cloud number fields, then allow one panel
  polling interval and ask the user to confirm `STALE` clears.
- [ ] If verification fails, roll back to the captured Worker version. Do not
  touch firmware or OTA as part of relay rollback.

## Task 6: Finish branch and return to the Wi-Fi icon

- [ ] Request a final independent review of implementation, docs, full-gate
  evidence, deployment evidence, and exact branch scope.
- [ ] Push/open or update the PR only after CI is green.
- [ ] Then continue the separate two-state Wi-Fi icon request (full connected
  icon versus distinct full-size offline symbol) with simulator and physical
  panel verification.
