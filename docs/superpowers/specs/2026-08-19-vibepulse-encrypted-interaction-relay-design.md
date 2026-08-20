# VibePulse encrypted interaction relay — design

**Date:** 2026-08-19
**Status:** security posture approved; implementation awaits review of this
written specification.
**Scope:** make the "Needs You" question/approval loop work across ordinary
internet-connected Wi-Fi without requiring the panel and tokenserver to share
a LAN, while preserving a simple, private, default-off open-source build.

## Outcome in plain English

With the optional encrypted interaction relay enabled, the panel and the
Mac/PC no longer need to be in the same house or on the same network. The
Mac/PC keeps the tokenserver private: it does not expose a port or broadcast
the tokenserver to the internet. Instead, both ends make outbound HTTPS
connections to a small Cloudflare relay owned by the user:

1. the Mac/PC encrypts the bounded question or approval view and uploads it;
2. the panel downloads and decrypts it on any ordinary Wi-Fi with internet;
3. the panel signs and encrypts the user's verdict and uploads it; and
4. the Mac/PC downloads, verifies, and applies that verdict to the still-live
   agent hook.

The Mac/PC must be awake, the tokenserver must be running, and the agent must
still be waiting for live "Needs You" decisions. If the Mac/PC is off, there
is no live agent to approve. The existing numbers relay may retain the last
published values, but the panel must mark them stale according to their
timestamps rather than imply that they are live.

"Any Wi-Fi" means a normal network that permits outbound HTTPS to the user's
Worker. Captive portals, fully offline networks, and networks that block that
Worker remain outside the guarantee. No inbound port forwarding, public
tokenserver, VPN, fixed IP, or router reconfiguration is required.

## Recommendation and rejected alternatives

The approved recommendation is the dedicated, end-to-end-encrypted relay in
this document, disabled by default. A secret-gated plaintext activity mailbox
is rejected: a leaked URL or relay-storage access would expose question and
command text. Keeping all activity strictly off-cloud remains available as
LAN-only mode, but cannot satisfy the work-from-any-network requirement.

When encrypted interaction relay is enabled, every eligible pending panel
view is uploaded as ciphertext, even when LAN direct also happens to work.
The Mac cannot know in time whether the remote panel needs the copy, and the
hook has a short deadline. Users who want zero cloud activity keep this switch
off and retain LAN-only behavior.

## Product rule: every remote/cloud feature is independent and opt-in

A fresh clone remains LAN-only. It needs no Cloudflare account, creates no
cloud activity mailbox, and compiles no interaction-relay task. Existing users
who update without adding configuration keep their current behavior.

| Capability | Default | Mac/PC required for live data | What crosses the cloud | Works across isolated Wi-Fi |
|---|---:|---:|---|---:|
| LAN VibePulse data | baseline after local setup | yes | nothing | no; direct LAN required |
| Local Needs You answers/detail | off (`--interactions`, detail, and device key opt in) | yes | nothing | no; direct LAN required |
| Existing numbers relay | off | yes to refresh | quota/history/public-repo numbers in plaintext | yes, for those numbers |
| Encrypted Needs You relay | off | yes, with a live agent | bounded panel view and verdict as padded ciphertext; routing metadata remains visible | yes |
| GitHub screen/source | off unless separately configured | depends on chosen source | public repository statistics only | independent |

The switches must not imply one another:

- `--publish` continues to enable only the existing numbers publisher.
- A new `--interaction-relay URL` explicitly enables the Mac/PC side of the
  encrypted interaction relay and requires `--interactions` plus
  `--interaction-detail`.
- A new target option, `CONFIG_TK_VIBEPULSE_INTERACTION_RELAY`, defaults to
  `n`. Only this option compiles and starts the panel-side relay client.
- GitHub remains controlled by its existing independent settings.
- Enabling the numbers relay must never enable encrypted activity, and
  enabling encrypted activity must never enable GitHub or numbers publishing.

`secrets.h.example` will keep every cloud setting commented out. When the
target option is enabled, configure/build guards require all of:

- `TK_VIBEPULSE_INTERACTION_RELAY_URL`;
- `TK_VIBEPULSE_INTERACTION_MAILBOX`;
- `TK_VIBEPULSE_INTERACTION_PANEL_TOKEN`; and
- the existing `TK_VIBEPULSE_DEVICE_KEY`.

Partially configured target builds fail with a direct recovery message. When
the Mac/PC flag is explicitly supplied but its optional crypto dependency or
credentials are absent, only the interaction-relay adapter fails closed. The
tokenserver keeps serving its LAN and numbers functions, emits a loud startup
diagnostic, and exposes the disabled reason on its local status page. It must
never silently send plaintext as a fallback.

## Why the LAN cannot be the robust answer

The current Mac and panel configuration was checked before selecting this
design:

- the tokenserver listens on port 8737 and Bonjour resolves the Mac correctly;
- the macOS application firewall is disabled and Python is allowed;
- the stock packet-filter configuration shows no custom rule that explains
  the failure; and
- connectivity can recover and later fail again.

During the reported incident, raw IP traffic failed in both directions while
both devices still had working internet. That rules out mDNS as the root cause
and is consistent with Wi-Fi client isolation, guest-band separation, or mesh
segmentation. Moving both devices to a non-isolated network may be a useful
local fix, but it depends on network administration and is not a product
solution.

An always-on ESP32 SoftAP/APSTA bridge is also rejected. It would require the
computer to change networks or have a second interface, disrupts normal
internet use during provisioning, and has already exercised the panel's most
fragile memory/render path. LAN direct remains the fast local path; the relay
is the robust path when direct reachability does not exist.

## Security posture

The old boundary was "activity never reaches the cloud." This optional mode
changes that boundary only after explicit user consent:

> Plaintext activity never reaches the cloud. Only the exact, bounded view
> eligible for display on the panel may enter the dedicated interaction relay,
> and it must be end-to-end encrypted before leaving the Mac/PC.

Cloudflare can observe account and network metadata such as source IP,
mailbox identifier, request timing, approximate padded size, and access
frequency. It stores ciphertext and cannot decrypt the question, command,
project text, or verdict without the separate Mac-to-panel device key. This is
documented plainly; end-to-end encryption does not hide metadata.

The relay does not receive raw hook payloads, agent status, session logs,
transcripts, file contents, or an unbounded command. The Mac/PC first converts
the hook into the existing allowlisted `pending_public()` panel view. If that
view is incomplete, truncated, unrenderable, over the size cap, marked
private, or not safe to approve, it may produce a terminal-only notice but
must set `can_approve=false`. Remote approval is impossible unless the exact
decision-relevant text fits and is shown.

### Threat model

- A passive network observer sees TLS traffic only.
- Cloudflare or someone who reads relay storage sees ciphertext and metadata,
  not content.
- Someone with only the panel relay token can copy ciphertext or submit junk,
  but cannot decrypt a question or mint a verdict that the Mac accepts.
- Someone with only the Mac relay token can cause denial of service, but
  cannot create panel-readable content without the device key.
- Replay is rejected by the live request ID, challenge, view digest, one-time
  state, and Mac-owned expiry.
- A stolen physical panel contains the device key and panel token and is
  therefore trusted like the panel is today. Rotation and revocation are part
  of the documented recovery procedure.
- A compromised Mac/PC or agent host is already inside the trust boundary and
  is not solved by this relay.

Availability attacks remain possible: the relay or an account operator can
drop, delay, or delete ciphertext. The safety response is terminal fallback,
never implicit approval.

## Separate service: do not modify the numbers relay

The current numbers Worker and `tools/tokenserver/publisher.py` remain
numbers-only. Their endpoints, KV behavior, CLI flag, tests, and privacy
rationale stay intact.

Encrypted interactions use a new `tools/interaction-relay/` Worker backed by
a Durable Object and a new `tools/tokenserver/interaction_relay.py` adapter.
They do not add an activity producer to `publisher.py`. Separation prevents a
numbers-only deployment, test, or secret from accidentally gaining an
activity path.

Workers KV is not suitable for one-time verdict coordination because reads
are eventually consistent across locations and it offers no atomic consume.
The dedicated service uses one SQLite-backed Durable Object per mailbox for
strongly consistent, transactional state and duplicate-safe operations.
Each open-source user deploys and owns their own Worker; this project does not
operate a central VibePulse mailbox.

## Relay API and storage rules

All routes are versioned, reject unsupported methods/content types, set
`Cache-Control: no-store`, disable permissive CORS, cap request bodies before
JSON parsing, and return generic authentication errors.

| Method and route | Credential | Purpose |
|---|---|---|
| `PUT /v1/mailboxes/{box}/requests/{id}` | Mac token | create or idempotently repeat one encrypted request |
| `GET /v1/mailboxes/{box}/requests/next` | panel token | read the oldest unexpired encrypted request, or 204 |
| `POST /v1/mailboxes/{box}/requests/{id}/verdict` | panel token | store one encrypted verdict or an exact idempotent repeat |
| `GET /v1/mailboxes/{box}/verdicts` | Mac token | read verdicts waiting for local verification |
| `DELETE /v1/mailboxes/{box}/requests/{id}` | Mac token | remove request and verdict after resolve/timeout |

The Worker has two unrelated 256-bit bearer tokens stored as Worker Secrets
and one configured mailbox identifier stored as a non-secret environment
setting:

- the Mac token can publish requests, read verdicts, and delete records;
- the panel token can read requests and post verdicts.

Tokens never appear in source control, URLs, logs, or response bodies.
Authentication comparisons are timing-safe. The mailbox identifier is a
separate random routing value, not an authentication secret. A deployment
serves only that configured mailbox; a valid token presented for any other
mailbox is rejected. Users who need independent panels deploy independent
mailboxes and credentials.

The Durable Object enforces:

- at most 8 live requests per mailbox;
- a maximum 4 KiB JSON transport envelope and a maximum 640-byte decoded
  panel view;
- oldest-first retrieval;
- at most 120 seconds of storage from the Durable Object's first receipt;
- create-once request IDs: an exact retry succeeds, a conflicting body gets
  409;
- one verdict per request: an exact retry succeeds, a conflicting verdict
  gets 409;
- transactional delete of request plus verdict; and
- an alarm that removes expired state even if the Mac disappears.

The relay cannot read the Mac's encrypted local deadline and never decides
whether a verdict is valid. Its 120-second lifetime is only a storage cap; the
live tokenserver's usually shorter monotonic deadline remains the authority.

## End-to-end cryptographic protocol

### Keys and randomness

The existing `TK_VIBEPULSE_DEVICE_KEY` is exactly 64 hexadecimal characters,
decoded to 32 raw bytes. It remains only on the panel and Mac/PC. Version 1
uses HKDF-SHA256 with fixed protocol salt
`SHA256("VibePulse interaction relay v1")`, the mailbox identifier in the
HKDF info, and distinct labels to derive. The exact info bytes are
`UTF8("vibepulse-ir/v1|" + mailbox + "|" + label)`:

- `mac-to-panel-aead` — AES-256-GCM request encryption;
- `panel-to-mac-aead` — AES-256-GCM verdict encryption; and
- `panel-verdict-mac` — HMAC-SHA256 over the decision fields.

Every encrypted message uses a fresh cryptographically random 96-bit GCM
nonce. A request ID is a fresh random 128-bit value encoded as unpadded
base64url. Each request also contains a fresh random 256-bit challenge. Fixed
test vectors lock hex decoding, HKDF labels, nonce handling, associated data,
and base64url behavior byte-for-byte between Python and ESP-IDF.

The GCM associated-data strings are unambiguous UTF-8 fields:

```
vibepulse-ir/v1|{mailbox}|{request_id}|request
vibepulse-ir/v1|{mailbox}|{request_id}|verdict
```

Mailbox and request ID are validated against narrow alphabets and lengths, so
the delimiter cannot be injected.

### Request contents

Before encryption, the Mac serializes this bounded request:

```json
{
  "v": 1,
  "requestId": "random-128-bit-id",
  "challenge": "random-256-bit-value",
  "expiresAt": 1787097720,
  "view": "base64url(exact compact panel-view JSON bytes)",
  "viewSha256": "sha256-of-those-exact-bytes"
}
```

Using exact view bytes avoids cross-language JSON-canonicalization ambiguity.
The panel verifies the AEAD tag, IDs, sizes, expiry shape, and SHA-256 before
parsing. It displays the decoded view and retains the request ID, challenge,
and view digest beside that exact UI item.

Padding is deterministic in size and random in content: request plaintext is
`uint16_be(json_length) || compact_json || random_padding` to exactly 2,048
bytes; verdict plaintext uses the same framing to exactly 1,024 bytes. The
length prefix and padding are inside GCM authentication. The outer JSON is
only `{v, nonce, ciphertext}` with unpadded base64url fields, so it remains
below the 4 KiB service cap. This reveals the message direction, which the
route already reveals, but removes content-dependent sizes within each
direction without unbounded ESP32 memory.

The displayed view digest is load-bearing: a verdict is valid only for the
exact bytes that produced the user's screen.

### Verdict contents and acceptance

The panel supports only the existing allowlisted actions appropriate to the
displayed request: `approve`, `deny`, `terminal`, or `panic`; it cannot send
arbitrary answer text. It calculates HMAC-SHA256 over this exact binary
encoding:

```
ASCII "vibepulse-ir-verdict-v1\0"
uint16_be(mailbox_utf8_length) || mailbox_utf8
16 raw request-id bytes
32 raw challenge bytes
32 raw view-digest bytes
uint8 verdict_code  // approve=1, deny=2, terminal=3, panic=4
```

It places those fields and the HMAC in the verdict plaintext, encrypts the
whole object with `panel-to-mac-aead`, and posts the opaque envelope. The
panel retries the exact same envelope until acknowledged or expired; it never
creates a different verdict for the same tap.

The Mac accepts a verdict only when all checks pass:

1. AEAD tag and version are valid;
2. request ID still names a live pending `InteractionStore` entry;
3. the Mac's own monotonic deadline has not elapsed;
4. challenge and view digest match that pending entry;
5. HMAC is valid with `panel-verdict-mac`;
6. the request has not already been consumed; and
7. `approve` is allowed only when the source view had `can_approve=true`.

The ESP32 wall clock is not a security authority. Timestamps are useful for
display and audit; the live Mac deadline and random challenge decide expiry.
After acceptance, the Mac resolves the hook once and deletes the relay record.
A forged, duplicate, late, unknown, or conflicting verdict is logged without
sensitive content and cannot resolve anything.

The emergency "deny everything" action is represented as a signed verdict
anchored to the request currently displayed. It is accepted only while that
anchor is pending, then resolves all pending interactions that existed on the
same tokenserver at acceptance time. Replaying it after the anchor disappears
does nothing. The existing LAN emergency route remains available.

## Mac/PC flow

The hook request still enters at loopback and parks in `InteractionStore`.
No hook handler and no store lock performs cloud I/O.

1. `InteractionStore` creates the CSPRNG request ID, challenge, exact bounded
   view bytes, digest, and local monotonic deadline.
2. It places an immutable publish job in a bounded background queue and
   immediately returns to holding the hook.
3. `interaction_relay.py` encrypts and publishes that job. An exact retry is
   safe.
4. While at least one relay-backed interaction is pending, the adapter polls
   verdicts promptly with bounded backoff. It is idle when none are pending.
5. It decrypts and verifies locally, hands only a valid decision to
   `InteractionStore`, then deletes the remote record.
6. Timeout, terminal answer, or direct-LAN answer also schedules remote
   deletion. Relay failure never extends the hook's existing terminal
   fallback deadline.

`interaction_relay.py` is the only module importing the optional Python
`cryptography` dependency. Default and numbers-only modes remain standard-
library compatible. The relay adapter has bounded queues, explicit timeouts,
redacted logs, exponential backoff with jitter, and no persistent plaintext.

The direct LAN API remains backward compatible. Its existing
`request_id|verdict|ts` HMAC format continues to work for current firmware;
the v1 relay envelope is an additional protocol rather than a silent format
replacement.

## Panel flow and two-source state

The current `/api/agent-status` LAN response continues to own agent rows and
local pending data. Relay polling must not feed a partial object through the
full agent-status apply function: doing so could blank valid agent data or let
LAN and relay updates erase one another.

Instead, firmware keeps independent bounded slots for:

- the latest LAN agent snapshot;
- pending interactions seen by LAN; and
- pending interactions seen by the encrypted relay.

It merges pending items deterministically by request ID and expiry, preferring
the LAN copy when both sources name the same request while retaining the relay
challenge/digest needed for failover. Answered IDs are suppressed until their
expiry so a delayed poll cannot resurrect a handled prompt.

Verdict routing is source-aware:

- a relay-only item posts its verdict to the relay;
- a LAN item uses the existing direct POST first;
- if a mirrored LAN verdict has an uncertain or failed direct result, the
  panel may post the same bound relay verdict; and
- duplicate delivery is safe because both Mac and relay consume once.

The Mac exposes optional v2 challenge/digest metadata in LAN pending objects
only when interaction relay is active, allowing that failover without changing
what is displayed. Older firmware ignores the additive fields.

The panel polls the interaction relay approximately every 5 seconds with
jitter, backs off on failure, and reconnects immediately after Wi-Fi returns.
It uses one bounded long-lived client/task where ESP-IDF permits connection
reuse. All Cloudflare HTTPS operations share a network/TLS gate so numbers,
GitHub, and interaction handshakes cannot pile up and recreate internal/DMA
memory pressure. The gate is never held with the LVGL/UI lock.

Network code decrypts and parses into bounded non-UI state. Only the final
validated state is applied under the UI lock; no network task calls LVGL. The
implementation uses bounded static or PSRAM buffers, explicit body caps, and
measures both free internal heap and largest DMA block during worst-case TLS
plus redraw. The corrected 256 KiB LVGL pool and its guard remain unchanged.

At a five-second idle poll, one panel makes about 17,280 small requests per
day. The Mac polls verdicts only while a hook is pending. The deployment guide
must state current Cloudflare limits and costs and show how to increase the
poll interval; the protocol must not depend on a free tier. The documented API
also permits a user to run a compatible self-hosted service instead of the
reference Cloudflare Worker.

## Failure behavior

- Relay disabled: behavior is byte-for-byte the current LAN path.
- Relay misconfigured: encrypted interaction mode stays off with a visible
  local diagnostic; no plaintext fallback occurs.
- Relay unavailable: direct LAN remains usable. Otherwise the hook reaches
  its existing terminal fallback safely.
- Mac/PC asleep or tokenserver stopped: no live Needs You request exists;
  the panel eventually clears expired mailbox state.
- Panel offline: the agent falls back to the terminal at its normal deadline.
- Mac restarts: its parked hook state is gone, so old cloud verdicts cannot be
  accepted; cleanup removes them.
- Wrong/rotated key: decrypt fails without revealing content and neither side
  treats the request as approved.
- Multiple taps/retries: exact idempotent verdict only; conflicting verdicts
  are rejected.

## Documentation deliverables

The implementation is not complete until an open-source user can understand,
enable, disable, and remove it without reading source code:

1. `README.md` gets the independent feature matrix and the plain-English
   network diagram.
2. `docs/relay.md` remains explicitly numbers-only and links to the separate
   optional interaction design.
3. New `docs/interaction-relay.md` documents deployment, exact data leaving
   each machine, metadata Cloudflare still sees, threat model, costs/limits,
   generation of all secrets, rotate/revoke, disable/uninstall, retention,
   failure behavior, and troubleshooting.
4. `tools/interaction-relay/README.md` covers the user-owned Worker/Durable
   Object deployment and deletion procedure.
5. `secrets.h.example` keeps settings commented out and includes safe
   generation commands; no real secret enters Git.
6. `tools/tokenserver/tokenserver.py --help` explains that `--publish` is
   numbers-only and that `--interaction-relay` sends bounded E2E ciphertext.
7. Upgrade notes state that old firmware and LAN-only installations continue
   to work with no migration.

The privacy statement must include a compact "what leaves your machine"
table and must never claim that encryption hides IP addresses, timing, mailbox
identity, or approximate padded sizes.

## Testing and review gates

### Automated boundaries

- Keep `test/test_relay_boundary.py` enforcing the existing numbers-only
  Worker and publisher, but narrow its rationale from "no activity in any
  cloud" to "this numbers transport has no activity producer or route."
  Numbers-relay comments in firmware and docs receive the same scoped wording.
  Its firmware assertion becomes specific to
  `TK_VIBEPULSE_RELAY_URL`/`torget_http_get_failover`; it must not forbid the
  separately configured encrypted client merely because its name contains
  `RELAY`.
- Add `test/test_interaction_relay_boundary.py` enforcing that the separate
  transport accepts only bounded ciphertext envelopes and that plaintext
  agent status, hooks, sessions, prompts, commands, and project fields have no
  route.
- Add default-off build tests proving no interaction-relay task, crypto
  dependency, endpoint, or secret is required.
- Add configuration-alignment tests across Kconfig defaults,
  `secrets.h.example`, CLI help, README, and both relay documents.

### Protocol and service tests

- Shared Python/C test vectors for hex decoding, HKDF, AES-GCM, HMAC,
  base64url, padding, associated data, and all tamper/wrong-key cases.
- Worker tests for role separation, cross-mailbox denial, body/count caps,
  no-store headers, TTL, oldest-first behavior, create-once semantics,
  one-verdict semantics, exact retries, and alarm cleanup.
- Tokenserver tests for background publication outside locks, valid resolve,
  forged/expired/duplicate/no-pending rejection, dead-hook cleanup, relay
  outage, direct answer cleanup, and optional-dependency failure behavior.
- Firmware host tests for hostile envelopes, parser bounds, two-source merge,
  deduplication, answered-ID suppression, source-aware routing, idempotent
  retry, Wi-Fi backoff, and absence of UI calls from network tasks.
- An integration test drives a fake hook, fake panel, and local Durable Object
  through publish, display bytes, verdict, verification, one-time resolve, and
  deletion.

### Hardware acceptance — ota_1 only

The physical gate deliberately makes LAN reachability unavailable without
changing the router, then verifies over normal internet:

1. numbers still arrive when their separate relay is enabled;
2. an encrypted question and permission appear with the exact expected text;
3. approve, deny/leave, timeout, and emergency action resolve correctly;
4. a reboot, Mac restart, relay outage, wrong key, and duplicate verdict all
   fail safely;
5. rotation, data arrival, OTA takeover, and relay polling do not wedge the
   display;
6. free internal heap stays at or above the existing 32 KiB health floor and
   the largest DMA block stays at or above twice one 11,520-byte panel flush
   (23,040 bytes, the existing runtime warning floor) during TLS handshake
   plus worst-case glyph redraw, with no allocation, lock, or watchdog error;
   and
7. a long soak covers reconnects and repeated interactions.

All flashing and testing targets `ota_1`. The v0.5.0 rollback in `ota_0` is
never written, erased, reformatted, or selected as a test target.

## Acceptance summary

This design is complete when an open-source user can choose any combination
of LAN-only, numbers relay, encrypted Needs You relay, and GitHub; a fresh
build sends no activity to any cloud; encrypted Needs You works across
isolated Wi-Fi with only outbound HTTPS; Cloudflare never receives plaintext
question or verdict content; retries and replays cannot resolve the wrong or
expired hook; relay failure falls back safely; and the new TLS work does not
regress the panel's rendering or memory stability.
