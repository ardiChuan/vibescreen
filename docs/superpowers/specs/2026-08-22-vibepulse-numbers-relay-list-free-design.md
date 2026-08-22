# VibePulse numbers relay: coordinated mailbox design

**Date:** 2026-08-22
**Status:** user-approved direction; strengthened after independent review
**Scope:** the existing numbers-only Cloudflare Worker in `tools/relay`

## Outcome in plain English

When a Mac or PC running `tools/tokenserver` is online, it publishes quota,
Max Tracker, and GitHub numbers to the user's Cloudflare mailbox. The panel
fetches those numbers outbound from any Wi-Fi with internet access. The panel
and computer do not need to share a house, subnet, router, or direct LAN path.

The privacy boundary does not change: this relay carries numbers only. Agent
activity, project names, questions, commands, and approval verdicts remain
outside this Worker.

## Root cause

The old Worker stores one KV document per publisher. Every panel GET calls
`KV.list()` to discover those documents. A panel polling all three endpoints
every 30 seconds can therefore cause 8,640 KV list operations per day. The
live account exhausted Cloudflare's separate free daily list allowance and
the Worker began returning error 1101, so the panel honestly retained its last
known values and marked them stale.

Removing `KV.list()` alone is not sufficient. Workers KV is eventually
consistent and cannot atomically update a dynamic publisher index. Independent
review demonstrated that a stale read can admit a ninth publisher, displace an
existing publisher, or silently replace a corrupt index. A strongly consistent
coordination point is required.

## Options considered

1. **Pay for more KV operations.** Avoids immediate failure but preserves the
   inefficient access pattern and an avoidable cost for open-source users.
2. **Poll much less often.** Requires firmware/OTA work, slows the display, and
   still scales the expensive operation with every panel read.
3. **Static publisher allowlist.** Consistent, but adds setup every time a user
   adds or renames a computer and conflicts with the simple open-source flow.
4. **One SQLite-backed Durable Object per private mailbox.** Strongly
   coordinates the bounded publisher set and its documents without lists.
   This is the selected design.

Cloudflare recommends SQLite-backed Durable Objects for new coordinated state.
The free tier includes 5 million row reads and 100,000 row writes per day. This
mailbox uses only a small fraction of those limits at the panel's current poll
rate.

## Architecture

The public Worker remains the authentication and protocol boundary. It checks
the secret path, endpoint allowlist, method, body limit, JSON, and sanitized
publisher exactly as today. After validation it routes the request to one
deterministically named `NumbersMailbox` Durable Object through the
`NUMBERS_MAILBOX` binding.

The Durable Object is the mailbox's coordination atom. A single private Worker
deployment has one logical mailbox, so this is not a global singleton shared
between unrelated users. It uses SQLite storage and synchronous transactions
for the bounded publisher registry and endpoint documents.

### POST/PUT from a Mac or PC

Within one transaction, the mailbox:

1. validates whether the publisher is already registered;
2. registers it only when fewer than `MAX_PUBLISHERS` (eight) exist;
3. rejects a ninth publisher without changing any existing state;
4. increments a mailbox-owned monotonic receipt sequence;
5. stores that sequence and the endpoint document; and
6. commits the counter, registry, and document together before acknowledging
   success.

Concurrent first publications serialize through the same mailbox and cannot
lose or displace peers. Storage errors fail the request; the existing
tokenserver publisher retries later. The public Worker and direct RPC callers
cannot supply `received_at`; extra RPC arguments have no authority over order.
This prevents a delayed caller or wall-clock skew from making a later stored
body look older than the body it replaces.

### GET from the panel

The mailbox reads only the endpoint's bounded stored rows. `/api/tokens` uses
the unchanged observation-timestamp merge; Max Tracker and GitHub use the
unchanged newest-document rule. Corrupt rows are skipped without hiding valid
rows. Missing data returns the existing JSON 404 response; valid data returns
the same JSON body and content type the firmware already understands.

No request calls Workers KV `list()` or uses an eventually consistent dynamic
index. Public URLs and the firmware response contract do not change, so the
repair needs a Worker deployment and tokenserver restart, not firmware or OTA.

Unexpected mailbox binding, RPC, or storage failures retain the existing 503
wire response and emit one structured diagnostic containing only the operation
(`publish` or `read`). Error text, URL secret, publisher, and body are never
logged.

## Storage, staged migration, and rollback

The deployment adds a `NUMBERS_MAILBOX` Durable Object binding and a
SQLite-backed `NumbersMailbox` export. The existing `VIBEPULSE` KV binding and
data are retained temporarily for rollback but are not read or written by the
new request path.

Cloudflare does not allow a Worker rollback to cross a Durable Object class
lifecycle change. This applies to the current declarative `exports` flow as
well as legacy migrations. Therefore rollout has two explicit deployments:

1. Create a private production JSON config with the real existing KV namespace
   ID, `main: "bootstrap.js"`, the `NUMBERS_MAILBOX` binding, the SQLite
   `NumbersMailbox` export, and `RELAY_SECRET` in `secrets.required`. Deploy it
   through the guard. This provisions the class while the bootstrap continues
   serving the old KV list/get/put request path. Capture this bootstrap version.
2. Change only `main` to `worker.js`, re-run the guarded dry build, then deploy.
   This activates the list-free Durable Object path without another class
   lifecycle change.

If stage 2 fails, rollback is allowed only to the captured bootstrap version,
because it is already on the Durable Object side of the lifecycle boundary.
Direct rollback to any pre-Durable-Object version is prohibited and must never
be promised. The bootstrap restores the old public KV behavior (including its
exhausted list-quota failure mode), and the existing KV data remains untouched.
These constraints follow Cloudflare's current
[Durable Object class exports](https://developers.cloudflare.com/durable-objects/reference/durable-objects-migrations/)
and [Worker rollback](https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/)
documentation.

The new mailbox begins empty. Immediately after stage 2, restart each active
tokenserver publisher so all three endpoint documents are republished. Do not
claim recovery until the cloud endpoints match the local tokenserver. No
destructive KV cleanup is part of this change.

## Deployment safety

The all-zero KV namespace exists only in explicitly named test configurations;
their Worker names also end in `-test`. The default Wrangler config points to a
missing sentinel entrypoint, so plain `wrangler deploy` from `tools/relay`
cannot upload a Worker. Production deployment requires the checked wrapper, an
explicit absolute private strict-JSON config outside the repository, the
expected nonzero real KV ID, and the expected stage entrypoint. The wrapper
rejects the wrong Worker name, entrypoint, KV binding/ID, Durable Object
binding/export, legacy migrations, or missing required-secret declaration
before starting Wrangler.

CI uses a separate command that can only invoke pinned Wrangler with
`--dry-run`. It compiles both test configurations (`bootstrap.js` and
`worker.js`) and cannot select a live deploy mode. Required secret names use
Cloudflare's current
[declarative secrets configuration](https://developers.cloudflare.com/workers/wrangler/configuration/#secrets),
never plaintext values.

## Budget

At a 30-second panel cadence, three endpoints produce 8,640 mailbox requests
per day. With the normal two publishers, each GET reads at most two document
rows. Every admitted publication updates one counter row and one document row,
plus a one-time publisher row: 384 daily publications are 768 steady-state row
writes for one publisher, or 1,536 for two. This is far below the Durable
Objects free allowances of 5 million row reads and 100,000 row writes per day.
Eight active publishers remain within the read allowance, although the
publisher write budget still makes one or two active publishers the supported
normal case.

## Verification

Regression tests must prove:

- the public Worker preserves secret-path auth, endpoint allowlisting, body
  bounds, JSON validation, publisher sanitation, and response bodies;
- the public Worker routes exactly one deterministic mailbox and never uses
  KV request-path operations;
- concurrent registration preserves every admitted publisher;
- a ninth publisher is rejected without displacement;
- registration and document storage commit atomically;
- storage failures return an error and roll back the receipt counter,
  publisher, and document together;
- neither the public Worker nor direct RPC callers can choose receipt order;
- token pools merge by observation timestamps across publishers;
- Max Tracker and GitHub retain newest-publication behavior;
- missing and corrupt stored records fail safely;
- the numbers-only privacy boundary and publisher daily-write ceiling remain
  green;
- the rollback bootstrap exports the class while preserving the old KV public
  contract;
- mailbox 503 diagnostics are useful but reveal no secret, publisher, body, or
  RPC error text;
- the deployment guard rejects invalid private configs before child-process
  execution;
- pinned Wrangler dry-builds both staged entrypoints without remote mutation.

Before deployment run focused Worker/mailbox tests, publisher tests, privacy
tests, the full repository gate, and a Wrangler dry run. After deployment,
restart tokenserver, verify local Claude data is fresh, compare non-secret
cloud fields, and confirm the physical panel clears `STALE` without OTA.
