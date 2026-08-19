# VibePulse Codex interactions — design

**Date:** 2026-08-19
**Status:** product, privacy, and visual direction approved; implementation
awaits review of this written specification.
**Depends on:**
`2026-08-19-vibepulse-encrypted-interaction-relay-design.md` for the
outbound-only, end-to-end-encrypted Mac/PC ↔ panel transport.

## Outcome in plain English

An open-source user may optionally let the VibePulse panel answer Codex in
the same way it can answer Claude Code. After one explicit setup on the
computer:

- safe Codex permission prompts can appear on the panel as **ALLOW ONCE**,
  **DENY**, or **LEAVE IT**;
- short multiple-choice questions can show the option Codex explicitly
  recommends, with the remaining options left on the computer; and
- the panel and computer may be on different networks when the separately
  enabled encrypted interaction relay is in use.

The Mac/PC must be awake, Codex must still be waiting, and the tokenserver
must be running. The computer does not broadcast a public tokenserver or
accept inbound internet traffic. Both the computer and panel make outbound
connections to the user's relay.

This is not enabled in a fresh clone. Claude interactions, Codex
interactions, the numbers relay, the encrypted interaction relay, and GitHub
remain independent switches. A user who wants only the existing display or
only Claude does not install or enable the Codex adapter.

## Why Codex needs two official extension paths

Codex exposes two different kinds of human interaction, and they cannot be
handled honestly through one hook:

1. The documented `PermissionRequest` lifecycle hook can directly return an
   `allow` or `deny` decision. It is the correct integration point for
   permissions. If the hook returns no decision, Codex presents its normal
   approval UI.
2. The normal Codex user-question request can be observed by `PreToolUse`,
   but `PreToolUse` can only block or rewrite a tool call; it cannot provide
   the user's answer as that tool's result. Pretending it can would leave the
   Codex Desktop/CLI prompt waiting after the panel tap.

The current Codex app-server protocol does expose
`tool/requestUserInput` and server-initiated approval requests to a client,
but adopting it would mean building and owning a separate Codex client rather
than extending the user's existing Desktop/CLI experience. Its WebSocket
transport is also documented as experimental and unsupported for production.
That is deliberately not the v1 product.

The approved v1 therefore uses:

- a trusted **Codex `PermissionRequest` command hook** for permissions; and
- a small local **VibePulse question MCP tool** for recommended choices.

These fit in one opt-in VibePulse Codex package. The package also supplies a
`SessionStart` hook that tells Codex when to prefer the question tool and when
to keep using the computer's normal question UI. Codex Desktop and Codex CLI
load the same package and local configuration.

Authoritative references:

- <https://learn.chatgpt.com/docs/hooks>
- <https://learn.chatgpt.com/docs/app-server>
- <https://learn.chatgpt.com/docs/build-plugins>

## Product switches and compatibility

The computer is the privacy authority because it decides which agent content
may leave the agent process. The target configuration is:

| Capability | Default | Enabling action |
|---|---:|---|
| Claude interactions | off | computer setup selects Claude |
| Codex interactions | off | computer setup selects Codex and installs the reviewed package |
| Local interaction detail | off | user explicitly allows bounded text on the panel |
| Encrypted interaction relay | off | user separately deploys/selects the E2E relay |
| Numbers relay | off | existing `--publish` path only |
| GitHub | independent | existing GitHub configuration only |

Host configuration gains separate `claude_interactions` and
`codex_interactions` booleans. The old `--interactions` flag remains a
backward-compatible alias for Claude-only behavior; an update must never
silently enable Codex. New explicit CLI flags may override the saved values
for diagnostics, but normal users use the setup command.

This refines the earlier relay specification's generic `--interactions`
prerequisite: encrypted interaction relay requires at least one explicitly
enabled provider plus interaction detail. It must not require the legacy
Claude alias, because Codex-only is a supported combination.

Firmware gains one default-off global interaction capability gate. Provider
choice stays on the computer: firmware does not need a combinatorial set of
Claude/Codex builds, and content for a disabled provider is never produced.
The provider is still validated on every received request.

Disabling Codex interactions immediately stops publishing new Codex
requests, resolves no parked request, and causes live hooks/tools to fall back
to the computer. Uninstall removes the Codex package and its owned config
entries without rewriting unrelated Codex settings.

## One simple, reviewable setup

The implementation adds one cross-platform setup entry point, tentatively:

```text
python3 tools/vibepulse_setup.py
```

It uses plain-language prompts and may be rerun safely:

1. choose Claude interactions, Codex interactions, both, or neither;
2. choose LAN-only or the separately deployed encrypted relay;
3. explain exactly what leaves the computer in the selected mode;
4. generate or validate the device key without printing it after creation;
5. install/update the VibePulse Codex package and its local MCP registration;
6. enable the matching tokenserver configuration; and
7. open or print the Codex hook-review step.

Codex requires non-managed command hooks to be reviewed and trusted. The
setup must not bypass that protection or edit Codex's trust database. The one
extra confirmation in `/hooks` is intentional: the user sees the exact
commands that can pause and answer Codex.

The same setup command has `status`, `doctor`, `disable`, and `uninstall`
modes. `doctor` checks the tokenserver, plugin/package registration, hook
trust, local MCP availability, key match without revealing the key, and relay
reachability. It prints a short pass/fix list rather than asking the user to
inspect configuration files.

Windows and macOS are first-class. Paths and command launchers are generated
for the current platform; no setup step assumes `/bin/sh`. Python 3.11 is the
only host runtime already required by VibePulse. Linux may use the same CLI
path but is not claimed supported until its complete install/doctor test
passes.

## Codex package

The repository contains the source of a local, versioned VibePulse Codex
package. It is not installed by cloning or building firmware. The package
contains:

- `hooks/hooks.json` with `SessionStart` and `PermissionRequest` command
  hooks;
- a small question MCP server registered as `vibepulse`;
- a short skill/reference explaining the tool's intended use; and
- platform-neutral helper commands that talk only to the loopback
  tokenserver.

Every executable path in the hook config is absolute after installation. The
package never reads the Codex transcript: hook payloads and explicit MCP tool
arguments are the only supported inputs. It never scrapes the Desktop UI,
injects mouse/keyboard input, edits rollout logs, or connects to an
undocumented Desktop socket.

The `SessionStart` hook returns narrow developer context:

- use the VibePulse question tool only for a short, non-secret,
  single-choice question with two or three bounded options;
- mark a recommended option only when Codex genuinely recommends it;
- use native `request_user_input` for free-form text, secrets, more than one
  question, multi-select, or anything that cannot be represented exactly;
- if the tool reports unavailable, timeout, or **LEAVE IT**, immediately use
  the normal computer question UI; and
- never treat silence or a transport error as an answer.

If that context or MCP server is unavailable, Codex behaves normally. The
package is an enhancement, not an enforcement boundary.

## Question flow and recommendation contract

The local MCP tool accepts exactly one question:

```json
{
  "question": "How should Codex handle approvals?",
  "header": "Approvals",
  "options": [
    {
      "label": "Use the trusted hook",
      "description": "Desktop + CLI, one setup",
      "recommended": true
    },
    {
      "label": "Keep computer only",
      "description": "No panel decisions"
    }
  ]
}
```

Bounds are enforced before anything is parked or published:

- one question, 96 display characters maximum;
- two or three options;
- 64 display characters per option label and description;
- zero or one explicitly `recommended: true` option;
- no free-form answer, multi-select, secret, control characters, or hidden
  payload; and
- a 120-second maximum hold with the tokenserver's shorter live deadline
  authoritative.

The panel's **APPROVE** action means “choose the exact option explicitly
marked recommended.” VibePulse never promotes the first option by convention
and never invents a recommendation. With no explicit recommendation, the
panel is alert-only and the question is answered on the computer.

The tool sends a normalized provider-tagged request to the loopback
tokenserver and waits outside all store/UI locks. On a valid panel choice it
returns the exact chosen option label and stable option index to Codex. On
**LEAVE IT**, timeout, unavailable tokenserver, invalid content, or relay
failure it returns a structured fallback result; Codex then calls its native
question UI. A late panel answer cannot be applied to a later question.

## Permission flow

The `PermissionRequest` hook receives documented Codex fields including
`session_id`, `turn_id`, `cwd`, `tool_name`, and `tool_input`. A small command
adapter:

1. reads one bounded JSON object from stdin;
2. normalizes it into the provider-neutral interaction store;
3. waits for a local or encrypted-relay verdict; and
4. prints the documented Codex decision JSON only after verification.

Mappings are exact:

| Panel action | Hook output |
|---|---|
| **ALLOW ONCE** | `decision.behavior = "allow"` |
| **DENY** | `decision.behavior = "deny"` with a short local message |
| **LEAVE IT** / timeout / unavailable | no decision; Codex shows its normal prompt |

Codex supports broader decisions such as session-wide acceptance and policy
amendments through other APIs. VibePulse v1 never sends them. It grants one
pending request only.

Remote **ALLOW ONCE** remains intentionally narrow. It is available only when
the exact decision-relevant text is displayed in full and the normalized
operation matches the existing safe allowlist: read-only inspection, tests,
or builds without shell chaining. V1 does not remotely approve:

- file changes;
- installs, deploys, publishes, pushes, deletes, or privilege escalation;
- arbitrary network or managed-network access;
- additional filesystem permissions;
- commands containing chaining, redirection, interpolation, or newlines;
- session-wide approval; or
- exec-policy amendments.

Unsupported but readable requests may still offer **DENY** and **LEAVE IT**.
Unreadable, private, malformed, or truncated requests offer only the safe
computer fallback. Other matching Codex hooks and managed policy remain
authoritative; a deny from another hook wins.

## Provider-neutral interaction core

`InteractionStore` becomes independent of Claude hook response formats. A
pending item carries:

- `provider`: `claude` or `codex`;
- `kind`: `question` or `approval`;
- random `request_id`, challenge, exact view bytes, view digest, creation
  time, and local deadline;
- stable session/turn/tool identifiers when supplied by the provider;
- exact bounded display fields and `can_approve`;
- question option identity, when applicable; and
- the adapter waiting for the result (`claude_hook`, `codex_hook`, or
  `codex_mcp`).

The core resolves once to an internal result. Provider adapters then format
that result:

- Claude adapter: existing `PreToolUse(AskUserQuestion)` or
  `PermissionRequest` hook JSON;
- Codex permission adapter: documented `PermissionRequest` decision JSON;
- Codex question adapter: MCP tool result containing the selected option; and
- relay adapter: encrypted, signed verdict handling from the separate relay
  specification.

This removes the current assumption that every question answer can be
expressed as Claude's `updatedInput.answers` object.

The public panel view adds the required `provider` enum. Provider is included
in the exact view bytes covered by the relay view digest. For direct LAN,
new firmware uses a v2 verdict MAC that binds provider, request ID, verdict,
timestamp, and view digest. The legacy direct verdict format remains accepted
for existing Claude firmware only; it cannot resolve a Codex request.

## Security and privacy rules

The encrypted-relay security posture remains unchanged:

- a fresh clone sends no activity to any cloud;
- plaintext questions, commands, projects, and verdicts never reach
  Cloudflare;
- only the exact bounded panel view is encrypted and uploaded;
- Cloudflare can still see IP addresses, mailbox identity, timing, and padded
  message sizes;
- a signed verdict is bound to provider, live request, challenge, exact view,
  and one-time state;
- the computer verifies the verdict before the provider adapter returns it;
  and
- silence, disconnect, bad crypto, wrong provider, stale state, or ambiguity
  always returns control to the computer without approval.

The Codex package does not weaken Codex sandboxing or managed policy. Hook
trust is visible to the user, and the package must fail closed if its source
changes until the user reviews the new hash. Logs contain request IDs,
provider, result class, and timing only—not question, command, project, token,
key, or ciphertext.

## Approved 480 × 480 Codex screen

The Codex question screen uses the same text anchors, sizes, and touch geometry
as the already approved Claude screen. Provider identity changes; layout does
not.

Shared geometry:

- frame: `(14, 14)`, `452 × 452`, radius `40`, stroke `2`;
- countdown ring: center `(80, 80)`, radius `44`, stroke `8`;
- eyebrow: `(148, 46)`, width `260`, `plex_ui_14`, letter spacing `1`,
  `LONG_DOT`; the left/top anchor and font stay identical on Claude and Codex,
  while the shorter width reserves a real no-overlap lane for Wi-Fi;
- question: `(148, 70)`, `300 × 68`, `plex_body_27`, stepping to
  `plex_ui_21` only when needed, `LONG_DOT` as the last bound;
- recommendation card: `(24, 140)`, `432 × 92`, radius `14`, stroke `2`;
- recommendation label/title/subtitle inside the card at `(20, 14)`,
  `(20, 34)`, and `(20, 70)` using 14/27/16 px fonts;
- question **APPROVE**: `(24, 244)`, `432 × 96`;
- question **LEAVE IT**: `(24, 350)`, `432 × 90`;
- footer: full width at `y=440`, `plex_ui_14`;
- approval description: `(148, 70)`, width `300`, 27 px;
- tool chip: `(24, 146)`, `58 × 26`;
- command: `(24, 182)`, width `432`, 40 px mono with the existing 24 px
  measured fallback;
- approval **ALLOW ONCE**: `(24, 252)`, `432 × 96`; and
- approval **DENY** / **LEAVE IT**: `(24, 360)`, `208 × 90` each with the
  existing 16 px gap.

Codex-specific rendering:

- accent `#6F78FF` replaces Claude coral everywhere except the shared deny
  red;
- eyebrow is `CODEX NEEDS YOU · <PROJECT>`;
- card label is `CODEX RECOMMENDS`;
- the icon is a new native `64 × 64` I4 asset generated by
  `tools/agent_assets/build-agent-images.py`, placed at `(48, 48)`;
- the icon uses the exact source-derived transparent Codex mark—no white app
  tile, runtime scaling, recolor, or hand-drawn substitute;
- the small neutral Wi-Fi indicator occupies the reserved top-right
  `28 × 28` slot beginning at `(418, 38)` and never enters a text lane; and
- the footer says `N MORE OPTION(S) ON COMPUTER` for Codex.

Question and recommendation baselines are deliberately identical to Claude:
the approved comparison put the prompt at the Claude row and the card title
and supporting text at the same rows. The simulator, not the design PNG, is
the acceptance source after implementation.

The existing one-object-tree rule stays in force. Provider changes update
asset, accent, and strings on the same bounded LVGL objects; they do not create
a second hidden Codex tree. This limits permanent LVGL pool pressure. Network
tasks never call LVGL and never hold the LVGL lock.

## Wi-Fi indicator behavior

The indicator is a shared platform component, not a Codex-only decoration.
It appears in the same top-right slot on Claude and Codex interaction screens
and follows the phone-first Wi-Fi design:

- strong/medium/weak connected states use progressively fewer arcs;
- disconnected uses the existing muted/error convention without flashing;
- setup mode may pulse only within the platform motion limits; and
- it displays connectivity only, not whether the Mac/PC or relay is alive.

The interaction screen may say `ON COMPUTER` or fall back normally when the
transport is unavailable; the signal icon must not imply end-to-end service
health.

## Failure behavior

- Codex package absent or disabled: Codex is byte-for-byte normal.
- Hook needs trust: Codex skips it and directs the user to `/hooks`; no panel
  decision is possible.
- Tokenserver stopped: helper exits quickly with no decision; Codex asks on
  the computer.
- Question tool unavailable: Codex uses native `request_user_input`.
- Panel or relay offline: live wait ends at the local deadline, then the
  computer prompt appears.
- Mac/PC asleep: no live request can be created or resolved.
- Detail disabled: the panel may signal that Codex is waiting but cannot
  approve or choose.
- Content too long, private, malformed, or unsupported: computer only.
- Duplicate, late, wrong-provider, wrong-key, or replayed verdict: rejected
  and logged without content.
- Claude and Codex wait concurrently: oldest live request is shown first;
  each verdict remains bound to its provider/request and cannot cross-resolve.
- Plugin update changes hooks: Codex requires the new hook hash to be reviewed
  before it runs.

## Implementation areas

The later implementation plan must cover these bounded areas:

1. refactor `tools/tokenserver/interactions.py` into provider-neutral state
   plus Claude/Codex response adapters;
2. add separate tokenserver provider switches, status, and configuration;
3. add the Codex permission command helper, question MCP server, SessionStart
   context, package manifest, installer, doctor, and uninstaller;
4. add `provider` and direct-verdict v2 to the LAN contract while preserving
   legacy Claude behavior;
5. extend the encrypted interaction relay's already approved exact-view
   contract with provider-aware requests and verdict checks;
6. parameterize the existing Needs You LVGL tree and policy for Claude/Codex,
   add the native 64 px Codex asset, and add the shared Wi-Fi indicator slot;
7. update setup, privacy, relay, agent, and troubleshooting documentation; and
8. update the numbers-only boundary test rationale without adding activity to
   the existing numbers Worker or `publisher.py`.

The dedicated interaction Worker remains separate from
`tools/relay/worker.js`. The numbers publisher remains numbers-only.

## Verification gates

### Host and contract tests

- official Codex hook fixtures for allow, deny, leave, timeout, malformed
  input, changed/unsupported fields, missing descriptions, and multiple-hook
  deny precedence;
- question MCP schema tests for exact recommendation, unmarked options,
  bounds, secrets/free-form rejection, timeout, and native-question fallback;
- provider-neutral store tests proving Claude/Codex output formats cannot
  cross and one verdict resolves only one request;
- installer tests in temporary Codex homes on macOS and Windows path shapes,
  including idempotent update and lossless uninstall;
- package discovery and hook trust diagnostics without bypassing trust;
- relay crypto vectors and wrong-provider/replay tests from the encrypted
  relay specification; and
- default-off/boundary tests proving a clone publishes no Codex activity and
  the existing numbers relay still has no activity route.

### Simulator visual tests

- exact 480 × 480 captures for Codex question, long question, approval,
  private, attract, payoff, strong/medium/weak/disconnected Wi-Fi, and Claude
  regression baselines;
- landmark checks for the coordinates and provider colors above;
- source-derived transparent icon checks that reject a white background or
  runtime-stretched asset;
- widest project, question, recommendation, description, command, and footer
  fixtures; and
- repeated provider switching and redraw under the 256 KiB LVGL pool with no
  allocation/assert loop.

### Physical panel acceptance — ota_1 only

1. Codex Desktop and CLI each produce one safe permission that can be allowed
   once, denied, and left to the computer.
2. Codex uses the VibePulse question tool for a short explicitly recommended
   choice; **APPROVE** returns the exact option and the task continues.
3. An unmarked, free-form, long, and multi-question case falls back to the
   computer without claiming a recommendation.
4. Claude interactions still render and resolve exactly as before.
5. Independent toggles prove Claude-only, Codex-only, both, and neither.
6. LAN direct and encrypted relay each work; a client-isolated Wi-Fi case
   succeeds over outbound HTTPS without router changes.
7. Wi-Fi loss, tokenserver restart, relay failure, timeout, duplicate tap,
   wrong key, and Mac sleep all fail safely.
8. Rotation, data arrival, OTA takeover, provider switching, and repeated
   interaction redraws do not wedge; memory/DMA health gates from the relay
   design remain green.

All hardware work targets `ota_1`. The v0.5.0 rollback image in `ota_0` is
never written, erased, reformatted, or selected as a test target.

## Acceptance summary

This design is complete when an open-source user can opt into Codex with one
reviewable setup; Codex Desktop and CLI can use the same panel; safe
permissions are one-time only; recommendations are explicit and come from
Codex rather than VibePulse; unsupported questions stay on the computer; the
approved Codex screen matches Claude's anchors without a white logo tile;
Claude/Codex/GitHub/relay choices remain independent; encrypted remote use
works across isolated Wi-Fi; failure never approves; and `ota_0` remains an
untouched rollback.
