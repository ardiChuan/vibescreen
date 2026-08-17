#!/usr/bin/env python3
"""The relay carries numbers, never activity.

The relay is a mailbox on the internet, so whatever crosses it is readable
by anyone who learns the URL.  Quota percentages and reset times are dull.
Project names, question text and shell commands are not — and neither is the
device key's answer path, which must never be reachable from outside the
LAN.  Nothing in the compiler enforces that split, so it is asserted here.
"""

from pathlib import Path

root = Path(__file__).resolve().parents[1]
read = lambda p: (root / p).read_text(encoding="utf-8")

config = read("components/app_tokens/app_tokens_config.h")
net = read("components/app_tokens/net.c")
github = read("components/app_tokens/github_net.c")
agent = read("components/app_tokens/agent_net.c")
needs_you = read("components/app_tokens/needs_you_net.c")
http = read("components/torget_net/torget_http.c")
example = read("secrets.h.example")

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

# --- What may not cross: anything that names your work ------------------
for path, source in (("agent_net.c", agent), ("needs_you_net.c", needs_you)):
    assert "RELAY" not in source.upper(), (
        f"{path} must never reach the relay — it carries project names, "
        "question text and commands"
    )
    assert "failover" not in source, (
        f"{path} must not use the failover helper"
    )

# The device key answers only the LAN service.  A verdict posted into a
# mailbox would be a signed instruction sitting in public storage.
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

print("OK: the relay carries numbers, and activity stays on the LAN")
