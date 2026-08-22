# VibePulse Claude stale recovery

**Date:** 2026-08-23

**Status:** Approved

**Scope:** Tokenserver credential recovery and numbers-relay publication only

## Problem

The Claude Code OAuth access token can expire while the computer remains on.
Merely running macOS or Windows does not refresh it; the official Claude client
refreshes the credential when Claude Code is used. Today the tokenserver treats
that local, harmless condition like a failed upstream request and backs off for
as long as eight minutes. On restart it can also publish the old stale snapshot
before the background Claude probe finishes, after which the five-minute relay
write ceiling delays the corrected snapshot. The result is a stale Claude card
even though the computer and Cloudflare relay are healthy.

## Chosen behavior

Use passive, safe recovery. The tokenserver must not create Claude prompts,
spend plan capacity, use an API key, or call an undocumented OAuth refresh
endpoint.

While Claude authentication is locally unavailable (`no token`, `expired
token`, or `known rejected token awaiting replacement`), the tokenserver checks
the local credential source again after a short recovery interval. Rechecking
the unchanged local state makes no Anthropic request. When the official Claude
client has replaced or renewed the credential, the next check performs the
existing read-only usage request and restores fresh values.

The numbers publisher treats a successful `/api/tokens` transition from stale
to fresh as a recovery event. It may publish that one correction immediately,
even if the normal five-minute endpoint ceiling has not elapsed. Ordinary value
changes, fresh-to-fresh changes, and unchanged heartbeats retain the existing
ceiling. A failed recovery POST does not update publisher state and is retried
at the next local publisher tick.

## Data flow

1. A Claude credential expires; the existing last-known values remain visible
   and honestly marked stale.
2. The tokenserver rechecks only local credential metadata at the short recovery
   interval. It does not send the expired or known-dead credential upstream.
3. Normal Claude Code use refreshes the official credential.
4. The tokenserver detects the replacement, runs its existing read-only usage
   probe, and marks the Claude values fresh.
5. The publisher recognizes stale-to-fresh recovery and immediately updates the
   secret-gated Cloudflare numbers mailbox.
6. The panel's normal outbound relay poll receives the fresh values on any
   working Wi-Fi.

## Failure and privacy boundaries

- Anthropic 429 cooldown remains authoritative and is never shortened.
- Network failures and malformed responses retain the existing exponential
  backoff.
- Expired and known-dead tokens are never sent upstream again.
- OAuth tokens, relay URLs, question text, project names, and commands are never
  logged or added to the numbers payload.
- This does not make the computer refresh Claude while nobody is using Claude
  Code. In that situation the panel remains honestly stale until the next real
  Claude Code use.
- The exceptional recovery write is bounded to a stale-to-fresh transition; it
  does not loosen normal Cloudflare write-economy rules.

## Tests

Regression tests must prove:

- local authentication-wait statuses use the short recovery interval;
- repeated checks of the same expired or known-dead credential make zero
  upstream requests;
- a renewed credential is picked up on the next recovery check;
- a `/api/tokens` stale-to-fresh correction bypasses the normal ceiling once;
- fresh-to-fresh changes still wait for the normal ceiling;
- failed recovery sends retry without losing the recovery state;
- non-token endpoints and the existing daily write-budget test are unchanged.

## Acceptance

After the official Claude client refreshes its credential, local Claude values
recover within one short tokenserver recovery interval and the corrected relay
snapshot is published on the next publisher tick, without a hidden Claude
conversation or manual tokenserver restart.
