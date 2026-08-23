<!-- GitHub-ready v0.7.0 release body. Intentionally starts without an H1. -->

VibePulse v0.7.0 closes the loop for both coding agents and makes the panel
far easier to move. Supported Claude Code **and Codex** questions can now be
answered from the glass, a phone can teach the panel a new Wi-Fi network, and
the tokenserver runs on Windows as well as macOS. When same-LAN access is not
possible, two separate opt-in relays can carry encrypted decisions and live
agent rows over ordinary internet Wi-Fi.

<p align="center">
  <img src="https://raw.githubusercontent.com/niclasvestlund-YT/vibepulse/v0.7.0/docs/img/vibepulse-needs-you-codex-question.png" width="31%" alt="Codex question on the VibePulse panel">
  &nbsp;
  <img src="https://raw.githubusercontent.com/niclasvestlund-YT/vibepulse/v0.7.0/docs/img/vibepulse-needs-you-codex-approval.png" width="31%" alt="Codex safe-command approval on the VibePulse panel">
  &nbsp;
  <img src="https://raw.githubusercontent.com/niclasvestlund-YT/vibepulse/v0.7.0/docs/img/vibepulse-wifi-setup.png" width="31%" alt="Phone-first Wi-Fi setup QR on the VibePulse panel">
</p>

## Highlights

- **Codex joins Needs You.** The optional VibePulse Codex plugin carries only
  supported two/three-option questions and a narrow safe-command tier to the
  panel. Unknown, mutating, secret-bearing, oversized, or ambiguous requests
  stay on the computer. Silence never means approval.
- **Phone-first Wi-Fi onboarding.** Scan the on-glass QR, choose a visible
  2.4 GHz network, and save it only after a successful join. The panel
  remembers six places while the networks in `secrets.h` remain an immutable
  recovery floor. Open networks are supported; captive portals and
  WPA2-Enterprise are not.
- **Needs You on unrelated Wi-Fi.** A user-owned Cloudflare Worker can carry
  fixed-size end-to-end encrypted request and verdict frames. Both sides make
  outbound HTTPS connections; there is no public computer, inbound port, VPN,
  or shared-LAN requirement.
- **Live agents on unrelated Wi-Fi.** A second independent switch can relay
  the minimized Claude/Codex activity rows. Direct LAN stays preferred and
  stale relay activity clears rather than pretending to be live.
- **Windows host support.** Claude credentials, Codex app-server reads,
  persistence, locking, state paths, and Task Scheduler autostart now have
  native Windows support. The current background task is health-checked via
  its root endpoint; run it in a terminal when a persistent diagnostic stream
  is needed. macOS behavior is unchanged.
- **A clearer connection state.** The neutral top-right Wi-Fi mark is shared
  across VibePulse, the launcher, Needs You, OTA, and setup. It reports the
  panel-to-access-point link only—not internet, tokenserver, or relay health.

## Independent and off by default

Claude interactions, Codex interactions, the numbers relay, the encrypted
interaction relay, the live agent status relay, and the GitHub page/star
notification remain separate choices. Installing the Codex plugin enables
none of them. The local-only setup still needs no VibePulse account and sends
no agent activity to a cloud service.

The encrypted paths expose network metadata such as connection IPs, timing,
mailbox identifiers, and fixed ciphertext sizes to Cloudflare. They do not
send question text, command text, project names, activity, or verdicts in
plaintext. See
[the relay privacy and setup guide](https://github.com/niclasvestlund-YT/vibepulse/blob/v0.7.0/docs/interaction-relay.md).

## Reliability work included

- Full host-gate coverage now runs in CI from the same tokenserver suite list
  used locally.
- Codex rejects non-weekly quota windows instead of labelling them weekly.
- The panel interaction task has an explicit stack budget for the bounded v2
  request view, and the encrypted relay build now selects its HKDF dependency.
- The numbers mailbox coordinates multiple publishers without list operations
  and caps cloud writes to protect the account-wide budget.
- Renewed Claude credentials are detected and published promptly instead of
  leaving a valid login behind stale cached data.
- Wi-Fi credentials are committed only after a fresh successful join; failed
  trials keep every previous recovery network intact.

## Upgrade and setup

Existing v0.6.0 installations can build the tag and use the normal
consent-gated A/B OTA path:

```sh
git switch --detach v0.7.0
. ~/esp/esp-idf/export.sh
idf.py build
tools/ota-flash.sh <device-ip>
```

The phone Wi-Fi flow is documented in
[docs/wifi.md](https://github.com/niclasvestlund-YT/vibepulse/blob/v0.7.0/docs/wifi.md).
Claude and Codex panel controls are installed through
[docs/agent-setup.md](https://github.com/niclasvestlund-YT/vibepulse/blob/v0.7.0/docs/agent-setup.md).
The optional encrypted paths have their own pinned Python/Node dependencies
and reviewed setup in
[docs/interaction-relay.md](https://github.com/niclasvestlund-YT/vibepulse/blob/v0.7.0/docs/interaction-relay.md).
A fresh clone keeps all interaction, relay, and GitHub choices off.

This release remains source-only. Do not attach `torget.bin`: a built image
contains the installer's Wi-Fi credentials and device key.
