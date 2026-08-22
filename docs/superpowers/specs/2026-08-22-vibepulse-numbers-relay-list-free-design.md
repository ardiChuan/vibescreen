# VibePulse numbers relay: list-free direct-read design

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
3. **Maintain a small fixed publisher index.** Keep the existing per-publisher
   documents, register each publisher once in a bounded index, and serve panel
   GETs with direct reads of only those known keys. This is the recommended
   design.

## Data model and request behavior

The Worker retains one document per publisher and endpoint, exactly as today,
plus one small fixed publisher-index record. The index contains at most the
existing `MAX_PUBLISHERS` limit of eight sanitized publisher names. Internal
key names and publisher metadata are never exposed to the panel.

A single merged snapshot was rejected during planning: Workers KV is
eventually consistent and does not provide a transaction around a read/merge/
write cycle. Two computers publishing simultaneously could therefore overwrite
one another's observations. The bounded index preserves the existing
per-publisher ownership and avoids that lost-update path.

### POST/PUT from a Mac or PC

The existing secret path, body limit, JSON validation, publisher header, and
endpoint allowlist remain unchanged.

Before accepting a document, the Worker directly reads the fixed publisher
index. A publisher already present causes no index write. A new publisher is
added without calling `KV.list()`; a ninth publisher is rejected rather than
silently displacing an existing one. Concurrent first registrations converge:
only a publisher missing from the index writes the union it observed, while a
publisher already present never rewrites a stale subset over a fuller index.

The accepted document is then written to the existing per-publisher endpoint
key. The Worker acknowledges success only after registration and document
storage complete. A failed operation leaves the tokenserver's retry behavior
unchanged.

### GET from the panel

The Worker directly reads the fixed publisher index, then directly reads the
known per-publisher keys for the requested endpoint. It never calls
`KV.list()` on the panel path. `/api/tokens` uses the unchanged observation-
timestamp merge; Max Tracker and GitHub use the unchanged newest-document
rule. A missing record returns the existing JSON 404 response; a valid record
returns the same JSON body and content type the firmware already understands.

The public URLs and firmware contract do not change, so this repair needs a
Worker deployment and tokenserver restart, not a firmware rebuild or OTA.

## Migration and rollback

The fixed publisher index is created by the first post-deployment publication.
Restarting tokenserver after deployment immediately registers the current
computer and republishes all three endpoints. Existing per-publisher documents
remain valid; no destructive data migration or cleanup is required.

The previous Worker version remains available through Cloudflare's version
history for rollback. Rolling back restores the old behavior but also restores
the list-budget failure, so rollback is only an emergency escape hatch.

## Budget

Panel traffic becomes one index read plus one direct read per registered
publisher, and zero list operations. With the normal two-publisher maximum,
three endpoints polled every 30 seconds use 25,920 key reads/day. Even all
eight supported publishers use 77,760 key reads/day, below the 100,000 free
daily read allowance. Publisher traffic retains the existing absolute
ceilings: at most 384 document writes/day for one continuously changing
publisher or 768 for two. Index writes occur only when registering a new
publisher, not on routine publications.

## Verification

Regression tests must prove:

- neither panel GETs nor publisher POSTs call `KV.list()`;
- first publication and first read work for every endpoint;
- known publishers do not rewrite the index and a ninth is rejected;
- independently registered publishers converge into the bounded index;
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
