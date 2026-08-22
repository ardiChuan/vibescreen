# VibePulse List-Free Numbers Relay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep quota, Max Tracker, and GitHub data fresh on any Wi-Fi by removing every `KV.list()` call from the numbers Worker's request path while preserving multi-publisher merging and the numbers-only privacy boundary.

**Architecture:** Retain the existing per-publisher endpoint documents and add one bounded publisher-index KV record. POST registers a sanitized publisher only when absent and then stores its document; GET reads the index and only the known per-publisher keys directly. This avoids Cloudflare's 1,000-list-request daily free limit without a read/merge/write race between multiple computers.

**Tech Stack:** Cloudflare Workers JavaScript, Workers KV bindings, Node.js `node:test`, Python boundary tests, Wrangler 4.

---

## File map

- Modify `tools/relay/test.mjs`: add an in-memory KV contract harness and full Worker request tests.
- Modify `tools/relay/worker.js`: replace prefix listing with a bounded fixed publisher index and direct reads.
- Modify `tools/relay/README.md`: document the list-free storage/read budget and verification.
- Modify `docs/relay.md`: explain the direct-read index and all-Wi-Fi behavior.
- Modify `docs/lessons.md`: record the independent KV list-request budget failure and guard.
- Use, but do not modify, `test/test_relay_boundary.py`: prove the numbers-only boundary remains intact.
- Use, but do not modify, `tools/tokenserver/test_publisher.py`: preserve the two-publisher write ceiling and retry behavior.

### Task 1: Reproduce the exhausted-list failure at the Worker boundary

**Files:**
- Modify: `tools/relay/test.mjs`
- Test: `tools/relay/test.mjs`

- [ ] **Step 1: Record the current baseline**

Run:

```sh
node --test tools/relay/test.mjs
```

Expected: the existing six pure merge tests pass.

- [ ] **Step 2: Add an in-memory KV harness and request helper**

Add the default Worker import and these helpers near the top of
`tools/relay/test.mjs`:

```js
import worker, { mergeTokens, newestBody } from "./worker.js";

const SECRET = "s".repeat(64);
const ROOT = `https://relay.example/u/${SECRET}`;

function memoryKv(initial = {}) {
  const values = new Map(Object.entries(initial));
  const calls = { get: [], put: [], list: 0 };
  return {
    values,
    calls,
    async get(key) {
      calls.get.push(key);
      return values.get(key) ?? null;
    },
    async put(key, value) {
      calls.put.push(key);
      values.set(key, value);
    },
    async list() {
      calls.list += 1;
      throw new Error("KV.list must never be called");
    },
  };
}

async function relayFetch(kv, method, endpoint, body, publisher = "mac") {
  const headers = { "X-VibePulse-Publisher": publisher };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  return worker.fetch(new Request(ROOT + endpoint, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  }), { RELAY_SECRET: SECRET, VIBEPULSE: kv });
}
```

Replace the old named import rather than adding a duplicate import.

- [ ] **Step 3: Add the failing no-list contract**

Add tests that POST and GET each endpoint, then poll repeatedly:

```js
test("first publication is directly readable without KV.list", async () => {
  for (const [endpoint, body] of [
    ["/api/tokens", { weekPct: 5, weekObservedAt: 100 }],
    ["/api/max-tracker", { peak: 7 }],
    ["/api/github", { stars: 11 }],
  ]) {
    const kv = memoryKv();
    assert.equal((await relayFetch(kv, "POST", endpoint, body)).status, 200);
    const response = await relayFetch(kv, "GET", endpoint);
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), body);
    assert.equal(kv.calls.list, 0);
  }
});

test("repeated panel polling performs zero list operations", async () => {
  const kv = memoryKv();
  await relayFetch(kv, "POST", "/api/tokens",
                   { weekPct: 5, weekObservedAt: 100 });
  for (let i = 0; i < 100; i += 1)
    assert.equal((await relayFetch(kv, "GET", "/api/tokens")).status, 200);
  assert.equal(kv.calls.list, 0);
});
```

- [ ] **Step 4: Run the focused test and verify RED**

Run:

```sh
node --test tools/relay/test.mjs
```

Expected: both new handler tests fail with `KV.list must never be called`,
proving the production GET path reproduces the live Cloudflare failure.

### Task 2: Implement bounded publisher registration and direct reads

**Files:**
- Modify: `tools/relay/worker.js`
- Modify: `tools/relay/test.mjs`
- Test: `tools/relay/test.mjs`

- [ ] **Step 1: Add publisher-index edge-case tests while production is still RED**

Extend `tools/relay/test.mjs` with tests that prove:

```js
test("known publishers do not rewrite the index", async () => {
  const kv = memoryKv();
  await relayFetch(kv, "POST", "/api/tokens", { weekPct: 5 }, "mac");
  const indexWrites = kv.calls.put.length;
  await relayFetch(kv, "POST", "/api/tokens", { weekPct: 6 }, "mac");
  assert.equal(kv.calls.put.length, indexWrites + 1,
               "only the endpoint document may be rewritten");
});

test("a ninth publisher is rejected without displacing the first eight", async () => {
  const kv = memoryKv();
  for (let i = 0; i < 8; i += 1)
    assert.equal((await relayFetch(kv, "POST", "/api/tokens",
      { weekPct: i }, `machine-${i}`)).status, 200);
  assert.equal((await relayFetch(kv, "POST", "/api/tokens",
    { weekPct: 9 }, "machine-8")).status, 409);
  const response = await relayFetch(kv, "GET", "/api/tokens");
  assert.equal(response.status, 200);
  assert.notEqual((await response.json()).weekPct, 9);
});

test("two publishers still merge each quota pool by observation time", async () => {
  const kv = memoryKv();
  await relayFetch(kv, "POST", "/api/tokens", {
    weekPct: 3, weekObservedAt: 100,
    codexWeekPct: 39, codexWeekObservedAt: 300,
  }, "mac");
  await relayFetch(kv, "POST", "/api/tokens", {
    weekPct: 5, weekObservedAt: 400,
    codexWeekPct: 35, codexWeekObservedAt: 200,
  }, "pc");
  const merged = await (await relayFetch(kv, "GET", "/api/tokens")).json();
  assert.equal(merged.weekPct, 5);
  assert.equal(merged.codexWeekPct, 39);
});
```

Add exact corrupt-state and unchanged-security tests:

```js
test("corrupt index and document JSON fail safely without listing", async () => {
  const brokenIndex = memoryKv({
    "__vibepulse_publishers_v1": "{",
  });
  assert.equal((await relayFetch(
      brokenIndex, "GET", "/api/tokens")).status, 404);

  const brokenDoc = memoryKv({
    "__vibepulse_publishers_v1": JSON.stringify(["mac"]),
    "/api/tokens:mac": "{",
  });
  assert.equal((await relayFetch(brokenDoc, "GET", "/api/tokens")).status,
               404);
  assert.equal(brokenIndex.calls.list + brokenDoc.calls.list, 0);
});

test("authentication allowlist and body validation stay unchanged", async () => {
  const kv = memoryKv();
  const wrongSecret = await worker.fetch(new Request(
      "https://relay.example/u/wrong/api/tokens"),
      { RELAY_SECRET: SECRET, VIBEPULSE: kv });
  assert.equal(wrongSecret.status, 404);
  assert.equal((await relayFetch(kv, "GET", "/api/agent-status")).status, 404);

  const oversized = await worker.fetch(new Request(ROOT + "/api/tokens", {
    method: "POST",
    body: "x".repeat(64 * 1024 + 1),
  }), { RELAY_SECRET: SECRET, VIBEPULSE: kv });
  assert.equal(oversized.status, 413);

  const malformed = await worker.fetch(new Request(ROOT + "/api/tokens", {
    method: "POST",
    body: "{",
  }), { RELAY_SECRET: SECRET, VIBEPULSE: kv });
  assert.equal(malformed.status, 400);
});
```

- [ ] **Step 2: Run again and verify the new tests fail for the intended reasons**

Run:

```sh
node --test tools/relay/test.mjs
```

Expected: failures show missing publisher-index behavior and the existing
`KV.list` call, not syntax or fixture errors.

- [ ] **Step 3: Add the minimal production implementation**

In `tools/relay/worker.js`, add a fixed internal index and strict parser:

```js
const PUBLISHER_INDEX_KEY = "__vibepulse_publishers_v1";
const PUBLISHER_NAME = /^[A-Za-z0-9._-]{1,64}$/;

function parsePublisherIndex(raw) {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed) || parsed.length > MAX_PUBLISHERS) return [];
    const unique = [];
    for (const value of parsed) {
      if (typeof value !== "string" || !PUBLISHER_NAME.test(value)) return [];
      if (!unique.includes(value)) unique.push(value);
    }
    return unique;
  } catch {
    return [];
  }
}

async function ensurePublisher(env, publisher) {
  const raw = await env.VIBEPULSE.get(PUBLISHER_INDEX_KEY);
  const publishers = parsePublisherIndex(raw);
  if (publishers.includes(publisher)) return true;
  if (publishers.length >= MAX_PUBLISHERS) return false;
  await env.VIBEPULSE.put(PUBLISHER_INDEX_KEY,
                          JSON.stringify([...publishers, publisher]));
  return true;
}

async function readDocs(env, endpoint) {
  const publishers = parsePublisherIndex(
      await env.VIBEPULSE.get(PUBLISHER_INDEX_KEY));
  const rawDocs = await Promise.all(publishers.map(
      (publisher) => env.VIBEPULSE.get(`${endpoint}:${publisher}`)));
  const docs = [];
  for (const raw of rawDocs) {
    if (!raw) continue;
    try {
      docs.push(JSON.parse(raw));
    } catch {
      // One corrupt document must not hide healthy publishers.
    }
  }
  return docs;
}
```

Delete the old `readDocs()` implementation that calls `KV.list()`.

In the POST/PUT branch, after JSON validation and before the existing endpoint
document `put`, add:

```js
if (!(await ensurePublisher(env, publisher)))
  return new Response("too many publishers", { status: 409 });
```

Keep the existing document key, envelope, merge functions, authentication,
body limit, endpoint allowlist, and response shapes unchanged.

- [ ] **Step 4: Run the Worker suite and verify GREEN**

Run:

```sh
node --test tools/relay/test.mjs
```

Expected: all pure merge and request-path tests pass; the fake KV's `list()`
method is never invoked.

- [ ] **Step 5: Commit the behavior and regression tests**

```sh
git add tools/relay/worker.js tools/relay/test.mjs
git commit -m "fix: remove KV listings from numbers relay"
```

### Task 3: Align the operator story and lessons with the real budget

**Files:**
- Modify: `tools/relay/README.md`
- Modify: `docs/relay.md`
- Modify: `docs/lessons.md`
- Test: `test/test_relay_boundary.py`

- [ ] **Step 1: Update the Worker guide and architecture guide**

Add this operational paragraph to `tools/relay/README.md`:

```markdown
Panel reads never list KV keys. The Worker keeps a bounded index of publisher
names and directly reads only those known documents. At a 30-second cadence,
three endpoints and two publishers use 25,920 key reads/day and zero list
requests. The publisher's existing ceiling remains at 384 document writes/day
for one continuously changing publisher or 768 for two, plus one index write
when each new publisher first registers.
```

Add the same storage rule to `docs/relay.md`, alongside the multi-publisher
section, and retain these exact facts:

- the Worker keeps one bounded publisher index and direct per-publisher keys;
- panel reads perform zero KV list requests;
- one panel with two publishers uses 25,920 reads/day at the 30-second,
  three-endpoint cadence;
- the existing 384/768 write ceiling remains unchanged;
- the computer must be awake, but it need not share the panel's network;
- the Worker route and numbers-only privacy boundary do not change.

- [ ] **Step 2: Add the lessons entry**

Append a `2026-08-22` entry to `docs/lessons.md` naming the mistake:

```markdown
## 2026-08-22 · KV key listing had its own daily budget

**What happened:** the numbers Worker returned error 1101 again even after
publisher writes were rate-capped. **Root cause:** every panel GET called
`KV.list()`; three endpoints at a 30-second cadence could make 8,640 list
requests/day against the free plan's separate 1,000/day allowance. Live
Wrangler inspection returned code 10048. **The rule:** budget every metered
operation class separately; a read design must not discover stable keys on
every read. **Guards:** the Worker now uses a bounded publisher index and
direct gets, and request-level tests make `KV.list()` throw if called.
**Watch for:** adding dynamic key discovery to a panel poll path or changing
the publisher/read ceilings without recomputing all KV operation classes.
```

- [ ] **Step 3: Run documentation/privacy checks and commit**

Run:

```sh
.venv/bin/python test/test_relay_boundary.py
git diff --check
```

Expected: the privacy test prints its `OK` line and the diff check is silent.

Commit:

```sh
git add tools/relay/README.md docs/relay.md docs/lessons.md
git commit -m "docs: explain list-free numbers relay"
```

### Task 4: Verify the repository before changing Cloudflare

**Files:**
- Test only; no repository modifications expected.

- [ ] **Step 1: Run focused regression suites**

```sh
node --test tools/relay/test.mjs
.venv/bin/python -m unittest tools.tokenserver.test_publisher -v
.venv/bin/python test/test_relay_boundary.py
```

Expected: all Worker, publisher-budget, retry, and privacy tests pass.

- [ ] **Step 2: Run the complete repository gate**

```sh
PYTHON_BIN="$PWD/.venv/bin/python" ./test/run.sh
```

Expected: exit 0, including the Node Worker suite once, tokenserver tests,
host C tests, visual tests, and interaction-relay tests.

- [ ] **Step 3: Validate the Worker bundle without deployment**

```sh
cd tools/relay
npx --yes wrangler@4.124.0 deploy worker.js \
  --dry-run --name vibepulse-relay --compatibility-date 2026-08-22
```

Expected: Wrangler builds the module Worker successfully and performs no
remote mutation.

- [ ] **Step 4: Review exact scope**

Run:

```sh
git status --short
git log --oneline origin/main..HEAD
git diff --check origin/main..HEAD
```

Expected: only the approved icon work, relay design/plan, Worker tests/code,
and relay documentation are present; no secrets, SDK config, firmware binary,
Wrangler state, or generated dependency files appear.

### Task 5: Deploy safely and prove the panel recovers without OTA

**Files:**
- External Cloudflare deployment and local service restart only.
- Do not modify firmware, `secrets.h`, `sdkconfig`, or OTA partitions.

- [ ] **Step 1: Capture the current Worker version and bindings**

Use Wrangler's read-only `deployments list` and `versions view` commands to
record the current version ID and confirm exactly two bindings remain:
`RELAY_SECRET` as secret text and `VIBEPULSE` as the existing KV namespace.
Do not print the relay URL secret.

- [ ] **Step 2: Create a private temporary Wrangler config**

Outside the repository, use `apply_patch` to create
`/tmp/vibepulse-relay-deploy/wrangler.toml`. Set `name` to
`vibepulse-relay`, `main` to this worktree's absolute
`tools/relay/worker.js`, and `compatibility_date` to `2026-08-22`. Add one
`[[kv_namespaces]]` block whose binding is `VIBEPULSE` and whose `id` is the
exact live namespace ID returned by Step 1.

The namespace ID is deployment metadata, not a secret, but the temporary
config stays outside git. Re-read the complete file before deployment and
compare its ID byte-for-byte to `versions view`; abort on any difference.

- [ ] **Step 3: Deploy the tested Worker**

```sh
npx --yes wrangler@4.124.0 deploy \
  --config /tmp/vibepulse-relay-deploy/wrangler.toml \
  --keep-vars --strict \
  --message "Serve numbers without KV list requests"
```

Expected: deployment succeeds and reports a new `vibepulse-relay` version.
Immediately inspect that version and confirm both original bindings remain.

- [ ] **Step 4: Warm the new publisher index**

Restart only the existing launchd tokenserver with `launchctl kickstart -k`.
The plist arguments are unchanged, so `kickstart` is the correct operation.
Wait for the local health endpoint to report `usage_http_200 + ok` and
`claudeWeekStale: false`.

- [ ] **Step 5: Verify cloud and panel behavior**

Read the private relay URL from the existing launchd plist into a shell
variable without printing it. Poll `/api/tokens` until it returns HTTP 200,
then compare only non-secret fields:

```text
claudeWeekPct
claudeWeekStale
claudeModelWeekPct
claudeModelWeekStale
codexWeekPct
codexWeekStale
```

Expected: cloud values match the local tokenserver and both Claude stale flags
are false. Allow one panel polling interval, then ask the user to confirm
`STALE` clears. No OTA or USB action is required.

- [ ] **Step 6: Roll back only if live verification fails**

If the deployed Worker cannot serve the warmed fixed index, use Wrangler's
rollback command with the version ID captured in Step 1, verify the old
version is active, and report the remaining Cloudflare list-quota limitation.
Do not alter panel partitions as part of Worker rollback.
