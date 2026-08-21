# The relay mailbox

A ~150-line Cloudflare Worker that lets the panel fetch its numbers from
anywhere, instead of only from the same LAN as the service. Full design
rationale and what may/may not cross it: [docs/relay.md](../../docs/relay.md).

## Deploy (once, ~10 minutes)

Requires a free Cloudflare account and `wrangler` (`npm i -g wrangler`).

```sh
cd tools/relay
wrangler kv namespace create VIBEPULSE      # note the id it prints

cat > wrangler.toml <<EOF
name = "vibepulse-relay"
main = "worker.js"
compatibility_date = "2026-08-01"

[[kv_namespaces]]
binding = "VIBEPULSE"
id = "<the id from above>"
EOF

python3 -c "import secrets; print(secrets.token_hex(32))"   # the secret
wrangler secret put RELAY_SECRET            # paste the secret
wrangler deploy                             # prints the workers.dev URL
```

Your mailbox address is then:

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

`wrangler tail` shows requests live. The `test.mjs` suite
(`node --test tools/relay/test.mjs`) holds the merge logic still without
any Cloudflare involvement.

## Free-tier arithmetic

The publisher checks locally every 30 seconds, but it has a hard cloud-write
ceiling: quotas at most every 5 minutes, Max Tracker and GitHub at most every
30 minutes (tools/tokenserver/publisher.py). That is at most 384 KV writes per
day for one continuously changing publisher, or 768 for two, below the free
account's 1,000-write allowance. The ceiling is necessary because presentation
fields such as the current time and reset countdowns legitimately change on
almost every local check. The panel's reads (2,880/day at a 30 s cadence) stay
below the 100,000-read allowance.
