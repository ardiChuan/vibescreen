# The relay mailbox

A small Cloudflare Worker that lets the panel fetch its numbers from anywhere,
instead of only from the same LAN as the service. Full design
rationale and what may/may not cross it: [docs/relay.md](../../docs/relay.md).

## Deploy safely

Install the pinned local toolchain with `npm ci`. The committed
`wrangler.jsonc` is intentionally non-deployable, and the all-zero namespace
IDs live only in `*-test.jsonc`. Do not create a `wrangler.toml` or run plain
`wrangler deploy`; that bypasses the identity checks needed for the existing
private mailbox.

Create an absolute private strict-JSON config outside the repository. Copy this
complete shape exactly, then replace the KV placeholder with the existing real
namespace ID. The ID must be 32 lowercase hexadecimal characters; do not create
a new namespace because the bootstrap rollback path needs the existing data.

```json
{
  "name": "vibepulse-relay",
  "main": "bootstrap.js",
  "compatibility_date": "2026-08-22",
  "compatibility_flags": ["nodejs_compat"],
  "observability": {
    "enabled": true
  },
  "durable_objects": {
    "bindings": [
      {
        "name": "NUMBERS_MAILBOX",
        "class_name": "NumbersMailbox"
      }
    ]
  },
  "exports": {
    "NumbersMailbox": {
      "type": "durable-object",
      "storage": "sqlite",
      "state": "created"
    }
  },
  "kv_namespaces": [
    {
      "binding": "VIBEPULSE",
      "id": "REPLACE_WITH_EXISTING_32_HEX_KV_NAMESPACE_ID"
    }
  ],
  "secrets": {
    "required": ["RELAY_SECRET"]
  }
}
```

The binding is deliberately local: do not add `script_name` or `environment`.
`NumbersMailbox` must be the only lifecycle export. Keep `RELAY_SECRET` in the
Worker secret store; `secrets.required` declares its name but never its value.
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

The first deployment provisions the SQLite class while `bootstrap.js` keeps
serving the old KV path. Confirm that public behavior, then capture that exact
bootstrap version. Change only `main` from `bootstrap.js` to `worker.js` in the
private JSON and repeat the guarded dry-run/deploy commands with
`--expected-main worker.js`. The active Worker does not read or write KV; the
existing binding and data remain only for the bootstrap rollback path.

After class creation, rollback is allowed only to the captured bootstrap
version, never directly to a pre-Durable-Object version. Do not delete the old
KV data while this rollback path is retained.

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

The SQLite mailbox starts empty when `worker.js` becomes active. Restart every
active tokenserver so its immediate first pass republishes `/api/tokens`,
`/api/max-tracker`, and `/api/github`.

`node --test tools/relay/test.mjs` holds the merge logic still without any
Cloudflare involvement. `npm test` runs the real Worker/Durable Object runtime
and deployment-guard regressions. `npm run build:dry` makes pinned Wrangler
compile both staged test entrypoints with `--dry-run`; it cannot deploy.

## Free-tier arithmetic

The panel makes 2,880 poll cycles per day. Three endpoints per cycle are 8,640
panel GETs and 8,640 mailbox RPCs. On the healthy-success path, each publisher
is capped at 288 admitted token, 48 Max Tracker, and 48 GitHub publications per
day: 384 total for one publisher or 768 for two.

Each admitted publication writes one monotonic counter row and one document
row. That is 768 steady-state row writes per day for one publisher or 1,536
steady-state row writes for two. Registration adds one row once per publisher,
so the first full-rate day after mailbox initialization is 769 row writes for
one publisher or 1,538 row writes for two. The fixed eight-publisher limit
bounds every read.

A failed POST is not admitted and does not advance the publisher's send time,
so it can retry on the next 30-second check. The successful-publication and row
totals above are therefore not a hard ceiling on failed request attempts.
