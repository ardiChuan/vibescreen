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
4. stores the endpoint document with its receipt timestamp; and
5. commits both changes together before acknowledging success.

Concurrent first publications serialize through the same mailbox and cannot
lose or displace peers. Storage errors fail the request; the existing
tokenserver publisher retries later.

### GET from the panel

The mailbox reads only the endpoint's bounded stored rows. `/api/tokens` uses
the unchanged observation-timestamp merge; Max Tracker and GitHub use the
unchanged newest-document rule. Corrupt rows are skipped without hiding valid
rows. Missing data returns the existing JSON 404 response; valid data returns
the same JSON body and content type the firmware already understands.

No request calls Workers KV `list()` or uses an eventually consistent dynamic
index. Public URLs and the firmware response contract do not change, so the
repair needs a Worker deployment and tokenserver restart, not firmware or OTA.

## Storage, migration, and rollback

The deployment adds a `NUMBERS_MAILBOX` Durable Object binding and a
SQLite-backed `NumbersMailbox` export. The existing `VIBEPULSE` KV binding and
data are retained temporarily for rollback but are not read or written by the
new request path.

The new mailbox begins empty. Immediately after deployment, restart each
active tokenserver publisher so all three endpoint documents are republished.
Do not claim recovery until the cloud endpoints match the local tokenserver.

Cloudflare version history remains the emergency rollback. Rolling back
restores the old KV data and public contract, but also restores the exhausted
list-operation failure. No destructive KV cleanup is part of this change.

## Budget

At a 30-second panel cadence, three endpoints produce 8,640 mailbox requests
per day. With the normal two publishers, each GET reads at most two document
rows; publisher writes remain capped at 384 per day for one continuously
changing publisher or 768 for two. This is far below the Durable Objects free
allowances of 5 million row reads and 100,000 row writes per day. Eight active
publishers remain within the read allowance, although the publisher write
budget still makes one or two active publishers the supported normal case.

## Verification

Regression tests must prove:

- the public Worker preserves secret-path auth, endpoint allowlisting, body
  bounds, JSON validation, publisher sanitation, and response bodies;
- the public Worker routes exactly one deterministic mailbox and never uses
  KV request-path operations;
- concurrent registration preserves every admitted publisher;
- a ninth publisher is rejected without displacement;
- registration and document storage commit atomically;
- storage failures return an error and do not partially publish state;
- token pools merge by observation timestamps across publishers;
- Max Tracker and GitHub retain newest-publication behavior;
- missing and corrupt stored records fail safely;
- the numbers-only privacy boundary and publisher daily-write ceiling remain
  green;
- Wrangler validates the SQLite Durable Object binding/export configuration.

Before deployment run focused Worker/mailbox tests, publisher tests, privacy
tests, the full repository gate, and a Wrangler dry run. After deployment,
restart tokenserver, verify local Claude data is fresh, compare non-secret
cloud fields, and confirm the physical panel clears `STALE` without OTA.
