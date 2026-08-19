# VibePulse Encrypted Interaction Relay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make default-off Claude and Codex Needs You decisions work when the panel and computer are on unrelated, client-isolated Wi-Fi by sending only bounded end-to-end-encrypted panel views and verdicts through a user-owned Cloudflare mailbox.

**Architecture:** Keep the existing numbers relay unchanged. Add a separate TypeScript Worker whose one SQLite-backed Durable Object per mailbox atomically coordinates create-once requests, one-time verdicts, and 120-second expiry. The tokenserver and panel derive direction-separated keys from the existing device key, encrypt before outbound HTTPS, verify after receipt, and retain the existing live local interaction store as the only authority that may resolve an agent hook.

**Tech Stack:** Python 3.11, `cryptography` 49, TypeScript 7, Wrangler 4, Cloudflare Workers, SQLite-backed Durable Objects, Vitest Workers integration, C11, ESP-IDF 5.5, Mbed TLS AES-GCM/HKDF/HMAC, cJSON, host C tests, SDL simulator.

---

## Prerequisites and delivery boundaries

Implement `2026-08-19-vibepulse-codex-local-interactions.md` first. This plan
uses its provider-neutral store, exact `view_sha256`, saved independent feature
switches, and provider-aware direct verdict contract.

Execute both plans in the same isolated worktree created from commit `6359dcf`.
The user's current checkout has unrelated changes and throwaway simulator
probes. Before every commit, reject staged `--utf8-test`, `--wedge-repro`,
`sdkconfig`, secret, `.wrangler`, swipe-navigation, or `ota_0` changes.

This plan never modifies the existing `tools/relay/worker.js` or
`tools/tokenserver/publisher.py` activity boundary. It creates a distinct
`tools/interaction-relay/` service. A fresh clone remains LAN-only and does not
need Node, Cloudflare, `cryptography`, relay credentials, or the new firmware
task. Physical validation may write only the `ota_1` application slot.

Current Cloudflare API details must be rechecked against official docs at
implementation time. The plan intentionally uses current recommendations:
SQLite-backed Durable Objects, RPC through `getByName()`, alarms for expiry,
generated binding types, and the Workers Vitest runtime.

## File structure

### Cloudflare service

- Create `tools/interaction-relay/package.json` and `package-lock.json`: pinned
  build, typecheck, test, and deploy dependencies.
- Create `tools/interaction-relay/wrangler.jsonc`: Worker, generated types,
  observability, one SQLite Durable Object migration, and non-secret mailbox.
- Create `tools/interaction-relay/src/index.ts`: bounded HTTP router,
  role-separated bearer authentication, and Durable Object RPC calls.
- Create `tools/interaction-relay/src/mailbox.ts`: strongly consistent
  create/read/verdict/delete/expiry state machine.
- Create `tools/interaction-relay/src/envelope.ts`: narrow path/body/envelope
  validators and constant-time bearer comparison.
- Create `tools/interaction-relay/test/*.test.ts`: HTTP, storage, concurrency,
  authentication, headers, and alarm tests in the Workers runtime.
- Create `tools/interaction-relay/vitest.config.ts`, `tsconfig.json`, generated
  `worker-configuration.d.ts`, `.gitignore`, and `README.md`.

### Tokenserver

- Create `tools/tokenserver/interaction_relay_crypto.py`: exact v1 key
  derivation, framing, padding, AEAD, verdict MAC, and strict decoding.
- Create `tools/tokenserver/interaction_relay.py`: bounded publish/delete queue,
  conditional verdict polling, retry/backoff, redacted diagnostics, and store
  integration.
- Create `tools/tokenserver/test_interaction_relay_crypto.py` and
  `test_interaction_relay.py`.
- Modify `tools/tokenserver/interactions.py`, `vibepulse_config.py`,
  `tokenserver.py`, their tests, and `tools/vibepulse_setup.py`.
- Create `requirements-interaction-relay.txt`: the only optional runtime
  dependency file.

### Firmware

- Create `components/app_tokens/interaction_relay_crypto.h/.c`: fixed-size
  hex/base64url/HKDF/AES-GCM/HMAC/padding primitives.
- Create `components/app_tokens/interaction_relay_policy.h/.c`: source merge,
  answered suppression, route choice, retry, and backoff as host-testable C.
- Create `components/app_tokens/interaction_relay_net.h/.c`: bounded HTTPS
  polling, decrypt/validate/apply, and exact-envelope verdict retry task.
- Modify `components/app_tokens/agent_status.h`, `agent_monitor.c`,
  `needs_you_net.c`, `app.c`, and `CMakeLists.txt`.
- Modify `components/torget_net/torget_http.h/.c` and its CMake file to add a
  shared Cloudflare/TLS gate that is never held with the LVGL lock.
- Modify `main/Kconfig.projbuild`, `secrets.h.example`, and add build guards.
- Create host tests and shared vectors under `test/` and `test-vectors/`.

## Task 1: Pin the cross-language cryptographic protocol

**Files:**
- Create: `test-vectors/interaction-relay-v1.json`
- Create: `tools/tokenserver/interaction_relay_crypto.py`
- Create: `tools/tokenserver/test_interaction_relay_crypto.py`
- Create: `requirements-interaction-relay.txt`
- Modify: `test/run.sh`

- [ ] **Step 1: Write failing tests around fixed inputs**

Use these immutable vector inputs:

```python
DEVICE_KEY_HEX = "000102030405060708090a0b0c0d0e0f" \
                 "101112131415161718191a1b1c1d1e1f"
MAILBOX = "vp_A1b2C3d4E5f6G7h8"
REQUEST_ID = "ABEiM0RVZneImaq7zN3u_w"
CHALLENGE_HEX = "202122232425262728292a2b2c2d2e2f" \
                "303132333435363738393a3b3c3d3e3f"
REQUEST_NONCE_HEX = "404142434445464748494a4b"
VERDICT_NONCE_HEX = "505152535455565758595a5b"
VIEW_BYTES = (b'{"provider":"codex","kind":"question",'
              b'"prompt":"How should Codex handle approvals?",'
              b'"title":"Use the trusted hook",'
              b'"subtitle":"Desktop + CLI, one setup",'
              b'"can_approve":true}')
```

Tests must assert literal values loaded from the committed JSON for all three
HKDF outputs, request/verdict associated data, request/view digests, framed
plaintext lengths 2048/1024, request and verdict ciphertext plus GCM tag,
verdict HMAC, and unpadded base64url. Vector padding is deterministic byte
`0xA5`; production padding must come from `secrets.token_bytes()`.

- [ ] **Step 2: Run the focused test and verify the missing module failure**

Run: `python3 -m unittest tools.tokenserver.test_interaction_relay_crypto -v`

Expected: `ModuleNotFoundError` naming `interaction_relay_crypto`.

- [ ] **Step 3: Implement strict Python framing and crypto**

Expose these functions with no network or store dependency:

```python
decode_device_key(hex_text: str) -> bytes
derive_keys(device_key: bytes, mailbox: str) -> RelayKeys
encode_request(keys, mailbox, request_id, challenge, expires_at,
               view_bytes, nonce=None, padding=None) -> bytes
decode_request(keys, mailbox, request_id, envelope: bytes) -> RelayRequest
encode_verdict(keys, mailbox, request, verdict, nonce=None,
               padding=None) -> bytes
decode_verdict(keys, mailbox, request_id, envelope: bytes) -> RelayVerdict
verify_verdict_mac(keys, mailbox, request, verdict) -> bool
```

Use `HKDF(SHA256, length=32)` with salt
`sha256(b"VibePulse interaction relay v1")` and exact info
`b"vibepulse-ir/v1|" + mailbox + b"|" + label`. Use AES-256-GCM with a
12-byte nonce and 16-byte tag. Reject padded frames unless their two-byte
length prefix fits entirely, decoded JSON has only the documented keys,
base64url is canonical and unpadded, request IDs decode to 16 bytes,
challenges/digests decode to 32 bytes, and the exact view stays within 640
bytes. Compare MAC/digests with `hmac.compare_digest`.

Pin `cryptography==49.0.0` only in
`requirements-interaction-relay.txt`; do not add it to default requirements.

- [ ] **Step 4: Generate once, freeze, and independently re-read the vector**

Generate `test-vectors/interaction-relay-v1.json` using the fixed inputs and
the installed `cryptography` package. Then make the unit test reconstruct
every output without writing the fixture. Tamper every nonce, ciphertext,
tag, AAD component, view byte, challenge, verdict code, and HMAC in separate
tests and require rejection.

Run:

```bash
python3 -m unittest tools.tokenserver.test_interaction_relay_crypto -v
python3 test/test_agent_status_body_capacity.py
```

Expected: all crypto/tamper tests pass and the panel-view budget remains under
640 bytes.

- [ ] **Step 5: Wire and commit the protocol fixture**

Add the test module to `test/run.sh`, then commit only:

```bash
git add test-vectors/interaction-relay-v1.json \
  tools/tokenserver/interaction_relay_crypto.py \
  tools/tokenserver/test_interaction_relay_crypto.py \
  requirements-interaction-relay.txt test/run.sh
git commit -m "feat: pin encrypted interaction relay protocol"
```

## Task 2: Scaffold the typed user-owned Worker

**Files:**
- Create: `tools/interaction-relay/package.json`
- Create: `tools/interaction-relay/package-lock.json`
- Create: `tools/interaction-relay/wrangler.jsonc`
- Create: `tools/interaction-relay/tsconfig.json`
- Create: `tools/interaction-relay/vitest.config.ts`
- Create: `tools/interaction-relay/.gitignore`
- Generate: `tools/interaction-relay/worker-configuration.d.ts`
- Create: `tools/interaction-relay/src/index.ts`
- Create: `tools/interaction-relay/src/mailbox.ts`
- Create: `tools/interaction-relay/src/envelope.ts`
- Create: `tools/interaction-relay/test/config.test.ts`

- [ ] **Step 1: Write the failing configuration test**

Require Worker name `vibepulse-interaction-relay`, entry
`src/index.ts`, compatibility date `2026-08-19`, `nodejs_compat`, enabled
observability, binding `INTERACTION_MAILBOX`, class `InteractionMailbox`, and
migration `{ "tag": "v1", "new_sqlite_classes": ["InteractionMailbox"] }`.
Require no literal `MAC_TOKEN` or `PANEL_TOKEN` values and no KV binding.

- [ ] **Step 2: Create the pinned package and config**

Use exact development dependencies:

```json
{
  "wrangler": "4.124.0",
  "vitest": "4.1.11",
  "@cloudflare/vitest-pool-workers": "0.22.0",
  "typescript": "7.0.2"
}
```

Add scripts `types`, `types:check`, `typecheck`, `test`, `deploy:dry`, and
`deploy`. Configure Vitest with `cloudflareTest({wrangler:{configPath:
"./wrangler.jsonc"}})`. Ignore only `node_modules`, `.wrangler`, `.dev.vars`,
and generated test output; do not ignore the lockfile or generated bindings.

- [ ] **Step 3: Add compiling empty entry points and generated types**

Export `InteractionMailbox extends DurableObject<Env>` and a default
`ExportedHandler<Env>` returning 404. Generate the `Env` type with Wrangler;
do not hand-write it. The class constructor may initialize only schema inside
`ctx.blockConcurrencyWhile()`.

Run:

```bash
cd tools/interaction-relay
npm ci
npx wrangler types
npx tsc --noEmit
npx vitest run test/config.test.ts
npx wrangler deploy --dry-run
```

Expected: typecheck, config test, and dry run pass.

- [ ] **Step 4: Commit the isolated Worker skeleton**

```bash
git add tools/interaction-relay
git commit -m "build: scaffold encrypted interaction worker"
```

## Task 3: Implement atomic mailbox semantics in the Durable Object

**Files:**
- Modify: `tools/interaction-relay/src/mailbox.ts`
- Create: `tools/interaction-relay/test/mailbox.test.ts`

- [ ] **Step 1: Write failing direct-RPC tests**

Using `env.INTERACTION_MAILBOX.getByName("mailbox-test")`,
`runInDurableObject`, `evictDurableObject`, and `runDurableObjectAlarm`, test:

- create and exact idempotent retry return `created`/`existing`;
- same request ID with different envelope returns `conflict`;
- ninth live request returns `full`;
- `nextRequest` is oldest-first and excludes expired records;
- a verdict requires a live request;
- exact verdict retry succeeds and a conflicting verdict returns `conflict`;
- delete removes request plus verdict in one transaction;
- state survives object eviction; and
- the alarm removes expired rows and schedules the next earliest expiry.

- [ ] **Step 2: Run the focused test and verify empty behavior fails**

Run: `cd tools/interaction-relay && npx vitest run test/mailbox.test.ts`

Expected: failures naming missing RPC methods.

- [ ] **Step 3: Implement one SQLite table and five RPC methods**

Create table `requests` with columns `request_id TEXT PRIMARY KEY`,
`request_envelope TEXT NOT NULL`, `request_hash TEXT NOT NULL`,
`created_at_ms INTEGER NOT NULL`, `expires_at_ms INTEGER NOT NULL`,
`verdict_envelope TEXT`, `verdict_hash TEXT`, and `verdict_at_ms INTEGER`;
index `(expires_at_ms, created_at_ms)`.

Implement typed RPC methods:

```typescript
putRequest(requestId: string, envelope: string, hash: string, nowMs: number)
nextRequest(nowMs: number)
putVerdict(requestId: string, envelope: string, hash: string, nowMs: number)
listVerdicts(nowMs: number)
deleteRequest(requestId: string, nowMs: number)
```

Each method first deletes expired rows. Use
`this.ctx.storage.transactionSync()` for read-modify-write and related deletes;
do not use `BEGIN`. The server sets `expires_at_ms = first receipt + 120000`;
client time never extends it. Store and compare the exact outer-envelope UTF-8
string plus SHA-256. After each mutation, schedule one alarm for the earliest
remaining expiry; `alarm()` performs idempotent cleanup and reschedules.

- [ ] **Step 4: Run concurrency, eviction, and alarm tests**

Run:

```bash
cd tools/interaction-relay
npx vitest run test/mailbox.test.ts
npx tsc --noEmit
```

Expected: all mailbox tests pass without `blockConcurrencyWhile()` in RPC
methods and without external I/O inside the object.

- [ ] **Step 5: Commit the state authority**

```bash
git add tools/interaction-relay/src/mailbox.ts \
  tools/interaction-relay/test/mailbox.test.ts
git commit -m "feat: coordinate one-time relay decisions"
```

## Task 4: Add the bounded role-separated HTTP API

**Files:**
- Modify: `tools/interaction-relay/src/envelope.ts`
- Modify: `tools/interaction-relay/src/index.ts`
- Create: `tools/interaction-relay/test/http.test.ts`

- [ ] **Step 1: Write failing HTTP tests for every route and role**

Drive the Worker through `SELF.fetch`. Test exact methods/routes from the
approved design, correct Mac/panel role, wrong role, missing/malformed bearer,
cross-mailbox access, wrong content type, extra JSON fields, request ID/path
injection, `Content-Length` above 4096, chunked body crossing 4096, invalid
base64url, wrong nonce/ciphertext sizes, 404/405/409/413 responses, 204 empty
poll, and `Cache-Control: no-store` on every response. Assert no
`Access-Control-Allow-Origin` header is emitted.

- [ ] **Step 2: Run and verify the router tests fail**

Run: `cd tools/interaction-relay && npx vitest run test/http.test.ts`

Expected: routes return 404 and validation/auth assertions fail.

- [ ] **Step 3: Implement bounded reading, validation, and authentication**

Implement a streaming reader that cancels and returns 413 as soon as more
than 4096 bytes have been read, even without `Content-Length`. Accept only
`application/json`. Outer request/verdict bodies contain exactly `v`, `nonce`,
and `ciphertext`; `v` must be 1, nonce must decode to 12 bytes, and decoded
ciphertext-plus-tag must match the fixed 2064-byte request or 1040-byte verdict
size. The Worker never decrypts.

Hash supplied and configured bearer strings to fixed SHA-256 buffers and use
`crypto.subtle.timingSafeEqual`. `MAC_TOKEN` may PUT/read verdicts/DELETE;
`PANEL_TOKEN` may read requests/POST verdicts. `MAILBOX_ID` is a non-secret
narrow identifier and must equal the route mailbox. Return generic 404 for
mailbox/auth mismatch and never log tokens, authorization headers, envelopes,
request IDs, or mailbox IDs.

- [ ] **Step 4: Route to the mailbox with awaited RPC only**

Use `env.INTERACTION_MAILBOX.getByName(configuredMailbox)` and await every RPC.
Map exact retry to 200, first create to 201, empty read to 204, conflicts to
409, full to 429, and validation errors to 400/413/415. Use structured logs
with only event name, route kind, status, and duration.

Run:

```bash
cd tools/interaction-relay
npx vitest run
npx wrangler types --check
npx tsc --noEmit
npx wrangler deploy --dry-run
```

Expected: all Worker tests and static gates pass.

- [ ] **Step 5: Commit the opaque mailbox API**

```bash
git add tools/interaction-relay/src tools/interaction-relay/test \
  tools/interaction-relay/worker-configuration.d.ts
git commit -m "feat: expose bounded encrypted mailbox routes"
```

## Task 5: Integrate a background relay adapter with the live store

**Files:**
- Create: `tools/tokenserver/interaction_relay.py`
- Create: `tools/tokenserver/test_interaction_relay.py`
- Modify: `tools/tokenserver/interactions.py`
- Modify: `tools/tokenserver/test_interactions.py`

- [ ] **Step 1: Write failing store-listener and adapter tests**

Use injected clock, random source, HTTP transport, and sleeper. Prove:

- parking emits an immutable publish job only after the store lock is free;
- the job contains only request ID, random challenge, exact bounded view bytes,
  digest, expiry, provider, and approval flag;
- no raw hook, session ID, transcript, or unbounded command enters the job;
- the publish queue is capped at 8 and never blocks the hook/UI path;
- polling is idle with no relay-backed pending item;
- valid verdict resolves once; tampered, wrong-key, expired, unknown, duplicate,
  conflicting, and `approve`-when-disallowed verdicts resolve nothing;
- direct answer, timeout, dead hook, and panic enqueue remote deletion; and
- relay outage never extends `await_result()` or suppresses computer fallback.

- [ ] **Step 2: Run and verify missing listener/adapter failures**

Run:

```bash
python3 -m unittest tools.tokenserver.test_interaction_relay \
  tools.tokenserver.test_interactions -v
```

Expected: imports and listener methods fail.

- [ ] **Step 3: Add immutable relay jobs outside the store lock**

Extend each pending entry with a 32-byte challenge, exact `view_bytes`,
`view_sha256`, monotonic deadline, and `can_approve`. Add a narrow listener
interface `on_park(job)` and `on_remove(request_id, reason)`. Collect callbacks
while holding the lock, invoke them only after release, and catch listener
exceptions so the decision path remains authoritative.

Add `resolve_relay(result)` that performs all seven acceptance checks from the
design in one locked transition. `panic` first authenticates its displayed
anchor, then snapshots and denies only entries pending at that instant.

- [ ] **Step 4: Implement the bounded adapter and HTTP transport**

`InteractionRelay` owns one daemon thread, a `queue.Queue(maxsize=8)`, and a
stop event. PUT exact encrypted jobs, poll verdicts only while pending, locally
decrypt/verify before store resolution, and DELETE after resolve/remove.
Retry the same request envelope; never re-encrypt a retry with a new nonce.
Use connect/read timeouts, 0.5-to-5-second exponential backoff with injected
jitter, `Authorization: Bearer` headers, a 4096-byte response cap, and
`Cache-Control: no-store`. Redact URLs to origin plus route kind in logs.

- [ ] **Step 5: Run unit, dead-hook, and race tests**

Run:

```bash
python3 -m unittest tools.tokenserver.test_interaction_relay \
  tools.tokenserver.test_interactions -v
python3 test/test_agent_status_body_capacity.py
```

Expected: all pass under repeated concurrent direct/relay answers and forced
timeouts.

- [ ] **Step 6: Commit the host adapter**

```bash
git add tools/tokenserver/interaction_relay.py \
  tools/tokenserver/test_interaction_relay.py \
  tools/tokenserver/interactions.py tools/tokenserver/test_interactions.py
git commit -m "feat: relay live interactions outside store locks"
```

## Task 6: Add fail-closed host configuration and end-to-end integration

**Files:**
- Modify: `tools/tokenserver/vibepulse_config.py`
- Modify: `tools/tokenserver/test_vibepulse_config.py`
- Modify: `tools/tokenserver/tokenserver.py`
- Modify: `tools/tokenserver/test_tokenserver.py`
- Create: `tools/tokenserver/test_interaction_relay_integration.py`
- Modify: `tools/vibepulse_setup.py`
- Modify: `test/test_vibepulse_codex_plugin.py`
- Modify: `test/run.sh`

- [ ] **Step 1: Write failing independent-switch and dependency tests**

Require saved fields `interaction_relay=false`, `interaction_relay_url=null`,
and `interaction_mailbox=null`. Require `--interaction-relay URL` to fail
closed unless one provider, detail, valid 64-hex device key, mailbox, 32-byte
Mac bearer token, and optional `cryptography` package all exist. Confirm LAN,
numbers publisher, Claude, Codex, and GitHub still start when only this adapter
is disabled.

- [ ] **Step 2: Run and verify configuration tests fail**

Run:

```bash
python3 -m unittest tools.tokenserver.test_vibepulse_config \
  tools.tokenserver.test_tokenserver -v
```

Expected: missing fields, option, and diagnostic failures.

- [ ] **Step 3: Wire the adapter without importing crypto in default mode**

Parse relay options before conditionally importing `interaction_relay`. Read
the Mac token from `VIBEPULSE_INTERACTION_MAC_TOKEN` or
`~/.vibepulse-interaction-relay-token`; require file mode `0600` where the OS
supports it. Root diagnostics report `off`, `ready`, or a non-secret disabled
reason. Shutdown stops the adapter before the HTTP server. No plaintext
fallback is allowed.

- [ ] **Step 4: Extend the setup tool with an explicit relay wizard**

Add `relay install/status/doctor/disable/uninstall`. `install` clearly asks
for E2E cloud consent, generates mailbox and independent 256-bit bearer tokens
with `secrets.token_urlsafe(32)`, writes the Mac token file mode `0600`, updates
only the gitignored `secrets.h` relay block after making a backup, and invokes
the pinned local Wrangler package. Secrets reach Wrangler through a mode-0600
temporary JSON file passed to `wrangler secret bulk`, which is deleted in a
`finally` block. It must never print token values.

`disable` flips only the interaction-relay switch. `uninstall` offers to
delete the Worker and removes only relay config/token/macros; it preserves
device key, Wi-Fi slots, providers, numbers relay, GitHub, Codex plugin, repo,
and every unrelated Codex setting.

- [ ] **Step 5: Drive a full local fake hook → Worker → fake panel loop**

The integration test starts the tokenserver handler, local Worker runtime, and
a fake panel using the shared crypto module. It parks a Codex question,
retrieves ciphertext, proves the displayed view bytes equal the store bytes,
posts one signed encrypted recommendation, verifies exact MCP answer, then
requires the remote row to disappear. Repeat for Claude permission deny,
timeout, duplicate, wrong key, and direct-LAN-first cleanup.

Run:

```bash
python3 -m unittest tools.tokenserver.test_interaction_relay_integration -v
python3 test/test_vibepulse_codex_plugin.py -v
```

Expected: all flows pass and setup tests prove no secret output or unrelated
configuration deletion.

- [ ] **Step 6: Wire repository tests and commit host integration**

Add the three relay Python modules to `test/run.sh`, then commit:

```bash
git add tools/tokenserver/vibepulse_config.py \
  tools/tokenserver/test_vibepulse_config.py \
  tools/tokenserver/tokenserver.py tools/tokenserver/test_tokenserver.py \
  tools/tokenserver/test_interaction_relay_integration.py \
  tools/vibepulse_setup.py test/test_vibepulse_codex_plugin.py test/run.sh
git commit -m "feat: opt in tokenserver to encrypted relay"
```

## Task 7: Port protocol validation to bounded firmware C

**Files:**
- Create: `components/app_tokens/interaction_relay_crypto.h`
- Create: `components/app_tokens/interaction_relay_crypto.c`
- Create: `test/test_interaction_relay_crypto.c`
- Create: `test/test_interaction_relay_vectors.py`
- Modify: `test/run.sh`

- [ ] **Step 1: Write failing C vector and hostile-input tests**

Load the same committed inputs through generated compile definitions or a
small generated header in the test build. Assert byte-identical derived keys,
request decrypt, view digest, verdict HMAC, verdict encrypt, and base64url.
Test every boundary: 63/64/65 hex chars, bad hex, padded base64, 11/12/13-byte
nonce, short tag, over-cap envelope, bad length prefix, oversized view,
unknown key, bad AAD, bad challenge, and all verdict codes.

- [ ] **Step 2: Run the host gate and verify missing functions**

Run: `./test/run.sh`

Expected: C compile failure naming `interaction_relay_crypto.h`.

- [ ] **Step 3: Implement fixed-size Mbed TLS wrappers**

Use `mbedtls_hkdf`, `mbedtls_gcm_auth_decrypt`,
`mbedtls_gcm_crypt_and_tag`, SHA-256, and HMAC. Implement strict unpadded
base64url conversion around Mbed TLS base64 without heap allocation. All APIs
take caller buffers/capacities, zero key material and plaintext scratch on
every exit, return typed errors, and parse JSON only after tag, framing, and
digest verification. Production nonces/padding use `esp_fill_random` only on
target; host tests inject bytes.

- [ ] **Step 4: Cross-check Python and C from one fixture**

Run:

```bash
./test/run.sh
python3 test/test_interaction_relay_vectors.py
python3 -m unittest tools.tokenserver.test_interaction_relay_crypto -v
```

Expected: every pinned field matches in both implementations and all tamper
cases fail.

- [ ] **Step 5: Commit the firmware crypto boundary**

```bash
git add components/app_tokens/interaction_relay_crypto.h \
  components/app_tokens/interaction_relay_crypto.c \
  test/test_interaction_relay_crypto.c \
  test/test_interaction_relay_vectors.py test/run.sh
git commit -m "feat: verify relay envelopes on the panel"
```

## Task 8: Add source merge, suppression, routing, and shared TLS gate

**Files:**
- Create: `components/app_tokens/interaction_relay_policy.h`
- Create: `components/app_tokens/interaction_relay_policy.c`
- Create: `test/test_interaction_relay_policy.c`
- Modify: `components/app_tokens/agent_status.h`
- Modify: `components/app_tokens/agent_monitor.c`
- Modify: `components/app_tokens/needs_you_net.c`
- Modify: `components/torget_net/torget_http.h`
- Modify: `components/torget_net/torget_http.c`
- Modify: `components/torget_net/CMakeLists.txt`
- Modify: `test/run.sh`

- [ ] **Step 1: Write failing pure-policy tests**

Cover LAN-only, relay-only, mirrored same ID, unrelated IDs, oldest-expiry
selection, LAN preference, relay metadata preservation, eight answered IDs,
suppression until expiry, direct success, direct uncertain failure followed by
same relay envelope, hard direct rejection without retry, exact retry reuse,
backoff reset after Wi-Fi recovery, and panic anchored to the visible item.

- [ ] **Step 2: Run and verify the policy API is missing**

Run: `./test/run.sh`

Expected: C compile failures naming the new policy types/functions.

- [ ] **Step 3: Keep independent LAN and relay slots**

Add source enum, 32-byte challenge, digest, and relay-envelope state to the
pending interaction structure. `agent_monitor.c` owns one LAN slot and one
relay slot, merges through the pure policy, and still renders one existing
Needs You tree. Applying relay state must not call the full agent-status apply
path or clear Claude/Codex job rows.

Change the verdict callback to pass one copied decision context containing
provider, source, request ID, challenge, digest, approval flag, and immutable
retry envelope. The UI callback only queues; it performs no crypto or I/O.

- [ ] **Step 4: Add a shared Cloudflare network gate**

Expose `torget_cloud_io_acquire(timeout_ms)` and
`torget_cloud_io_release()` from `torget_http`. Back it with one FreeRTOS mutex
created before network tasks. Existing numbers/GitHub relay HTTPS and the new
interaction relay acquire it only around Cloudflare client open/perform/close.
LAN requests do not wait on it. Assert in source tests that no gate is acquired
under `torget_ui_lock` and all exits release it.

- [ ] **Step 5: Run policy and source-safety gates**

Run:

```bash
./test/run.sh
python3 test/test_lvgl_layer_safety.py
```

Expected: pure state tests pass, one LVGL tree remains, and network sources do
not call LVGL.

- [ ] **Step 6: Commit source-aware decision routing**

```bash
git add components/app_tokens/interaction_relay_policy.h \
  components/app_tokens/interaction_relay_policy.c \
  components/app_tokens/agent_status.h \
  components/app_tokens/agent_monitor.c \
  components/app_tokens/needs_you_net.c \
  components/torget_net/torget_http.h components/torget_net/torget_http.c \
  components/torget_net/CMakeLists.txt \
  test/test_interaction_relay_policy.c test/run.sh
git commit -m "feat: merge LAN and relay decisions safely"
```

## Task 9: Compile and run the opt-in panel relay client

**Files:**
- Create: `components/app_tokens/interaction_relay_net.h`
- Create: `components/app_tokens/interaction_relay_net.c`
- Modify: `components/app_tokens/app.c`
- Modify: `components/app_tokens/CMakeLists.txt`
- Modify: `main/Kconfig.projbuild`
- Modify: `secrets.h.example`
- Create: `test/test_interaction_relay_build.py`
- Create: `test/test_interaction_relay_net_source.py`
- Modify: `test/run.sh`

- [ ] **Step 1: Write failing default-off and build-wiring tests**

Require `CONFIG_TK_VIBEPULSE_INTERACTION_RELAY` default `n`. With it off,
require no relay task/source or Mbed TLS dependency in the component build.
With it on, require URL, mailbox, panel token, and 64-hex device key guards
with exact recovery text. Ensure every example macro is commented out and no
real URL/token is tracked.

- [ ] **Step 2: Run and verify the option/client is missing**

Run:

```bash
python3 test/test_interaction_relay_build.py
python3 test/test_interaction_relay_net_source.py
```

Expected: missing Kconfig, client, and guard assertions fail.

- [ ] **Step 3: Add conditional build wiring and configure-time guard**

Conditionally append crypto, policy, and net sources plus `mbedtls` and
`esp_hw_support` only when the Kconfig option is true. At configure time, read
only macro names/shapes from gitignored `secrets.h`; fail with:

```text
Encrypted interaction relay is enabled but incomplete.
Add URL, mailbox, panel token, and the 64-hex device key to secrets.h,
or run: python3 tools/vibepulse_setup.py relay doctor
To return to LAN-only: disable TK_VIBEPULSE_INTERACTION_RELAY in menuconfig.
```

- [ ] **Step 4: Implement one bounded poll/send task**

Wait for `torget_net_wait()`, then poll `requests/next` every 5 seconds with
bounded jitter/backoff. Reuse one HTTPS client per direction where ESP-IDF
allows; set CA bundle, bearer header, `Cache-Control: no-store`, and strict
4096-byte complete-body cap. Decrypt into fixed/PSRAM scratch, parse into the
relay slot, then take `torget_ui_lock` only for the final validated apply.

Verdicts use the immutable envelope created once when the tap is queued and
retry that exact body until HTTP success, local expiry, or source suppression.
Never log bearer, mailbox, full URL, ciphertext, question, project, command,
challenge, key, or HMAC. Expose redacted counters and last status for doctor
and hardware acceptance.

- [ ] **Step 5: Start only the explicitly enabled task**

Call `tokens_interaction_relay_net_start()` from `app.c` only under the Kconfig
option. The stub for disabled builds must be absent from the binary rather than
a dormant task. Preserve existing LAN and numbers tasks exactly.

Run:

```bash
./test/run.sh
. "$IDF_PATH/export.sh"
idf.py reconfigure build
```

Expected: default-off build succeeds without relay secrets; an isolated
temporary sdkconfig with the option on and missing secrets fails with the
recovery text; a configured build succeeds without changing the 256 KiB LVGL
pool.

- [ ] **Step 6: Commit the optional panel client**

```bash
git add components/app_tokens/interaction_relay_net.h \
  components/app_tokens/interaction_relay_net.c \
  components/app_tokens/app.c components/app_tokens/CMakeLists.txt \
  main/Kconfig.projbuild secrets.h.example \
  test/test_interaction_relay_build.py \
  test/test_interaction_relay_net_source.py test/run.sh
git commit -m "feat: poll encrypted decisions on any Wi-Fi"
```

## Task 10: Revise privacy boundaries and document simple opt-in setup

**Files:**
- Modify: `README.md`
- Modify: `docs/relay.md`
- Create: `docs/interaction-relay.md`
- Create: `tools/interaction-relay/README.md`
- Modify: `tools/tokenserver/README.md`
- Modify: `docs/agent-setup.md`
- Modify: `test/test_relay_boundary.py`
- Create: `test/test_interaction_relay_boundary.py`
- Create: `test/test_interaction_relay_docs.py`
- Modify: `test/run.sh`

- [ ] **Step 1: Write failing privacy and documentation gates**

Keep the numbers Worker/publisher allowlist exactly three numeric endpoints.
Change only its rationale from “activity can never use any cloud” to “this
numbers transport never carries activity.” Require the separate Worker to
contain only opaque envelope field names and forbid plaintext fields/routes:
`agent-status`, `hook`, `session`, `prompt`, `command`, `project`, `question`,
`title`, `subtitle`, and `answer`.

Require docs to name independent defaults, computer-on requirement, outbound
HTTPS guarantee limits, Cloudflare-visible metadata, exact plaintext allowed
before local encryption, fixed padding sizes, 120-second maximum retention,
rotate/revoke, disable/uninstall, costs/limits lookup, and self-hosting API.

- [ ] **Step 2: Run and verify old rationale/docs fail**

Run:

```bash
python3 test/test_relay_boundary.py
python3 test/test_interaction_relay_boundary.py
python3 test/test_interaction_relay_docs.py
```

Expected: missing scoped rationale and setup/privacy documentation failures.

- [ ] **Step 3: Document the plain-English product outcome**

Use one simple diagram:

```text
Claude/Codex ↔ tokenserver → encrypt → user's Worker → decrypt → panel
Claude/Codex ← tokenserver ← verify  ← user's Worker ← encrypt ← tap
```

Explain that panel and computer may be anywhere on ordinary internet Wi-Fi;
the computer must be awake and tokenserver running; no router, inbound port,
public Mac, VPN, or same-house LAN is required. Explain that Cloudflare sees
IP/timing/mailbox/fixed direction size but never plaintext content or verdict.
State that captive portals, offline networks, and blocked Worker domains are
not covered.

Document one recommended wizard path, a manual path, `status`, `doctor`,
`disable`, complete deletion, credential rotation, and updating. The wizard
must present separate toggles for Claude, Codex, numbers, encrypted
interactions, and GitHub; no selection implies another.

- [ ] **Step 4: Update help and test runner**

Keep `--publish` explicitly numbers-only. Describe `--interaction-relay` as
bounded E2E ciphertext. Add Worker tests with `npm ci && npm test` when Node is
available; CI must require Node rather than skip the security service.

- [ ] **Step 5: Run full static documentation and privacy gates**

Run:

```bash
./test/run.sh
cd tools/interaction-relay && npm ci && npm test && npm run typecheck
```

Expected: numbers privacy test, encrypted privacy test, setup/default tests,
Worker tests, and existing suites all pass.

- [ ] **Step 6: Commit the open-source contract**

```bash
git add README.md docs/relay.md docs/interaction-relay.md \
  tools/interaction-relay/README.md tools/tokenserver/README.md \
  docs/agent-setup.md test/test_relay_boundary.py \
  test/test_interaction_relay_boundary.py \
  test/test_interaction_relay_docs.py test/run.sh
git commit -m "docs: explain optional encrypted decisions"
```

## Task 11: Final regression, deployment, and ota_1 hardware acceptance

**Files:**
- Create after observation: `docs/superpowers/reviews/2026-08-19-vibepulse-encrypted-relay-acceptance.md`

- [ ] **Step 1: Review complete scope before any deployment**

Run:

```bash
git diff --check 6359dcf..HEAD
git diff --name-status 6359dcf..HEAD
git log --oneline --reverse 6359dcf..HEAD
git status --short
```

Expected: no secret, sdkconfig, `.wrangler`, simulator probe, swipe change,
numbers-relay activity route, or rollback-partition change is committed.

- [ ] **Step 2: Run all local and build gates from a clean clone/worktree**

Run:

```bash
python3 -m pip install -r requirements-interaction-relay.txt
./test/run.sh
cd tools/interaction-relay
npm ci
npm run types:check
npm run typecheck
npm test
npm run deploy:dry
cd ../..
cmake -S sim -B sim/build -G Ninja
ninja -C sim/build
./sim/build/torget-sim --vibepulse-needs-you-qa
python3 test/test_vibepulse_visual_landmarks.py
. "$IDF_PATH/export.sh"
idf.py build
```

Expected: every suite passes; build reports the guarded 256 KiB LVGL pool and
no new allocation/DMA warning.

- [ ] **Step 3: Deploy a temporary user-owned Worker only with approval**

Use the setup wizard, review generated secrets without printing them, deploy,
run `doctor`, and test from two network paths. Confirm wrong role/token,
cross-mailbox, oversize, replay, conflict, and expired state are rejected.
Inspect logs to prove content, identifiers, credentials, and envelopes are not
logged. Delete temporary remote state after the test unless the user chooses
to keep the deployment.

- [ ] **Step 4: Obtain explicit permission before touching the panel**

Confirm USB port, target build, and currently running partition. Write only the
application image to `ota_1`; never erase flash, repartition, write `ota_0`, or
select `ota_0` as the test image.

- [ ] **Step 5: Verify real isolated-Wi-Fi behavior and stability**

Make direct Mac/panel LAN communication unavailable while retaining outbound
internet. Verify Claude and Codex question/permission approve, deny, leave,
timeout, panic, direct/relay duplicate, Mac restart, panel reboot, relay
outage, wrong key, and Wi-Fi reconnect. Verify rotation, data arrival, OTA
takeover, transparent Codex logo, top-right Wi-Fi icon, and long labels.

Soak repeated TLS handshakes and glyph redraws beyond the old 45-second wedge
window. Require free internal heap at least 32 KiB and largest DMA block at
least 23,040 bytes during TLS plus worst-case redraw, with no LVGL assert, lock
flood, watchdog, incomplete-body apply, or frozen display.

- [ ] **Step 6: Record only observed evidence and commit it**

Record commit, Worker version, firmware, port, `ota_1`, networks, test matrix,
heap/DMA minima, logs reviewed, failures exercised, and remaining limitations.

```bash
git add docs/superpowers/reviews/2026-08-19-vibepulse-encrypted-relay-acceptance.md
git commit -m "docs: record encrypted relay acceptance"
```

## Final acceptance checklist

- [ ] Fresh clone and existing update remain LAN-only with no optional runtime
      or cloud requirement.
- [ ] Claude, Codex, numbers relay, encrypted interactions, and GitHub switch
      independently.
- [ ] Panel and computer need only outbound HTTPS and may be on unrelated
      ordinary Wi-Fi; computer must be awake with tokenserver running.
- [ ] Cloudflare receives fixed-size opaque envelopes only; no plaintext
      activity producer or route exists.
- [ ] Provider, live request, random challenge, exact displayed bytes/digest,
      verdict, direction, and one-time state are cryptographically bound.
- [ ] Timeout, outage, restart, wrong key, malformed data, and replay fail back
      to the computer and never approve by silence.
- [ ] LAN direct and the existing three numbers endpoints remain compatible.
- [ ] One LVGL Needs You tree remains, the 256 KiB pool guard remains, and TLS
      work does not regress heap/DMA/display stability.
- [ ] No secret, generated sdkconfig, `.wrangler` state, throwaway simulator
      probe, or unrelated user file is committed.
- [ ] `ota_0` is untouched.
