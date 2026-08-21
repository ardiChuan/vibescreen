#!/usr/bin/env python3
"""This existing numbers transport never carries activity.

The separate interaction transport is explicit opt-in and end-to-end
encrypted. This file protects the old public numbers Worker/publisher and the
direct LAN client from accidentally becoming an activity transport.
"""

from pathlib import Path
import plistlib

root = Path(__file__).resolve().parents[1]
read = lambda p: (root / p).read_text(encoding="utf-8")

config = read("components/app_tokens/app_tokens_config.h")
net = read("components/app_tokens/net.c")
github = read("components/app_tokens/github_net.c")
agent = read("components/app_tokens/agent_net.c")
needs_you = read("components/app_tokens/needs_you_net.c")
http = read("components/torget_net/torget_http.c")
example = read("secrets.h.example")
readme = read("README.md")
agent_setup = read("docs/agent-setup.md")
tokenserver_readme = read("tools/tokenserver/README.md")
interaction_guide = read("docs/interaction-relay.md")
interaction_worker_readme = read("tools/interaction-relay/README.md")
observability = read("docs/observability.md")
mac_service = read("tools/tokenserver/se.torget.tokenserver.plist")
windows_service = read("tools/tokenserver/install-windows-task.ps1")

# --- What may cross: numbers -------------------------------------------
for name in ("TK_TOKENS_RELAY_URL", "TK_MAX_TRACKER_RELAY_URL",
             "TK_GITHUB_RELAY_URL"):
    assert name in config, f"{name} must be derived in app_tokens_config.h"

# Undefined base must compile to NULL, so a clone without the opt-in keeps
# exactly today's behaviour instead of fetching a malformed URL.
assert "#else" in config and "TK_TOKENS_RELAY_URL      NULL" in config, (
    "without TK_VIBEPULSE_RELAY_URL every relay address must be NULL"
)
assert "torget_http_get_failover(TK_TOKENS_URL, TK_TOKENS_RELAY_URL" in net
assert "torget_http_get_failover(TK_MAX_TRACKER_URL" in net
assert "torget_http_get_failover(TK_GITHUB_URL" in github

# --- What may not cross the numbers transport: anything naming your work --
assert "RELAY" not in agent.upper()
assert "failover" not in agent
assert "failover" not in needs_you, (
    "direct verdicts must not enter the plaintext numbers failover helper"
)
assert "TK_VIBEPULSE_RELAY_URL" not in needs_you
assert "torget_cloud_io" not in needs_you
assert "tk_interaction_relay_queue_verdict" in needs_you, (
    "the only cloud handoff here is the separately encrypted transport"
)

# The direct verdict route stays on LAN; remote delivery belongs only to the
# separate encrypted client and must not enter the numbers failover helper.
assert "TK_VIBEPULSE_BASE_URL" in needs_you, (
    "the Needs You verdict must post to the LAN base URL"
)

# --- The failover helper itself -----------------------------------------
# A missing relay must be a plain fetch, not a special case each caller
# has to remember.
assert "if (!relay_url || !relay_url[0])" in http, (
    "a NULL/empty relay must degrade to a plain torget_http_get"
)
# Only the LAN attempt may fall onwards; a dead relay must not bounce back
# or two dead addresses spin a fetch in circles.
assert "tg_net_source_may_fall_back(source)" in http

# --- The opt-in stays opt-in -------------------------------------------
assert "/* #define TK_VIBEPULSE_RELAY_URL" in example, (
    "the relay must ship commented out — a fresh clone stays LAN-only"
)

# --- The same boundary, from the service side ---------------------------
# The publisher must have no way to send the activity endpoints, and the
# Worker must not accept them.  Three directions, one rule.
publisher = read("tools/tokenserver/publisher.py")
worker = read("tools/relay/worker.js")
for source, name in ((publisher, "publisher.py"), (worker, "worker.js")):
    assert "agent-status" not in source and "interaction" not in source, (
        f"{name} must never touch the activity endpoints"
    )
assert '"/api/tokens", "/api/max-tracker", "/api/github"' in worker, (
    "the Worker's endpoint allowlist must stay exactly the three number paths"
)

# --- Open-source feature choices stay independent and default-off --------
# These sentences are part of the setup contract, not marketing shorthand:
# installing one adapter must never silently widen what leaves the computer.
for heading in ("Claude interactions", "Codex interactions", "Numbers relay",
                "Interaction relay", "Live agent status relay", "GitHub"):
    assert heading in readme, (
        f"README must list {heading} as one independent switch"
    )
assert "Installing the Codex plugin does not enable Codex interactions" in readme
assert "--interactions` is a legacy alias for Claude only" in readme
assert "encrypted interaction relay" in readme.lower()
assert "off by default" in readme.lower()

# The live rows path is an independent, explicit E2E opt-in. It may name
# activity only inside fixed-size ciphertext and must never broaden the old
# plaintext numbers relay.
for source, name in ((readme, "README"),
                     (interaction_guide, "interaction guide")):
    for required in (
            "Live agent status relay", "computer must be awake",
            "end-to-end encrypted", "off by default"):
        assert required.lower() in source.lower(), (
            f"{name} must explain {required}"
        )
for required in (
        "relay enable-status --yes-e2e-cloud",
        "relay disable-status",
        "CONFIG_TK_VIBEPULSE_AGENT_STATUS_RELAY=y",
        "2,816-byte", "15 seconds", "20 seconds", "five seconds",
        "project basenames"):
    assert required.lower() in interaction_guide.lower(), (
        f"interaction guide must pin live-status contract: {required}"
    )
for required in (
        "PUT /v1/mailboxes/{box}/status",
        "GET /v1/mailboxes/{box}/status",
        "2,816", "20 seconds"):
    assert required in interaction_worker_readme, (
        f"Worker README must document status route/retention: {required}"
    )
for required in (
        "TK_VIBEPULSE_AGENT_STATUS_RELAY", "relay enable-status",
        "fixed-size ciphertext"):
    assert required in example, (
        f"secrets example must document live status: {required}"
    )
assert "status_polls_ok" in observability
assert "status_applied" in observability
assert "status_cleared" in observability

host_config = read("tools/tokenserver/vibepulse_config.py")
kconfig = read("main/Kconfig.projbuild")
assert "agent_status_relay: bool = False" in host_config
status_option = kconfig.split(
    "config TK_VIBEPULSE_AGENT_STATUS_RELAY", 1)[1]
assert "default n" in status_option.split("endmenu", 1)[0]

# A login service loads the saved interaction choices. Provider/detail choices
# do not belong in a visible, stale process command line.
plist = plistlib.loads(mac_service.encode("utf-8"))
assert plist["ProgramArguments"] == [
    "/usr/bin/python3", "-u", "tokenserver.py"
]
for source, name in ((mac_service, "macOS launchd template"),
                     (windows_service, "Windows Task Scheduler installer")):
    for forbidden in ("--interactions", "--claude-interactions",
                      "--codex-interactions", "--interaction-detail",
                      "--legacy-claude-panel-v1"):
        assert forbidden not in source, (
            f"{name} must load saved feature switches, not bake {forbidden} "
            "into its command line"
        )
    assert "saved config" in source.lower(), (
        f"{name} must explain that it starts from saved config"
    )

for guide, name in ((agent_setup, "agent setup"),
                    (tokenserver_readme, "tokenserver README")):
    assert "computer must be awake" in guide.lower(), (
        f"{name} must state the computer-on requirement plainly"
    )

# Windows autostart ships in-tree. The public guides must not keep telling
# people to hand-build a Task Scheduler entry after that installer exists.
assert "install-windows-task.ps1" in readme, (
    "README must link the shipped Windows Task Scheduler installer"
)
assert "install-windows-task.ps1" in tokenserver_readme, (
    "tokenserver README must document the Windows autostart installer"
)
assert "What is missing is **autostart**" not in readme
assert "Kvar på Windows: **autostart**" not in tokenserver_readme

print("OK: the numbers relay carries only numbers; activity uses a separate encrypted boundary")
