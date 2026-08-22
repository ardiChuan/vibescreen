# VibePulse numbers relay: fixed-snapshot design

**Date:** 2026-08-22  
**Status:** user-approved direction; implementation pending  
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

The Worker currently stores one KV document per publisher. Every panel GET
calls `KV.list()` to discover those documents and then reads each one. A panel
polling all three endpoints every 30 seconds can therefore cause up to 8,640
KV list operations per day. Cloudflare's live API reports that this account
has exhausted the free daily allowance for that operation (`code 10048`), and
the Worker responds with error 1101. The panel then honestly keeps its last
known values and marks them stale.

The publisher write ceiling fixed the earlier write-budget failure, but it did
not address this independent read-path list budget.

## Options considered

1. **Pay for more KV operations.** No code change, but the inefficient access
   pattern remains and every open-source user inherits an avoidable cost.
2. **Poll much less often.** This requires firmware and OTA changes, makes the
   screen slower, and still scales the expensive list operation with every
   panel read.
3. **Maintain one ready-to-read snapshot per endpoint.** Merge on the bounded
   publisher POST path, then serve each panel GET with one direct KV read and
   no listing. This is the recommended design.

## Data model and request behavior

The Worker owns one fixed KV record for each allowed endpoint:

- `/api/tokens`
- `/api/max-tracker`
- `/api/github`

The exact internal key names are implementation details and are never exposed
to the panel.

### POST/PUT from a Mac or PC

The existing secret path, body limit, JSON validation, publisher header, and
endpoint allowlist remain unchanged.

For `/api/tokens`, the Worker reads the current fixed snapshot, combines it
with the incoming document using the existing observation-timestamp rules,
and writes the new snapshot. The freshest observation still wins separately
for Claude, Codex, and model-specific pools, so multiple computers continue
to cooperate honestly.

For `/api/max-tracker` and `/api/github`, the newest accepted publication
replaces the fixed snapshot, matching the current newest-document rule.

The Worker acknowledges success only after the fixed record is written. A
failed write leaves the publisher retry behavior unchanged.

### GET from the panel

The Worker performs one direct `KV.get()` for the requested endpoint. It never
calls `KV.list()` on the panel path. A missing record returns the existing
JSON 404 response; a valid record returns the same JSON body and content type
the firmware already understands.

The public URLs and firmware contract do not change, so this repair needs a
Worker deployment and tokenserver restart, not a firmware rebuild or OTA.

## Migration and rollback

The new fixed keys are warmed by restarting tokenserver after deployment,
which immediately republishes all three endpoints. Old per-publisher keys may
remain in KV but are no longer listed or read; no destructive cleanup is
required for the repair.

The previous Worker version remains available through Cloudflare's version
history for rollback. Rolling back restores the old behavior but also restores
the list-budget failure, so rollback is only an emergency escape hatch.

## Budget

Panel traffic becomes one KV read per endpoint request and zero list
operations. Publisher traffic retains the existing absolute ceilings: at most
384 writes/day for one continuously changing publisher or 768 for two. Each
publication adds at most one direct read of the existing snapshot, keeping the
normal two-publisher total far below the read allowance while remaining below
the existing write allowance.

## Verification

Regression tests must prove:

- panel GETs never call `KV.list()`;
- first publication and first read work for every endpoint;
- token pools merge by their observation timestamps across publishers;
- Max Tracker and GitHub retain newest-publication behavior;
- missing and corrupt stored records fail safely;
- authentication, endpoint allowlisting, body bounds, and numbers-only privacy
  remain unchanged;
- repeated panel polling does not increase list-operation count;
- the existing publisher daily-write budget test remains green.

Before deployment: run the Worker tests, relay privacy boundary tests, and a
Wrangler dry run. After deployment: restart tokenserver, verify its local
Claude data is fresh, verify the cloud endpoint returns the same fresh values,
and then confirm the physical panel clears `STALE` without a new OTA.

