# VibePulse "Needs You" — Claude and Codex technical investigation

**Written:** 2026-08-15. **Status:** research and architecture only. No
implementation, no authorization, no flash implied, no capability promoted in
`spec/`.

> The question: can VibePulse become a physical human-in-the-loop interface for
> Claude Code — surfacing the moments Claude needs a human, letting you answer
> from the device, and letting the *same* session continue — without a second
> paid AI account, without secrets on the ESP32, and without weakening Claude
> Code's security model?

**Answer: YES**, and the one load-bearing unknown has since been settled by
experiment — see [Test Zero](#test-zero). Everything else is documented in the
current Claude Code docs, or was already verified against the shipped binary in
[`companion-features-brainstorm.md`](companion-features-brainstorm.md).

> **Status, 2026-08-16.** Test Zero **passed** and the loop is now built end to
> end in software. The bridge (stage 1) is `tools/tokenserver/interactions.py`
> plus the endpoints below; the device-side parser, policy, and the approved v2
> takeover screens are in `components/app_tokens/`; and the verdict now leaves
> the glass — a tap runs `needs_you_send_policy` (canonical message + portable
> HMAC, host-tested byte-for-byte against the bridge's `sign_answer`) through
> `needs_you_net` (a signed `esp_http_client` POST on a worker task). KEY3
> mid-hold-and-release panics; the 3 s hold still opens OTA, cleanly separated.
> Without a device key the sender compiles out and the screens stay
> display-only. **The wiring is done. What remains is physical:** verify touch
> and KEY3 on the named unit, ask the explicit flash question, then the static
> physical AMOLED review (`lv_arc` anti-aliasing and the mascot poses under the
> real panel). No board has been flashed.

This document supersedes nothing. It is the deeper follow-up to the "Can the
screen answer back?" section of the brainstorm, which reached the same
conclusion from the permissions side and whose verification work is reused here
rather than repeated.

## Current implementation addendum (2026-08-20)

The Claude-first investigation below is kept as the design record. The current
local implementation now supports both providers through one interaction store
and one LVGL object tree:

- Claude keeps its loopback HTTP question/permission hooks. The old
  `--interactions` flag is a legacy alias for Claude only.
- Codex uses a packaged `PermissionRequest` command hook plus a local stdio MCP
  question tool. Installation and enablement are separate; installing the
  plugin leaves Codex interactions off by default.
- Claude, Codex, detail-on-panel, legacy compatibility, numbers relay, the
  future interaction relay, and GitHub are independent choices. The guided
  lifecycle is `python3 tools/vibepulse_setup.py install`, then `status`,
  `doctor`, `disable`, or `uninstall` as needed.
- Every current Codex verdict is signed over protocol version, provider,
  request id, the SHA-256 digest of the exact rendered view, verdict, and
  timestamp. A legacy Claude v1 answer cannot resolve a Codex request.
- Codex offers **ALLOW ONCE** only inside a narrow safe-command tier. Unknown,
  mutating, secret-bearing, malformed, or visually incomplete requests use the
  computer fallback. Questions need two or three options with exactly one
  recommendation explicitly marked by Codex; VibePulse does not invent one.
- The computer must be on. The currently implemented activity/answer path is
  direct LAN, while the existing public relay remains numbers-only. A future
  encrypted interaction relay is a separate default-off design: end-to-end
  encrypt prompt content between computer and panel, keep a short TTL, and bind
  one-time signed verdicts to request id, view digest, and timestamp. It is not
  enabled by installing either provider adapter.

For Codex hook trust, run `/hooks`, review VibePulse's `SessionStart` and
`PermissionRequest` hooks, explicitly trust them, and **Start a new Codex task**.
The setup tool's doctor reports the state but never bypasses that review.
Uninstalling the Codex adapter preserves Claude, relays, GitHub, the device key,
and unrelated Codex settings. Legacy Claude v1 is insecure, Claude-only, and
off by default.

---

## The approved design direction (2026-08-16)

Five frames, exact 480 x 480, regenerated with
`python3 tools/mockups/gen_needsyou_v2.py`. **Approved by the owner as the
direction** after two expert critiques (small-display ergonomics; the
vibecoder's shelf-photo test) and a less-is-more audit. Approved as
*concepts*: the LVGL raster remains the visual authority, the LVGL captures
still need Studio approval, and nothing here authorizes a flash.

![Attract stage](img/mockups/needs-you-v2-attract.png)
![Question](img/mockups/needs-you-v2-question.png)
![Approval](img/mockups/needs-you-v2-approval.png)
![Private](img/mockups/needs-you-v2-private.png)
![Payoff](img/mockups/needs-you-v2-payoff.png)

What the direction locks:

- **Two-stage summon.** Stage A (attract) is the old alert's soul — mascot in
  a ring, one huge word — with the ring now a **depleting countdown**: the
  timer is pre-attentive, and the "118s left" text is gone. Any tap brings the
  decision screen. One dominant thing at both distances.
- **The mascot is back and emotes**, cell-accurate to the shipped asset,
  integer pixel scales only: asking (cocked eye, raised arm), alert
  (attract), happy chevron-eyes ^ ^ (payoff). It never begs, never sulks at a
  deny, never gestures at the recommended option.
- **Touch floor is law: every target ≥ 90 px** (the v1 screens undershot
  their own 7 mm floor by ~40%). APPROVE is a filled 96 px slab — outline
  pills vanish at distance. DENY is restrained red (`#E5484D`), a deliberate,
  contained break of the one-accent rule for the one destructive control, and
  exists **only where the command is readable**. LEAVE IT stays gray.
- **The payload is the hero and it is sacred**: the command in large Plex
  Mono directly on black, tool demoted to a chip; never decorated,
  paraphrased or truncated-for-a-joke. Personality lives in the chrome only.
- **Less is more, enforced**: no text under 14 px, no two lines carrying one
  idea, three type roles per screen, project name demoted into the eyebrow,
  the question footer is the honest option count ("1 MORE OPTION IN
  TERMINAL", from `options_total`).
- **The private screen has no buttons.** With nothing readable there is no
  decision: tap anywhere hands the prompt to the terminal immediately; the
  mascot renders at 60% so public-vs-private reads across the room by
  brightness; KEY3 long-press remains the emergency deny-everything.
  Blind-deny buttons were removed as a footgun.
- **The persuasion ceiling**: filled APPROVE directly under CLAUDE RECOMMENDS
  is the maximum acceptable nudge. No animation toward the button, no mascot
  gaze at it. The ring always maps to the real terminal-fallback time; the
  payoff's echo line is always the verbatim approved item. The payoff
  *animation* waits behind the motion gate; v2 ships it as a static beat.

### Superseded earlier concepts

`needs-you-question/options/done.png` under `img/mockups/` are the v1
concepts this direction replaces (kept for the record). The select-then-
confirm option list and the DONE/next-action screen remain future work and
will be redrawn in this design language when their stages arrive.

---

## 1. Why this is possible today

The three interactions map onto three different official mechanisms, all of
which exist now.

| Interaction | Mechanism | Status |
|---|---|---|
| **Approval** | `PermissionRequest` hook, `http` type, blocks for a structured verdict | **Verified** against shipped binary v2.1.231 (brainstorm doc) |
| **Question** | `PreToolUse` hook matching `AskUserQuestion`, answered via `updatedInput` | **Mirroring verified; answering needs [Test Zero](#test-zero)** |
| **Completion** | `Stop` / `StopFailure` hooks + a plugin MCP tool for curated actions | **Documented** |

The parts that sounded hardest turn out to be the native ones:

- **Claude already generates the options.** `AskUserQuestion` is a built-in
  tool whose input is 1–4 questions, each with a short `header` and 1–4 options
  carrying a `label` and a `description`. The A/B-with-rationale shape is
  literally the wire format. **No second model is needed to invent buttons.**
- **Hooks block and wait.** A held hook is not a hack; it is the documented
  execution model. The device's answer is the hook's return value.
- **The answer lands in the same live session**, because the session never
  stopped. No resume, no new process, no injected keystrokes.

---

## 2. Architecture

The bridge already exists — it is `tools/tokenserver`. Today it only reads
logs; this feature adds a loopback listener for hooks and an authenticated
answer path for the device.

```
  any project, unmodified CLAUDE.md, user runs `claude` as always
┌───────────────────────────────────────────────────────────────┐
│  Claude Code (interactive CLI / -p / Agent SDK)               │
│    · VibePulse plugin (config only — no daemon):              │
│        hooks: PermissionRequest, PreToolUse(AskUserQuestion), │
│               Stop, StopFailure, Notification                 │
│        MCP tool: vibepulse_handoff (strict schema)            │
│        skill: when to hand off, and when to say nothing       │
└──────────────┬────────────────────────────────────────────────┘
               │ http hooks → POST http://127.0.0.1:8737/…
               │ (loopback only — Claude Code blocks LAN hook URLs;
               │  the held response IS the pending interaction)
┌──────────────▼────────────────────────────────────────────────┐
│  tokenserver.py — the existing Mac service (launchd)          │
│    · already: tails ~/.claude logs → /api/agent-status (1 Hz) │
│    · new: hook listener (loopback) + pending-interaction store│
│    · new: LAN endpoints for the device:                       │
│        GET  /api/agent-status   ← now carries pending item    │
│        POST /api/interaction/<request_id>  (HMAC, one-shot)   │
└──────────────┬────────────────────────────────────────────────┘
               │ plain JSON over LAN, HMAC on the answer path
┌──────────────▼────────────────────────────────────────────────┐
│  ESP32-S3 AMOLED — thin UI/control client                     │
│    renders question/approval/done · sends one signed verdict  │
│    holds: WiFi creds + one revocable device key. Nothing else.│
└───────────────────────────────────────────────────────────────┘
```

Three properties make this shape correct rather than merely workable:

1. **The held HTTP response *is* the pending interaction.** The server mints a
   `request_id` and parks the connection; the device echoes that id back.
   Present → resolve that exact connection and delete it. Absent → reject,
   because it was already answered, timed out or superseded. There is no code
   path where a tap lands on a different prompt than the one it named, and
   idempotency on flaky WiFi comes free from delete-on-resolve.
2. **Fail-safe by construction.** A timed-out `PermissionRequest` hook is
   cancelled, its output discarded, and **no decision is rendered** — the normal
   terminal prompt appears. Ignoring the device costs nothing.
3. **Almost nothing new on the device.** The 1 Hz `/api/agent-status` poll that
   already drives NEEDS YOU carries the pending interaction. The only genuinely
   new device capability is one authenticated POST.

---

## 3. Event mapping

| Claude event | Mechanism | Data available | Can VibePulse respond? | Recommended UX |
|---|---|---|---|---|
| **Question** | `PreToolUse`, matcher `AskUserQuestion` | `session_id`, `cwd`, `tool_use_id`, full `questions[]` with labels + descriptions | **Yes** — `allow` + `updatedInput.answers` (see Test Zero) | Recommendation as hero + APPROVE + LEAVE IT |
| **Permission** | `PermissionRequest` | `tool_name`, full `tool_input`, `cwd`, `permission_mode`, `permission_suggestions` | **Yes** — `decision {behavior}`; deny rules still win | Full command in mono, or APPROVE disabled |
| **Normal work** | existing JSONL tailing | state, activity, model, effort, project | Display only | Existing live header; no change |
| **Failure** | `StopFailure`, matcher = error type | `rate_limit`, `server_error`, `billing_error`, … | Display; optional retry | FAILED; `rate_limit` → RATE LIMITED beside the reset countdown |
| **Completion** | `Stop` | `last_assistant_message`, `turn_number` | Display (never block Stop) | DONE ✓ + project |
| **Next action** | plugin MCP tool `vibepulse_handoff` | title, summary, verification, 0–2 actions | **Yes** — the choice returns as the tool result | At most two pills; zero is the default |
| **Attention nudge** | `Notification` (`permission_prompt`, `idle_prompt`, …) | notification type + session identity | No (cannot block, by design) | Belt-and-braces wake; never the answer channel |

---

## 4. AskUserQuestion — the proof

`PreToolUse` fires for `AskUserQuestion`, so the plugin's http hook receives,
on the live session, before the terminal picker renders:

```json
{
  "session_id": "e8a3c2d1-…",
  "cwd": "/Users/niclas/vibepulse",
  "hook_event_name": "PreToolUse",
  "tool_name": "AskUserQuestion",
  "tool_use_id": "toolu_01ABC…",
  "tool_input": {
    "questions": [{
      "question": "Which authentication approach should I use?",
      "header": "Auth",
      "multiSelect": false,
      "options": [
        { "label": "New auth layer (Recommended)", "description": "Cleaner architecture" },
        { "label": "Keep existing auth",           "description": "Smaller change" }
      ]
    }]
  }
}
```

The bridge parks this, shows it on the panel, and on APPROVE completes the held
response with:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "updatedInput": {
      "questions": [ "…unchanged…" ],
      "answers": { "Which authentication approach should I use?": "New auth layer (Recommended)" }
    }
  }
}
```

The same session continues with the answer. No resume, no new process, no API
call.

### The recommendation is already on the wire

Claude Code's convention is that a recommended option is listed **first** with
the literal suffix **`(Recommended)`** on its label. The bridge detects that
with a string match — deterministic, no AI, no guessing — which is what makes
the v1 screen possible. When no option carries the marker, the panel shows the
alert only and does not offer an answer; **it never invents a recommendation.**

### Test Zero

<a id="test-zero"></a>

Answering via `updatedInput` is **explicitly documented for the Agent SDK**
(`canUseTool` returns `allow` + an `answers` map). For the interactive CLI it is
documented neither way. This was the one unknown in the whole design, and v1
depended on it.

The test: a throwaway `PreToolUse` command hook matching `AskUserQuestion` that
logs the payload and answers with the **last** option — deliberately not the
recommendation, which Claude lists first, so the outcome could not be confused
with "Claude simply followed its own preference".

**Result: passed.** No picker rendered, and the session continued on the option
the hook supplied. An interactive Claude Code session therefore accepts an
answer from outside the terminal, which is what makes the panel an input device
rather than a notifier.

Two consequences worth stating plainly:

* v1 is the question flow, as scoped. The `PermissionRequest` fallback stays in
  the design as the approvals feature, not as a consolation prize.
* This behaviour is **not documented for the CLI**, so it is not a promise
  Anthropic has made. Treat it as verified-by-experiment on the installed
  version, keep the fallback path alive in code (every unanswerable payload
  already returns "no decision"), and re-run this test after Claude Code
  upgrades. A regression here degrades the panel to alert-only — it does not
  break a session.

---

## 5. Permissions — the verified path

```
Claude wants: Bash("npm test")
   │  PermissionRequest fires BEFORE the terminal prompt renders
   ▼
POST 127.0.0.1:8737  { tool_name, tool_input:{command:"npm test"}, cwd,
                       permission_mode, permission_suggestions, … }
   │  bridge parks it; terminal shows the spinner with the hook's
   │  statusMessage ("Waiting for VibePulse…")
   ▼
ESP32: APPROVAL REQUIRED · npm test · APPROVE / DENY / LEAVE IT
   │  tap → device POSTs {request_id, verdict, ts, hmac}
   ▼
bridge completes the held response:
  {"hookSpecificOutput":{"hookEventName":"PermissionRequest",
    "decision":{"behavior":"allow"}}}
   │
   ▼
Claude runs it and continues — same session, no interruption.
```

`behavior` is `allow`, `deny` (with a `message` Claude sees), or `ask`. An
optional `updatedPermissions` lets a "don't ask again" pill echo back one of the
`permission_suggestions`, behaving exactly like picking it in the terminal.
Returning **no** decision — LEAVE IT, or a timeout — falls through to the normal
prompt.

### Why this cannot weaken Claude Code's security model

- **Deny rules still win.** A hook returning `allow` cannot override a matching
  `permissions.deny` rule or an enterprise managed policy. Hooks tighten; they
  never loosen. Ship a recommended deny baseline (`rm -rf`, `sudo`,
  `curl … | sh`, force-push, `.env` writes) and the device **physically cannot**
  approve those — the worst-case authority is bounded by a settings file, not by
  our code being correct.
- **Timeout is fail-safe** (above). Nothing is approved by silence.
- **No double-offer.** The hook fires before the TUI prompt renders, so the
  device and the terminal are never both live for the same decision. This is the
  property `tmux send-keys` can never have.

---

## 6. Sessions, pausing and resuming

The reframe that matters: **for these flows you never pause and resume the
session at all.** The session is alive the whole time; the hook is a slow
function call and the answer is its return value. "The user replies two minutes
later" is just a held connection. Deferral only matters *past* the hook timeout,
and there the story differs by mode.

| Mode | Beyond the timeout | Verdict |
|---|---|---|
| **Interactive CLI** (the target) | Falls back to the terminal prompt, which waits indefinitely. If the terminal was killed: `claude --resume <session_id>` (cross-project since v2.1.223) or `claude -p --resume <id> "answer"` continues the same conversation. | **Works.** Zero workflow change; deferral bounded but fail-safe |
| **`claude -p`** | `permissionDecision: "defer"` exits with the tool call preserved so a wrapper can collect input and resume — officially supported deferral. | **Best deferral.** True walk-away |
| **Agent SDK** | `canUseTool` awaits with no timeout; documented AskUserQuestion answering; `resume` / `forkSession`. | **Cleanest API**, wrong default product fit — it replaces the TUI. Support, don't require |
| **Web / cloud** | Hooks run in Anthropic's cloud and cannot reach a home LAN. | **Out of scope** (see limitations) |
| **Desktop / IDE** | Same local hook config for CLI-backed sessions. | Should work; verify once |

**Multi-session support falls out for free.** Every hook payload carries
`session_id`, `transcript_path` and `cwd`, and `agent_status.py` already keys
agents by `sha256(sessionId)` with a per-provider job list. Pending interactions
are keyed `(session_id, tool_use_id)`; concurrent held hooks are just concurrent
parked connections, which `ThreadingHTTPServer` already handles. Sessions can be
named (`claude -n auth-refactor`). The "3 AGENTS" screen is a rendering job, not
an architecture change. Stale interactions expire with their hook; a tap on an
expired id is rejected, never re-routed.

---

## 7. Where good options come from

**Hybrid: A + D, with B for completion, C demoted to detection.** The rule that
keeps options good: *choices come from Claude's own in-session output, structure
comes from schemas, state comes from deterministic events. Nothing is generated
after the fact.*

| Approach | Verdict | Why |
|---|---|---|
| **A — native AskUserQuestion** | **Adopt** for blocked choices | Options are already generated, in context, labelled and capped at four by the tool itself. This is the entire "no second AI" answer. |
| **B — `vibepulse_handoff` MCP tool** | **Adopt** for completion | Strict schema: `state`, `title`, `summary`, `verification`, `actions` (`maxItems: 2`, may be empty), `risk`. The 0–2 rule is *schema-enforced*. The chosen action returns as the tool result, so the same session executes it. |
| **C — Stop hook forcing a handoff** | **Demote** to detection | `Stop` gives a deterministic DONE — use that. Blocking Stop to force UI turns every turn end into a potential loop (8-block cap, `stop_hook_active`) and fights the model. Never hold a session hostage for a screen. |
| **D — hooks only, deterministic** | **Adopt** as the floor | Everything except curated actions is deterministic. The device stays honest and useful even if Claude never calls the handoff tool. |
| **E — something better** | **No** | Surveyed and rejected: MCP elicitation (inverted direction), MCP channels (research preview; complements later), OTel spans (measurement, not control), `--permission-prompt-tool` (absent from current docs). |

**Deterministic:** state transitions, question and approval content, DONE,
FAILED, RATE_LIMITED, and verification facts the bridge can check itself.
**From Claude:** question options, and the 0–2 completion actions with their
summary line. Generic filler is excluded *structurally* — the schema has no
default actions, the skill says zero is preferred, and the bridge renders
nothing when actions are absent.

### The v1 scope decision

v1 renders **only** the recommended option plus APPROVE and LEAVE IT. This
deletes the option-list UI from the firmware entirely, removes the small-screen
legibility question from the first release, and matches how these prompts are
actually answered. Questions without a `(Recommended)` marker are alert-only in
v1. The full list is a v2 decision, informed by real usage.

### State model

Minimal, and every state mapped to a signal that actually exists. VERIFYING is
dropped (not reliably observable); NEEDS_YOU is split into its two real
variants; DONE_WITH_NEXT_ACTION becomes a *field* on DONE rather than a state.

| State | Source |
|---|---|
| `OFFLINE` | device-side poll failures (exists) |
| `IDLE` | no active sessions (exists) |
| `WORKING` | JSONL tail — activity, model, effort (exists) |
| `QUESTION` | held `PreToolUse(AskUserQuestion)` |
| `APPROVAL` | held `PermissionRequest` |
| `FAILED` | `StopFailure`, non-rate-limit matchers |
| `RATE_LIMITED` | `StopFailure` matcher `rate_limit` |
| `DONE` | `Stop`, enriched by `vibepulse_handoff` |

---

## 8. Plugin structure

A plugin can package everything except the daemon — and the daemon already
exists as a launchd service.

```
vibepulse-claude/
├── .claude-plugin/plugin.json     name, version, userConfig (bridge port +
│                                  token, sensitive → keychain)
├── hooks/hooks.json               http hooks → 127.0.0.1:8737, timeouts,
│                                  statusMessage
├── skills/vibepulse-handoff/      when to call the handoff tool; 0–2 actions;
│   └── SKILL.md                   zero is honest; no filler verbs
├── .mcp.json                      stdio server, ${CLAUDE_PLUGIN_ROOT}/server/…
├── server/vibepulse_mcp.py        stdlib Python; forwards to the bridge
└── scripts/ensure-bridge.sh       SessionStart: say so if the bridge is down
```

Installing the plugin wires **every** project the user opens — no per-project
`CLAUDE.md` edits. Distribution is a `marketplace.json` in this repo plus
`/plugin marketplace add`, so the target experience holds: install plugin, pair
device, run `claude` normally.

**Outside the plugin:** the tokenserver and its launchd job (already shipped),
the recommended `permissions.deny` baseline (a documented copy-paste block — the
user should own their deny rules; a plugin quietly editing permissions would be
wrong), and device pairing.

---

## 9. The bridge

Extend `tokenserver.py` rather than adding a second service: it already has the
launchd lifecycle, the LAN listener, the session identity model, the privacy
contract and a large test suite.

- **Hook listener on loopback.** Claude Code blocks http hooks that resolve to
  LAN or link-local addresses, so the loopback/LAN split is forced — and is the
  right design anyway. Parks held connections, mints `request_id`, enforces the
  per-type timeout.
- **Pending-interaction store.** `{request_id, kind, session, project, payload,
  expires_at}`, delete-on-resolve, one visible interaction at a time, ordered by
  the existing state priority.
- **Device API.** Pending item rides the existing 1 Hz `/api/agent-status`
  response as a new optional field (version-bumped; old firmware ignores it).
  Answers via `POST /api/interaction/<request_id>` with
  `{verdict, ts, hmac}`.
- **Verdict log.** Append-only: request id, tool, full input, decision, device
  id, timestamp. The answer to "did the shelf do that?"

**Protocol: keep HTTP polling plus one POST for v1; no WebSocket.** The 1 Hz
poll already exists on both ends and gives ≤1.5 s alert latency. The latency
that actually matters — the answer — is the POST, which is immediate. A second
transport with reconnect logic and new firmware surface is not worth sub-second
gains on a 120 s window.

### What is built locally

`tools/tokenserver/interactions.py` holds the store and the pure logic;
`tokenserver.py` exposes it. Independent saved switches gate Claude and Codex;
both are off in a fresh clone. `--interactions` remains a Claude-only legacy
alias, while `tools/vibepulse_setup.py` is the supported guided setup.

| Route | Who calls it | Behaviour |
|---|---|---|
| `POST /api/hook/question` | Claude Code, loopback only | parks a question, holds the connection, returns the answer |
| `POST /api/hook/permission` | Claude Code, loopback only | same, for approvals |
| `POST /api/codex/question` | local Codex MCP adapter, loopback only | normalizes one bounded question and returns its exact recommended answer or computer fallback |
| `POST /api/codex/permission` | local Codex command hook, loopback only | normalizes one permission and returns allow/deny or computer fallback |
| `POST /api/interaction/<id>` | the device, over the LAN | one v2 signed, provider/view-bound answer: `approve` / `deny` / `leave_it` |
| `POST /api/panic` | the device | signed panic stop: denies everything parked |
| `GET /api/agent-status` | the device | unchanged, plus an optional `pending` object |

Three details that are easy to get wrong and are therefore pinned by tests:

* **`pending` is a new optional ROOT key and `v` stays 2.** The shipped
  firmware checks the root's *required* keys and pins the version, but does not
  reject unknown root keys — so a panel running today's build keeps working.
* **Size is the real hazard, not schema.** Past `TK_AGENT_HTTP_BODY_CAP`
  (4096 bytes) the device discards the entire body, agent list included.
  `test/test_agent_status_body_capacity.py` reads that `#define` straight from
  the firmware header and asserts a worst-case snapshot *plus* a worst-case
  pending item stays under 75 % of it — and that an oversized pending item is
  dropped rather than allowed to take the agent list with it.
* **Every unknown returns "no decision"** (HTTP 200, empty body): a payload we
  cannot render, too many already parked, a crash in the handler, a timeout.
  The terminal then behaves exactly as it does today.
* **A dead client frees its slot at once.** A held hook watches its own
  connection (2 s poll bound) and is reaped the moment the session that asked
  hangs up — Ctrl-C, a closed terminal, a killed process. Found in external
  review: without this, a ghost prompt shadowed real ones for the rest of its
  timeout (oldest-first display) and enough of them filled the queue.
* **The port binds immediately on restart.** The first full log scan — minutes
  against a large history — now warms in the background instead of running
  before bind. Same review: `launchctl kickstart` used to mean a multi-minute
  window of connection-refused hooks, which fail safe but fail needlessly.
  Hooks and `/api/agent-status` are incremental and answer meaningfully at
  once; `/api/tokens` answers when the scan lands, and the panel shows its
  usual dashes until then.

**Try it without hardware.** `tools/fake-panel.py` polls at the device's own
1 Hz cadence, draws the interaction at panel proportions, and answers with the
same signed POST:

```sh
python3 tools/tokenserver/tokenserver.py --interactions --interaction-detail
python3 tools/fake-panel.py        # [a]pprove [d]eny [l]eave [p]anic
```

---

## 10. Threat model

Proportionate: a maker device on a home LAN whose worst honest failure must be
"someone stopped my agent", never "someone ran code".

| Risk | Mitigation |
|---|---|
| Device approves something dangerous | **Layer 0 is Claude Code itself**: `permissions.deny` and managed policies are evaluated regardless of hook output. Ship a deny baseline; the device cannot approve past it. |
| LAN peer forges an answer | Current v2 answer POSTs use HMAC-SHA256 over protocol version, provider, request id, exact view digest, verdict, and timestamp with a per-device key. Request ids are single-use and short-lived. Read endpoints remain unauthenticated local status data. |
| Approving unreadable text | If the command does not fit at 480 x 480, render it truncated and **disable APPROVE**. DENY always works. The honesty invariant, applied to a button. |
| Passer-by taps APPROVE | Risk tiers below, asymmetric buttons, optionally a KEY3 press to arm APPROVE (reusing the OTA consent language). |
| ESP32 stolen or compromised | Blast radius is WiFi credentials plus one device key. No Anthropic, GitHub or OAuth secrets ever reach the device. Revocation is deleting the key server-side. Worst case with a live key is approving tier-2 prompts until revoked. |
| Command text leaking to the panel | A deliberate, separately gated privacy widening: **off by default**, scoped to interaction screens only, documented in the README privacy section, never a side effect of enabling display features. |
| Pairing | First boot: the bridge prints a short-lived pairing code, confirmed on-device, and issues the device key. TLS on-LAN is possible but the self-signed certificate lifecycle outweighs the benefit; HMAC covers integrity and authenticity of verdicts. Reassess if payloads widen. |

**Risk tiers — what the device may decide**

| Tier | Examples | Device may |
|---|---|---|
| **0 · never routed** | matches the deny baseline: `rm -rf`, `sudo`, `curl…\|sh`, force-push, secrets, deploys | nothing — blocked before any hook decision |
| **1 · terminal only** | unrecognised Bash, writes outside cwd, MCP mutations, anything truncated | DENY and LEAVE IT (no APPROVE) |
| **2 · device-approvable** | question answers, allowlisted read-only/test/build commands, retry, handoff actions | APPROVE / DENY / LEAVE IT |

Routing uses hook matchers plus bridge-side classification as **noise
reduction** — matcher parsing is best-effort and can fail open, so the security
boundary stays deny rules plus tiering, never the matcher.

---

## 11. Limitations, stated critically

- **Interactive AskUserQuestion answering is unproven** — the only real risk to
  the headline demo. Test Zero decides it in ten minutes, and the fallback is
  still a good product.
- **Interactive deferral is bounded.** A held hook is not "safely paused"; the
  turn is waiting. Past the timeout the decision returns to the terminal and the
  device can no longer answer it — the panel should then say so. Open-ended
  deferral is official only for `-p` and SDK modes.
- **Answering is per-turn, not a conversation.** VibePulse can answer the
  question Claude asked; it cannot say "actually, do something else". That is
  the terminal's job. Scope, not defect.
- **`Stop` fires on every turn end**, not on task completion. DONE needs
  debouncing or it will flap mid-conversation; the handoff tool is the reliable
  "genuinely finished" signal.
- **Plugins cannot ship daemons.** The bridge stays a separately started
  service; a `SessionStart` hook makes "bridge down" honest.
- **Managed configs can disable the whole feature.** `allowedHttpHookUrls` and
  `allowManagedPermissionRulesOnly` can silently prevent http hooks. Detect and
  say so during setup rather than debugging a silent no-op.
- **Skill-steered handoff is probabilistic.** Claude will sometimes finish
  without calling the tool; the deterministic DONE floor keeps the panel honest.
- **Docs and binary drift.** `tool_use_id` appears in `PermissionRequest`
  payloads in the current docs, while the earlier binary check (v2.1.231) found
  none. Treat it as a bonus key when present; the server-minted `request_id`
  stays authoritative. Re-verify schemas against the installed binary at build
  time, ignore unknown fields, and fall back to LEAVE IT on anything
  unparseable.
- **Cloud and mobile sessions are invisible to the panel, and that is not
  fixable today.** Sessions started from the mobile app or claude.ai/code run on
  Anthropic infrastructure: they write no local transcript (only an explicit
  `claude --teleport` pulls one down), there is no documented API to list cloud
  sessions or their status from a local machine, and hooks and channels do not
  run in cloud sessions — so there is nothing for the bridge to observe. Three
  honest consequences: **quota already covers them** (cloud usage shares the
  account's rate limits, which the tokenserver's usage read captures — mobile
  work *does* move the quota pages, just not the live monitor); **attention is
  already handled natively** by the phone those sessions live on; and the
  panel's live-status scope is precisely "agents on this Mac", including
  teleported sessions, which become local on arrival. Say this in the README
  rather than half-supporting it. A public cloud-sessions API would make a
  bridge-side poller easy to add later.
- **macOS-only server** (unchanged; Linux and Windows tracked in #2 and #3).

---

## 12. MVP

Prove one magical interaction end to end:

1. **Test Zero** — ten minutes, no VibePulse code.
2. **Bridge slice** — loopback hook endpoint, parked connections, `request_id`
   store, HMAC-verified answer POST, pending item on `/api/agent-status`. Pure
   stdlib, host-tested like every other tokenserver module.
3. **Hooks config** — a hand-written settings snippet first; plugin packaging
   comes later.
4. **Device slice** — the v1 question screen: question line, recommendation
   card, APPROVE, LEAVE IT. Simulator first, exact 480 x 480 captures, physical
   review before any motion, **no flash without explicit authorization**.
5. **The loop** — ask Claude something ambiguous, walk to the shelf, tap
   APPROVE, watch the terminal continue.

If Test Zero fails, the same MVP with `PermissionRequest` and APPROVE/DENY:
already verified end to end, identical plumbing, identical screen geometry.
Either way the **panic stop** (KEY3 long-press → deny everything pending) rides
along nearly free and is the safest possible first physical input — it can only
ever say no.

---

## 13. Staged plan

| Stage | Content |
|---|---|
| **0 — verify** | Test Zero; re-verify the `PermissionRequest` schema against the installed binary; structured physical check of touch and KEY3, and promote them in `spec/` — the feature stands on an input path the registry still marks `unit_verified: unknown` |
| **1 — bridge core** | hook listener, pending store, HMAC device auth, pairing, verdict log, tests. No UI; a CLI fake device answers |
| **2 — one interaction on glass** | the MVP screen, plus the panic stop |
| **3 — approvals and safety** | risk tiers, deny baseline doc, truncation disables APPROVE, privacy switch, "don't ask again" via `permission_suggestions` |
| **4 — completion** | `Stop` / `StopFailure` states with debouncing, then `vibepulse_handoff` plus the skill |
| **5 — plugin packaging** | `.claude-plugin/`, `marketplace.json`, SessionStart bridge health, userConfig pairing, `docs/agent-setup.md` update |
| **6 — multi-session and polish** | provider-neutral queue and Codex adapters are now built; richer session naming and headless `defer` + resume remain later work |

---

## 14. Recommendation

**Build it.** This is a material improvement, not novelty.

The critical case first: quota displays are a crowded lane — this repo's own
competitive analysis found a shipped competitor on the *identical* panel — and a
passive NEEDS YOU alert still ends with you walking back to the terminal. The
target experience closes the loop every competitor leaves open: *walk away, get
tapped on the shoulder, decide from the shelf, Claude continues.* The same
analysis found that nobody has shipped approve-or-answer on a WiFi ESP32 panel;
Anthropic's own buddy is an explicitly unsupported BLE developer feature, and
AgentDeck's ESP32 fleet is output-only. This is an open surface, and the repo is
unusually well positioned for it: the bridge, the state classifier, the alert
UX, the consent culture and the honesty rules all already exist.

The honest risks: the interactive-answering unknown (day one); notification
fatigue if DONE debouncing is sloppy — the device earns trust by interrupting
only when a decision is genuinely waiting; and the approval surface is a real
security responsibility that ships **with** the deny baseline and the auth layer
or does not ship. None of these threatens the architecture.

> The terminal is where you talk to Claude. VibePulse is where Claude taps you
> on the shoulder — and where a two-option decision stops costing you a context
> switch.

---

## Sources

Current Claude Code documentation, fetched 2026-08-15:
[hooks](https://code.claude.com/docs/en/hooks.md) ·
[hooks guide](https://code.claude.com/docs/en/hooks-guide.md) ·
[tools reference](https://code.claude.com/docs/en/tools-reference.md) ·
[plugins reference](https://code.claude.com/docs/en/plugins-reference.md) ·
[plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces.md) ·
[MCP](https://code.claude.com/docs/en/mcp.md) ·
[skills](https://code.claude.com/docs/en/skills.md) ·
[sessions](https://code.claude.com/docs/en/sessions.md) ·
[Agent SDK: user input](https://code.claude.com/docs/en/agent-sdk/user-input.md) ·
[Agent SDK: sessions](https://code.claude.com/docs/en/agent-sdk/sessions.md) ·
[headless](https://code.claude.com/docs/en/headless.md) ·
[Claude Code on the web](https://code.claude.com/docs/en/claude-code-on-the-web.md) ·
[remote control](https://code.claude.com/docs/en/remote-control.md) ·
[channels](https://code.claude.com/docs/en/channels.md)

In-repo: [`companion-features-brainstorm.md`](companion-features-brainstorm.md)
(binary verification of the `PermissionRequest` path against v2.1.231),
`tools/tokenserver/agent_status.py`, `components/app_tokens/`, `spec/`.
