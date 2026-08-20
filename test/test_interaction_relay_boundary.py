#!/usr/bin/env python3
"""Privacy boundary for the separate encrypted interaction Worker."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "tools" / "interaction-relay"
source = "\n".join(
    path.read_text(encoding="utf-8")
    for path in sorted((SERVICE / "src").glob("*.ts"))
).lower()

# The cloud service knows transport envelopes and routing only. It has no
# plaintext activity schema or endpoint, even if the numbers relay is enabled.
for forbidden in (
    "agent-status", "hook", "session", "prompt", "command", "project",
    "question", "title", "subtitle", "answer",
):
    assert forbidden not in source, (
        f"encrypted Worker must not gain plaintext field/route {forbidden!r}"
    )

for required in (
    "nonce", "ciphertext", "envelope", "requestid", "expiresatms",
    "verdictatms", "cache-control", "no-store",
):
    assert required in source, f"missing opaque transport field {required!r}"

assert "request_ciphertext_bytes = 2048 + 16" in source
assert "verdict_ciphertext_bytes = 1024 + 16" in source
assert "const request_ttl_ms = 120_000" in source
assert "const max_live_requests = 8" in source
assert "console.log" in source
for leaked in ("mailbox: route.mailbox", "requestid: route.requestid"):
    assert leaked not in source, f"redacted Worker logs must not add {leaked}"

print("OK: the interaction Worker stores only bounded opaque envelopes")
