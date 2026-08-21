# VibePulse Encrypted Agent-Status Relay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep Claude/Codex live status current when the panel cannot reach the Mac over the LAN, using a separate default-off end-to-end encrypted latest-value relay.

**Architecture:** Reuse the user-owned interaction-relay origin, role tokens, mailbox, and device key while adding a direction-separated status AEAD key and a single short-lived status slot. The host encrypts the bounded public agent snapshot; the panel authenticates, validates freshness, and applies it only when LAN status has been unavailable for five seconds. Pending interactions remain on their existing independent merge path.

**Tech Stack:** Python 3.11+, `cryptography`, TypeScript Cloudflare Worker + SQLite Durable Object, C11, Mbed TLS, ESP-IDF 5.5, cJSON, unittest/Vitest/host C tests.

---

### Task 1: Define cross-language status crypto

**Files:**
- Modify: `tools/tokenserver/interaction_relay_crypto.py`
- Modify: `tools/tokenserver/test_interaction_relay_crypto.py`
- Modify: `components/app_tokens/interaction_relay_crypto.h`
- Modify: `components/app_tokens/interaction_relay_crypto.c`
- Modify: `test/test_interaction_relay_crypto.c`
- Create: `test-vectors/agent-status-relay-v1.json`

- [ ] **Step 1: Write Python RED tests**

Add exact tests for:

```python
keys.status_aead
encode_status(keys, MAILBOX, publication_id, expires_at, status_bytes,
              nonce=b"\x01" * 12, padding=lambda n: b"\xa5" * n)
decode_status(keys, MAILBOX, envelope)
```

Require a fixed `STATUS_FRAME_BYTES == 2816`, canonical outer JSON, a maximum 2560-byte compact status, fresh nonce, digest binding, strict publication/expiry integers, and rejection of tamper, wrong key/mailbox, altered length/digest/magic, noncanonical envelope, oversize, and invalid padding source.

- [ ] **Step 2: Run Python RED**

```sh
./.venv/bin/python -m unittest \
  tools.tokenserver.test_interaction_relay_crypto.StatusRelayCryptoTests -v
```

Expected: missing `status_aead`, `encode_status`, and `decode_status` failures.

- [ ] **Step 3: Implement the host frame**

Extend `RelayKeys` with `status_aead`, derived with:

```python
status_aead=derive(b"mac-to-panel-status-aead")
```

Implement a binary plaintext frame with exact big-endian fields:

```text
"VPS1" | publication_id:u64 | expires_at:u32 | length:u16 |
sha256(status):32 | status | random authenticated padding
```

Bind it with AAD:

```python
b"vibepulse-ir/v1|" + mailbox.encode("ascii") + b"|status"
```

Use the existing strict outer envelope helpers and convert every crypto/format exception to `ValueError("invalid status envelope")`.

- [ ] **Step 4: Generate and freeze the shared vector**

Write exact device key, mailbox, nonce, padding byte, publication ID, expiry, canonical status JSON, derived status key, and final envelope to `test-vectors/agent-status-relay-v1.json`.

- [ ] **Step 5: Write C RED tests and implement the C decoder**

Expose:

```c
#define TK_IR_STATUS_FRAME_BYTES 2816u
#define TK_IR_MAX_STATUS_BYTES 2560u

typedef struct {
  uint8_t status_aead[TK_IR_KEY_BYTES];
  /* existing request/verdict keys remain */
} tk_ir_keys_t;

typedef struct {
  uint64_t publication_id;
  uint32_t expires_at;
  uint8_t status[TK_IR_MAX_STATUS_BYTES];
  size_t status_len;
} tk_ir_status_t;

tk_ir_error_t tk_ir_decode_status(...);
```

The C test consumes the exact JSON vector, proves byte-identical derivation/decryption, and repeats every wrong-key/tamper/bounds failure. Wipe output/work on every failure.

- [ ] **Step 6: Run GREEN crypto tests**

```sh
./.venv/bin/python -m unittest \
  tools.tokenserver.test_interaction_relay_crypto -v
./test/run.sh --group interaction-relay-crypto
```

Expected: Python and C vectors pass with ASan/UBSan where the runner provides them.

- [ ] **Step 7: Commit**

```sh
git add tools/tokenserver/interaction_relay_crypto.py \
  tools/tokenserver/test_interaction_relay_crypto.py \
  components/app_tokens/interaction_relay_crypto.h \
  components/app_tokens/interaction_relay_crypto.c \
  test/test_interaction_relay_crypto.c test-vectors/agent-status-relay-v1.json
git commit -m "feat: add encrypted agent status frames"
```

### Task 2: Add the Worker's latest-value status slot

**Files:**
- Modify: `tools/interaction-relay/src/envelope.ts`
- Modify: `tools/interaction-relay/src/index.ts`
- Modify: `tools/interaction-relay/src/mailbox.ts`
- Modify: `tools/interaction-relay/test/http.test.ts`
- Modify: `tools/interaction-relay/test/mailbox.test.ts`

- [ ] **Step 1: Write Worker RED tests**

Require:

```text
PUT /v1/mailboxes/{box}/status   Mac token only
GET /v1/mailboxes/{box}/status   panel token only
```

Test exact ciphertext size, content type, no-store, wrong/missing role token as 404, method allowlist, duplicate headers, body overflow/short read, latest-write-wins, 20-second expiry, alarm cleanup, and no interaction-request/verdict regression.

- [ ] **Step 2: Run RED**

```sh
cd tools/interaction-relay && npm test -- --runInBand
```

Expected: status routes and mailbox methods are missing.

- [ ] **Step 3: Implement the status slot**

Add one-row SQL table keyed by literal slot `1`:

```sql
CREATE TABLE IF NOT EXISTS agent_status (
  slot INTEGER PRIMARY KEY CHECK (slot = 1),
  envelope TEXT NOT NULL,
  envelope_hash TEXT NOT NULL,
  stored_at_ms INTEGER NOT NULL,
  expires_at_ms INTEGER NOT NULL
)
```

`putStatus` atomically replaces the row with `expires_at_ms = now + 20000`.
`getStatus` deletes expiry first and returns the envelope plus stored/expiry
timestamps. Extend alarm scheduling to the minimum of request and status
expiry. Never log envelope content.

- [ ] **Step 4: Run GREEN Worker tests**

```sh
cd tools/interaction-relay && npm test
```

Expected: all status and existing request/verdict suites pass.

- [ ] **Step 5: Commit**

```sh
git add tools/interaction-relay/src tools/interaction-relay/test
git commit -m "feat: add encrypted status mailbox slot"
```

### Task 3: Publish status from the tokenserver behind an independent switch

**Files:**
- Modify: `tools/tokenserver/vibepulse_config.py`
- Modify: `tools/tokenserver/tokenserver.py`
- Modify: `tools/tokenserver/interaction_relay.py`
- Modify: `tools/tokenserver/test_vibepulse_config.py`
- Modify: `tools/tokenserver/test_interaction_relay.py`
- Modify: `tools/tokenserver/test_tokenserver.py`
- Modify: `tools/vibepulse_setup.py`
- Modify: `test/test_vibepulse_codex_plugin.py`

- [ ] **Step 1: Write config/setup/publisher RED tests**

Pin strict `agent_status_relay: bool = False`, CLI pairs
`--agent-status-relay/--no-agent-status-relay`, saved precedence, root
diagnostics, explicit consent, and independent disable behavior.

For the publisher, inject `status_source=lambda: snapshot` and require:

```python
InteractionRelay(..., publish_interactions=False,
                 publish_agent_status=True,
                 status_source=status_source)
```

It publishes immediately and at most every two seconds, uses a monotonically
increasing Unix-millisecond publication ID, sets inner expiry to wall time +
15 seconds, reuses exact ciphertext only for the same retry, never includes a
`pending` key, and logs only content-free counters.

- [ ] **Step 2: Run RED**

```sh
./.venv/bin/python -m unittest \
  tools.tokenserver.test_vibepulse_config \
  tools.tokenserver.test_interaction_relay \
  tools.tokenserver.test_tokenserver \
  test.test_vibepulse_codex_plugin -v
```

Expected: the independent switch and status publisher paths are absent.

- [ ] **Step 3: Implement strict host configuration**

Add `agent_status_relay` to `_FIELDS`, `VibePulseConfig`, validation, merge,
root diagnostics, and setup status/doctor. Start the relay adapter if either
interaction or status relay is enabled. Allow `store=None` when only status is
enabled; attach the interaction listener only when a store exists.

Add explicit setup commands:

```text
vibepulse_setup.py relay enable-status --yes-e2e-cloud
vibepulse_setup.py relay disable-status
```

`enable-status` requires valid existing URL/mailbox/private Mac token/panel
block/device key, exact consent, and a successful Worker ownership probe.
`disable-status` changes only the saved boolean and retains credentials.

- [ ] **Step 4: Implement bounded publishing**

Compact JSON with `ensure_ascii=True`, sorted keys, and comma/colon separators.
Reject values above 2560 bytes. Publish to `/status` with the Mac token and the
same strict HTTPS/no-proxy/no-redirect/bounded response rules. Maintain a
separate retry/backoff state so status failure cannot delay a verdict.

- [ ] **Step 5: Run GREEN host tests**

Run the RED command again. Expected: all pass, including off-by-default,
switch independence, malformed config, timeout/retry, and privacy-boundary
tests.

- [ ] **Step 6: Commit**

```sh
git add tools/tokenserver tools/vibepulse_setup.py \
  test/test_vibepulse_codex_plugin.py
git commit -m "feat: publish optional encrypted agent status"
```

### Task 4: Add firmware status decoding and source precedence

**Files:**
- Create: `components/app_tokens/agent_status_source_policy.h`
- Create: `components/app_tokens/agent_status_source_policy.c`
- Modify: `components/app_tokens/agent_net.c`
- Modify: `components/app_tokens/interaction_relay_net.c`
- Modify: `components/app_tokens/interaction_relay_net.h`
- Modify: `components/app_tokens/agent_monitor.c`
- Modify: `components/app_tokens/agent_monitor.h`
- Modify: `components/app_tokens/app.c`
- Modify: `components/app_tokens/app_tokens.h`
- Modify: `components/app_tokens/CMakeLists.txt`
- Modify: `main/Kconfig.projbuild`
- Modify: `test/test_agent_net_wiring.py`
- Create: `test/test_agent_status_source_policy.c`
- Modify: `test/run.sh`

- [ ] **Step 1: Write source-policy and wiring RED tests**

Define the pure contract:

```c
#define TK_AGENT_LAN_FRESH_MS 5000u
#define TK_AGENT_RELAY_STALE_MS 20000u

void tk_agent_source_note_lan(tk_agent_source_policy *, uint64_t now_ms);
bool tk_agent_source_allow_relay(const tk_agent_source_policy *, uint64_t now_ms);
void tk_agent_source_note_relay(tk_agent_source_policy *, uint64_t now_ms);
bool tk_agent_source_should_clear_relay(tk_agent_source_policy *, uint64_t now_ms);
```

Test boot/no-LAN allowance, fresh-LAN denial, exact five-second boundary,
relay note, exact 20-second one-shot clear, LAN recovery, monotonic saturation,
and no unsigned wrap.

Wiring tests require separate Kconfig default `n`, compilation when either
relay option is enabled, no relay source in simulator, no LVGL from the network
task, and preservation of the pending-interaction path.

- [ ] **Step 2: Run RED host C/wiring tests**

```sh
./test/run.sh --group agent-status-source
./.venv/bin/python test/test_agent_net_wiring.py
```

Expected: policy files/symbols and status-relay Kconfig are missing.

- [ ] **Step 3: Implement source precedence**

On every valid LAN parse, note LAN before applying. The relay applies only
when `allow_relay` is true. Add a monitor entry point that replaces only
`seq`, `claude`, and `codex`, then reselects the already independent pending
slot:

```c
void tk_agent_monitor_apply_status_relay(
    const tk_agent_snapshot *snapshot, int64_t now_us);
```

An empty relay clear uses zero provider rows and never mutates the pending
policy. Factor shared render/keep-awake code rather than duplicating behavior.

- [ ] **Step 4: Implement bounded status polling**

Under `CONFIG_TK_VIBEPULSE_AGENT_STATUS_RELAY`, poll `/status` every five
seconds with the panel token. Strictly parse the wrapper, decode the fixed
frame, verify inner and Worker expiry against wall time, require a publication
ID greater than the last accepted ID, parse status bytes through
`tk_agent_status_parse`, and reject any `pending` key in the decrypted status
schema. Apply under `torget_ui_lock` only after all checks.

If the status slot is absent/expired for 20 seconds, LAN is not fresh, and
relay currently owns the agent rows, apply one empty snapshot and arm the
one-shot clear. Requests/verdicts continue on their existing cadence and
failure state.

- [ ] **Step 5: Run GREEN C/wiring tests**

```sh
./test/run.sh --group agent-status-source
./test/run.sh --group interaction-relay-crypto
./.venv/bin/python test/test_agent_net_wiring.py
./.venv/bin/python test/test_relay_boundary.py
```

Expected: all pass; numbers relay remains activity-free.

- [ ] **Step 6: Commit**

```sh
git add components/app_tokens main/Kconfig.projbuild \
  test/test_agent_status_source_policy.c test/test_agent_net_wiring.py \
  test/test_relay_boundary.py test/run.sh
git commit -m "feat: consume encrypted agent status on panel"
```

### Task 5: Document, verify, and prepare opt-in rollout

**Files:**
- Modify: `secrets.h.example`
- Modify: `README.md`
- Modify: `docs/interaction-relay.md`
- Modify: `docs/observability.md`
- Modify: `docs/lessons.md`
- Modify: `tools/interaction-relay/README.md`
- Modify: `test/test_relay_boundary.py`
- Modify: `test/test_agent_status_body_capacity.py`

- [ ] **Step 1: Add RED documentation/boundary assertions**

Require independent rows for numbers, interactions, and live agent status;
default off in host and firmware; exact encrypted content/metadata/TTL;
disable/doctor commands; LAN precedence; computer-on requirement; and no
plaintext agent status in `tools/relay/worker.js` or its publisher.

- [ ] **Step 2: Update user documentation**

Explain in plain English that enabling live status lets the panel follow the
computer between ordinary internet Wi-Fi networks, while the computer and
tokenserver still need to be running. Clearly state that project basenames and
activity are inside E2E ciphertext, Cloudflare still sees timing/IP/mailbox,
and the switch is off unless explicitly chosen.

- [ ] **Step 3: Run focused and full verification**

```sh
./.venv/bin/python test/test_relay_boundary.py
./.venv/bin/python test/test_agent_status_body_capacity.py
cd tools/interaction-relay && npm test
cd ../..
PYTHON_BIN="$PWD/.venv/bin/python" ./test/run.sh
cmake --build sim/build -j4
PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python \
  test/test_vibepulse_visual_landmarks.py -v
```

Expected: all tests pass. Then build ESP32-S3 with the effective 256 KiB LVGL
pool and both explicitly selected relay options. Do not flash or deploy yet.

- [ ] **Step 4: Commit documentation**

```sh
git add README.md secrets.h.example docs tools/interaction-relay/README.md \
  test/test_relay_boundary.py test/test_agent_status_body_capacity.py
git commit -m "docs: explain encrypted live status relay"
```

- [ ] **Step 5: Request rollout authority**

Present exact test/build results, Worker diff, local ignored-config diff, and
firmware image hash. Ask separately before updating the user's Worker and
before writing `ota_1`. Never read, erase, switch, or write `ota_0`.

