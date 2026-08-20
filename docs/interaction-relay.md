# Encrypted Needs You relay — approvals on any Wi-Fi

This optional path lets a VibePulse panel show and answer supported Claude
Code or Codex decisions when the panel and computer are on unrelated networks.
It is for guest Wi-Fi, a phone hotspot, an isolated IoT network, or a panel in
another building. It is off by default and is separate from the numbers relay.

In plain English: the computer must be awake and tokenserver must be running.
However, both ends make only outbound HTTPS connections, so they may use any
ordinary internet Wi-Fi. There is no router reconfiguration, no inbound port,
no public Mac, no VPN, and no same LAN requirement.

```text
Claude/Codex ↔ tokenserver → encrypt → user's Worker → decrypt → panel
Claude/Codex ← tokenserver ← verify  ← user's Worker ← encrypt ← tap
```

Each user deploys and owns a separate Worker. VibePulse does not operate a
shared mailbox service.

## Pick features independently

Five choices stay independent and default to **Off**:

| Choice | Effect |
|---|---|
| Claude interactions | Claude Code may ask the local tokenserver for a panel decision. |
| Codex interactions | The optional Codex plugin may ask the local tokenserver. |
| Numbers relay | Quota, reset, Max Tracker, and optional public GitHub numbers use the older numbers-only Worker. |
| Interaction relay | Bounded encrypted views and encrypted verdicts use this Worker. |
| GitHub | One public repository's screen/notification may be enabled. |

Installing the Codex plugin does not enable Codex interactions and does not
enable the encrypted interaction relay. Enabling a provider does not enable
detail, either relay, or GitHub. The interaction relay additionally requires
at least one provider and bounded detail because there would otherwise be no
decision view to deliver.

## Recommended setup

Run these commands from the repository root. Nothing below flashes hardware.

1. Pair the panel and computer with the same 64-hex device key, as described
   in [agent-setup.md](agent-setup.md). Keep it in gitignored `secrets.h` and
   `~/.vibepulse-device-key` (mode `0600`).
2. Choose Claude, Codex, both, or neither in the guided local installer. It
   separately asks whether bounded detail may reach the panel; choose yes for
   the encrypted interaction relay:

   ```sh
   python3 tools/vibepulse_setup.py install
   ```

3. Install the pinned Worker tools and authenticate your own Cloudflare
   account:

   ```sh
   cd tools/interaction-relay
   npm ci
   npx wrangler login
   cd ../..
   ```

4. Find the HTTPS origin assigned to
   `vibepulse-interaction-relay` in your Cloudflare dashboard (or use a custom
   domain you control). Let the setup tool generate all routing credentials,
   deploy the Worker, save the private Mac token, and add the panel-only block
   to `secrets.h`:

   ```sh
   python3 tools/vibepulse_setup.py relay install \
     --url https://vibepulse-interaction-relay.YOUR-SUBDOMAIN.workers.dev \
     --yes-e2e-cloud
   ```

   Without `--yes-e2e-cloud`, an interactive terminal asks for the same
   explicit consent. Non-interactive setup fails closed.
5. Enable **VibePulse optional network features → Encrypted Needs You relay**
   in `idf.py menuconfig`, then build. The option is
   `CONFIG_TK_VIBEPULSE_INTERACTION_RELAY=y`. Flash or OTA only after the user
   separately approves that hardware-changing step.
6. Restart the tokenserver and verify both sides:

   ```sh
   python3 tools/vibepulse_setup.py relay status
   python3 tools/vibepulse_setup.py relay doctor
   python3 tools/vibepulse_setup.py doctor
   ```

For Codex, open `/hooks`, review and trust the exact VibePulse commands, then
start a new Codex task. For Claude Code, install only the documented loopback
hooks. Neither setup bypasses the agent's own trust UI.

## What leaves the computer

The tokenserver first constructs the same bounded public view the panel is
allowed to render. Before local encryption, the only possible stable fields
are:

- common: `provider`, `request_id`, `kind`, `can_approve`, `hold_ms`, and
  `project`;
- question: `prompt`, `marked`, `options_total`, selected `title`, and
  optional `subtitle`;
- approval: `tool`, `title`, and optional `subtitle`.

That list is not a cloud schema. It exists in local memory, is encoded as the
exact panel-view bytes, hashed, and encrypted before upload. Raw hook bodies,
session transcripts, full option lists, file contents, environment variables,
and unrestricted commands are never mailbox fields. If detail is disabled,
the relay cannot be enabled.

Every request is padded inside authentication to a fixed **2,048-byte request**
plaintext before its GCM tag. Every tap becomes one fixed **1,024-byte verdict**
plaintext before its tag. The outer Worker object contains only protocol
version, nonce, and ciphertext plus bounded routing metadata.

### What Cloudflare can still see

Encryption does not hide network metadata. Cloudflare can see an IP address
at each connection, timing and frequency, the mailbox identifier, request ID,
message direction, HTTP status, and the fixed padded size for that direction.
The repository's Worker logs only route kind, status, and duration.

Cloudflare never receives those fields in plaintext: question text, command
text, project name, or verdict. It also never receives the device key or the
Mac's live monotonic deadline. A mailbox operator can drop, delay, replay, or
delete ciphertext (availability), but cannot turn it into a valid approval.

## Security and retention

- Requests use AES-256-GCM with fresh nonces and keys derived from the paired
  256-bit device key. Verdicts are independently encrypted and HMAC-bound to
  the live request ID, random challenge, exact displayed-view digest, and one
  allowlisted verdict code.
- The Worker stores at most eight live requests. It deletes each row after at
  most **120 seconds** and uses a Durable Object alarm for cleanup. The
  tokenserver's usually shorter local deadline remains authoritative.
- A direct LAN answer, timeout, restart, or accepted remote answer schedules
  deletion. Old or duplicate ciphertext cannot approve a new hook.
- Failure is safe: no valid answer means Claude/Codex falls back to the
  computer. Silence is never approval.

This does reverse the old blanket “activity never uses cloud” statement, but
only behind an explicit opt-in and only after end-to-end encryption. The older
numbers transport never carries activity and keeps its independent secret and
allowlist.

## Limits the relay does not solve

The path needs working internet and HTTPS. A captive portal the panel cannot
accept, an offline network, DNS failure, TLS interception, or blocked Worker
domains still prevents delivery. The direct LAN path can continue working at
the same time. If both paths fail, the decision stays on the computer.

At the default five-second panel poll, one panel can make roughly 17,280 idle
requests per day. Cloudflare pricing and quotas change, so check the current
[Cloudflare pricing for SQLite Durable Objects](https://developers.cloudflare.com/durable-objects/platform/pricing/),
[Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits/),
and [Cloudflare Durable Objects limits](https://developers.cloudflare.com/durable-objects/platform/limits/)
before deploying. The protocol does not depend on a free tier. Increase
`TK_IR_POLL_INTERVAL_MS` and rebuild if your account needs a lower poll rate;
that increases worst-case delivery latency by the same amount.

## Disable, remove, Rotate, Revoke, Update

Temporarily stop cloud traffic while keeping credentials:

```sh
python3 tools/vibepulse_setup.py relay disable
```

Restart the tokenserver after changing saved routing. To make the panel binary
LAN-only too, disable `TK_VIBEPULSE_INTERACTION_RELAY` in menuconfig and build
a new firmware image.

Remove local relay settings but leave the user-owned Worker for inspection:

```sh
python3 tools/vibepulse_setup.py relay uninstall --keep-worker
```

Remove local settings and delete that Worker:

```sh
python3 tools/vibepulse_setup.py relay uninstall --delete-worker
```

Uninstall preserves provider choices, the Codex plugin, GitHub, the numbers
relay, the repository, and the shared device key. A private backup named
`secrets.h.before-interaction-relay` is kept beside the saved config for
recovery; protect and later remove it deliberately.

To **Rotate** or **Revoke** a suspected relay credential, uninstall with
`--delete-worker`, verify the deployment is gone, then run relay install again;
it generates a new mailbox and unrelated Mac/panel tokens. If the device key
may be exposed, replace the 64-hex key on both computer and panel before
reinstalling, rebuild the panel, and invalidate the old Worker. Do not reuse a
numbers-relay secret.

To **Update**, pull a reviewed release, run `npm ci` in
`tools/interaction-relay`, execute its tests, and rerun relay install after a
deliberate uninstall/rotation. Never run an unreviewed Worker update against a
live mailbox.

## Manual or self-hosted service

Advanced users may self-host a compatible service instead of Cloudflare. Use
HTTPS with a publicly trusted certificate and implement the exact bounded API:

| Route | Role | Result |
|---|---|---|
| `PUT /v1/mailboxes/{box}/requests/{id}` | Mac token | Create or exact idempotent retry. |
| `GET /v1/mailboxes/{box}/requests/next` | Panel token | Oldest unexpired request or 204. |
| `POST /v1/mailboxes/{box}/requests/{id}/verdict` | Panel token | One verdict or exact retry. |
| `GET /v1/mailboxes/{box}/verdicts` | Mac token | One waiting verdict or 204. |
| `DELETE /v1/mailboxes/{box}/requests/{id}` | Mac token | Atomically remove request and verdict. |

The replacement must preserve role-separated 256-bit bearer tokens,
`Cache-Control: no-store`, strict canonical envelope sizes, eight-row capacity,
oldest-first ordering, create-once semantics, and the 120-second maximum TTL.
It does not need any encryption key: crypto remains end to end.

## Troubleshooting

| Symptom | Check |
|---|---|
| Relay status is `OFF` | This is the safe default. Run the explicit install path. |
| Doctor says provider/detail is missing | Rerun the guided local install and opt in to exactly what you want. |
| Doctor says panel block/key is missing | Restore the generated block and shared 64-hex key in gitignored `secrets.h`, then rebuild. |
| Worker deploy fails | Run `npm ci`, `npx wrangler login`, check the HTTPS origin/account, then retry. Local routing remains disabled on failure. |
| Panel shows Wi-Fi but no decision | Check captive portal/DNS/domain filtering, relay doctor, tokenserver, and serial redacted counters. |
| Wrong key after rotation | No plaintext fallback occurs. Pair both sides with the same new key and rebuild. |

Protocol internals and threat analysis are recorded in
[`docs/superpowers/specs/2026-08-19-vibepulse-encrypted-interaction-relay-design.md`](superpowers/specs/2026-08-19-vibepulse-encrypted-interaction-relay-design.md).
