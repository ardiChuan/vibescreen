# Security policy

VibePulse reads local usage metadata, can expose a LAN service, and optionally
bridges bounded decisions to a physical panel. Please treat authentication,
request signing, relay encryption, permission handling, and privacy-boundary
bugs as security issues even when no prompt content is stored.

## Supported versions

Security fixes target the latest published release and `main`. Older releases
may receive documentation-only mitigations, but should not be assumed safe
after a fix ships.

## Report a vulnerability privately

Use **Security → Report a vulnerability** in the GitHub repository. Do not open
a public issue for a suspected vulnerability until the maintainer has had a
reasonable chance to investigate and publish a fix.

Never include any of the following in a report, screenshot, test fixture, or
log attachment:

- OAuth access or refresh tokens;
- the VibePulse device key, OTA token, relay bearer, or mailbox secret;
- Wi-Fi credentials or a committed `secrets.h`;
- raw prompts, messages, commands, session files, or account identifiers.

Use synthetic values and describe the minimum conditions needed to reproduce
the problem. Safe diagnostics include version/commit, operating system,
endpoint status codes, content-free health states, and redacted timestamps.

## Security invariants

- A timeout, missing panel, computer fallback, or silence is never approval.
- Provider, request, and exact-view bindings must be verified before a panel
  verdict is accepted.
- Unknown, mutating, secret-bearing, truncated, or ambiguous commands stay on
  the computer.
- Cloud transports remain independent, explicit, default-off choices.
- The plaintext numbers relay never carries agent activity or interaction
  content; the interaction/status relay carries only fixed-size ciphertext.
- Hooks and local decision ingress remain loopback-only; the panel posts only
  signed, bounded verdicts.
- Secrets never belong in firmware artifacts, releases, CI logs, process
  output, issues, or documentation.
