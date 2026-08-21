# VibePulse live status on isolated Wi-Fi — approved design

**Status:** Approved by the user on 2026-08-21 after reviewing the local
visual explanation page.

## Outcome in plain English

Three symptoms have three independent fixes:

1. The Wi-Fi icon remains global and top-right, but a weak connection must
   still look like the familiar complete Wi-Fi symbol. Inactive arcs are a
   clearly visible neutral grey; active arcs are white; disconnected adds a
   slash.
2. The GitHub page is enabled only in this panel's ignored local configuration.
   The open-source default remains off and the public example continues to
   document the explicit opt-in.
3. Live Claude/Codex status may optionally use the existing user-owned
   encrypted mailbox when direct LAN access to the Mac fails. This is a new,
   independent, default-off privacy switch. It is not silently bundled with
   approvals or the numbers relay.

The computer must still be awake and the tokenserver must still be running.
The panel and computer only need ordinary outbound HTTPS and may be on
different, client-isolated, or unrelated Wi-Fi networks. No router changes,
inbound port, public Mac, or VPN are required.

## Evidence behind the design

- The flashed panel is healthy and joins `Solgarden WiFi`.
- Live samples moved from roughly -59 dBm (two bars) to -86 dBm (one bar), so
  the signal state changes; the physical one-bar rendering merely hides the
  faint outer arcs and resembles a small `C` plus a dot.
- The Mac tokenserver's `/api/agent-status` and `/api/github` responses are
  fresh.
- The panel's direct `.local` agent-status request stalls before HTTP headers
  on this Wi-Fi, while numbers and Max Tracker continue through their relay.
- The GitHub page is compiled out because `TK_GITHUB_SCREEN_ENABLED` is unset
  and therefore defaults off.

## Wi-Fi indicator contract

The existing geometry and ownership remain unchanged:

- one shared 28 x 28 platform object at `(418, 38)`;
- visible consistently across normal app screens;
- hidden during the existing boot handoff and foregrounded on supported
  overlays;
- 0–3 bars report association/RSSI only, never internet, Mac, tokenserver,
  GitHub, or relay health;
- the Wi-Fi event/task ordering and generation-saturation protection remain
  unchanged.

The only visual change is contrast. Every state keeps all three arcs and the
dot visible. Active ink is white. Inactive ink uses the already approved
neutral `#9298A2` rather than the physical-display-invisible dark grey. The
disconnected state also retains the white slash. Exact 480 x 480 simulator
captures must prove the symbol is identical across representative apps and
that all four signal states remain distinct.

## GitHub opt-in contract

No tracked source default changes. `secrets.h.example` continues to ship:

```c
#define TK_GITHUB_SCREEN_ENABLED 0
```

Only this panel's gitignored `secrets.h` changes to `1`. GitHub notifications
and sound remain independently off unless the user explicitly enables them.
The build and simulator tests must still prove that both the on and off forms
compile and that a fresh clone remains opt-out.

## Encrypted agent-status relay

### Independence and setup

Add `agent_status_relay` as a strict saved host boolean and
`CONFIG_TK_VIBEPULSE_AGENT_STATUS_RELAY` as a separate firmware option. Both
default off. It may share the existing interaction-relay HTTPS origin,
mailbox, Mac token, panel token, device key, and Worker deployment, but neither
switch implies the other.

The setup tool exposes a clear, explicit enable/disable/status/doctor path for
live status. Enabling requires the same explicit end-to-end-cloud consent as
the interaction relay. Disabling live status must not disable approvals,
providers, GitHub, the numbers relay, or remove credentials.

### What is encrypted

The host publishes only the existing bounded public `v:2` agent snapshot:

- at most four public jobs for Claude and four for Codex;
- provider counts and the already sanitized public job fields (`task_id`,
  `event_id`, state, project basename, activity category, normalized model,
  effort, and age);
- no pending question, approval, verdict, raw hook body, transcript, file
  content, environment variable, Wi-Fi credential, or unrestricted command.

This is the same public status the panel already renders on the LAN. Project
basenames and activity categories are encrypted end to end. Cloudflare sees
only fixed-size ciphertext, mailbox routing, IP addresses, timing, direction,
and HTTP result.

### Cryptographic frame

Derive a new direction-separated 256-bit key from the paired device key and
mailbox with the label `mac-to-panel-status-aead`. Do not reuse request or
verdict keys.

Each publication uses a fresh 96-bit nonce and AES-256-GCM. A fixed 2,816-byte
plaintext frame contains:

- four-byte status-frame magic/version;
- uint64 big-endian monotonically increasing Unix-millisecond publication ID;
- uint32 big-endian Unix-second expiry;
- uint16 big-endian status byte length;
- SHA-256 of the exact status bytes;
- canonical compact UTF-8 JSON status bytes;
- random authenticated padding to the fixed frame size.

The associated data binds protocol version, mailbox, and the literal status
direction. The outer canonical JSON remains `v`, `nonce`, and `ciphertext`.
The complete fixed envelope remains within the firmware's bounded relay body.
Python and C share exact vectors.

### Mailbox and freshness

The Worker adds one latest-value status slot per mailbox:

- `PUT /v1/mailboxes/{box}/status` — Mac role only;
- `GET /v1/mailboxes/{box}/status` — panel role only;
- fixed ciphertext size and strict no-store/content-type rules;
- server retention no longer than 20 seconds;
- host publication every two seconds;
- panel poll every five seconds with bounded retry/backoff.

The encrypted inner expiry is 15 seconds. The panel verifies the AEAD, exact
frame, digest, canonical agent parser, wall-clock expiry, Worker expiry, and a
strictly newer publication ID before applying it. Replay, wrong key, tamper,
oversize, malformed JSON, unknown fields, expiry, or clock failure is a soft
drop and never changes the displayed status.

### Direct-LAN precedence and stale clearing

The LAN poll remains enabled. A valid LAN status owns the display while it is
fresh. Relay status may apply only after there has been no valid LAN result
for five seconds. This prevents a slightly older cloud copy from replacing a
working direct feed.

Relay application updates only Claude/Codex agent rows and preserves the
independent pending-interaction source merge. If the relay feed then expires
and LAN is still unavailable, the panel applies one empty agent snapshot
instead of showing an old working/waiting state forever. This clear never
resolves or removes a Needs You item.

### Failure and privacy posture

- Failure is fail-closed: last valid data may remain briefly, then activity
  clears; nothing becomes approved and no plaintext fallback is introduced.
- The older numbers Worker remains numbers-only.
- The interaction request/verdict routes retain their existing fixed frames,
  TTL, and authorization.
- Status relay remains optional in builds, setup, runtime, docs, and tests.
- Logs and doctor output report only counters/readiness, never agent fields or
  decrypted status.

## Verification and rollout

Before another hardware write:

1. Run focused Python, Worker, C crypto/parser/source-policy, wiring, boundary,
   setup, simulator, and exact visual tests.
2. Run the complete repository test gate.
3. Build the ESP32-S3 target with the effective 256 KiB LVGL pool and both
   chosen relay options, without touching `ota_0`.
4. Inspect the one-bar Wi-Fi capture at 1:1.
5. Ask separately before deploying/updating the user's Worker and before
   flashing `ota_1`.
6. On hardware, verify GitHub appears, Wi-Fi 0/1/2/3 states remain readable,
   LAN status wins when reachable, and encrypted status updates/clears on an
   isolated or unrelated Wi-Fi.

