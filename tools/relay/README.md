# The relay mailbox

A ~150-line Cloudflare Worker that lets the panel fetch its numbers from
anywhere, instead of only from the same LAN as the service. Full design
rationale and what may/may not cross it: [docs/relay.md](../../docs/relay.md).

## Deploy safely

Install the pinned local toolchain with `npm ci`. The committed
`wrangler.jsonc` is intentionally non-deployable, and the all-zero namespace
IDs live only in `*-test.jsonc`. Do not create a `wrangler.toml` or run plain
`wrangler deploy`; that bypasses the identity checks needed for the existing
private mailbox.

Create an absolute private strict-JSON config outside the repository. It must
name `vibepulse-relay`, use the existing real `VIBEPULSE` namespace ID, bind and
export the SQLite `NumbersMailbox`, and declare `RELAY_SECRET` as required.
The staged rollout is documented in the
[coordinated-mailbox design](../../docs/superpowers/specs/2026-08-22-vibepulse-numbers-relay-list-free-design.md): bootstrap first, then the active Worker.

```sh
cd tools/relay
npm ci
npm run build:dry
npm run deploy:dry -- \
  --config /absolute/private/vibepulse-relay.production.json \
  --expected-kv-id <existing-real-kv-id> \
  --expected-main bootstrap.js
npm run deploy -- \
  --config /absolute/private/vibepulse-relay.production.json \
  --expected-kv-id <existing-real-kv-id> \
  --expected-main bootstrap.js
```

After capturing the bootstrap version, change only `main` to `worker.js` and
repeat the guarded dry-run/deploy commands with `--expected-main worker.js`.
Rollback after class creation is allowed only to the captured bootstrap
version, never to a pre-Durable-Object version.

The mailbox address remains:

```
https://vibepulse-relay.<your-subdomain>.workers.dev/u/<the secret>
```

The secret never lives in code or in this repo — it exists in the Worker's
secret store, in your `secrets.h`, and in the service's start command.

## Wire it up

**Service side** (each machine that should publish — one or several):

```sh
python3 tools/tokenserver/tokenserver.py --publish "https://.../u/<secret>"
```

**Panel side** (`secrets.h`, then build + OTA once):

```c
#define TK_VIBEPULSE_RELAY_URL "https://.../u/<secret>"
```

## Verify

```sh
curl -s https://.../u/<secret>/api/tokens | head -c 200   # JSON within 30 s
```

`node --test tools/relay/test.mjs` holds the merge logic still without any
Cloudflare involvement. `npm test` runs the real Worker/Durable Object runtime
and deployment-guard regressions. `npm run build:dry` makes pinned Wrangler
compile both staged test entrypoints with `--dry-run`; it cannot deploy.

## Free-tier arithmetic

The panel polls three endpoints every 30 seconds: 8,640 mailbox requests per
day. Reads touch at most the bounded publisher rows. Each admitted publication
updates the monotonic receipt counter and one document row, plus a one-time
publisher row. At the existing publisher ceiling, 384 publications are 768
steady-state row writes for one publisher, or 1,536 for two.
