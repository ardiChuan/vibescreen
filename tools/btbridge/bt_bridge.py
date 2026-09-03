#!/usr/bin/env python3
"""The Bluetooth half of the phone panel.

The ESP32 panel is an HTTP client on the LAN.  Over USB the phone can be
literally that (``adb reverse`` puts the tokenserver on the phone's own
loopback), so no bridge is needed.  Bluetooth has no HTTP: RFCOMM is a byte
stream.  This process accepts that stream, unpacks each framed request, makes
the *identical* HTTP call to the tokenserver, and frames the response back.

Nothing here interprets the payload.  It is a pipe, deliberately:

* the panel is read only, so the bridge forwards GETs and nothing else.  No
  answer route, no panic route, no signing;
* it forwards only an allowlisted set of tokenserver paths, so a stray or
  hostile connection cannot reach the loopback-only hook routes that Claude
  Code and Codex post to.

Wire format, shared with ``android/.../net/Frames.kt``::

    request : [4-byte big-endian length][UTF-8 {"method","path","body"}]
    response: [4-byte big-endian length][UTF-8 {"status","body"}]

RFCOMM is a stream, so framing is not optional: ``/api/agent-status`` runs to
roughly 3.5 KB and a "read until it goes quiet" loop truncates it
intermittently, which looks exactly like a JSON parse bug.

Usage::

    python tools/btbridge/bt_bridge.py
    python tools/btbridge/bt_bridge.py --channel 5 --tokenserver http://127.0.0.1:8737

Pair the phone with this computer first.  The channel this manages to bind is
printed at startup -- enter that number in the app's settings, because Windows
offers no way to publish an SDP record from the standard library, so the phone
connects to a channel number directly rather than discovering it.
"""
import argparse
import json
import socket
import struct
import sys
import threading
import urllib.error
import urllib.request

# Only what a panel legitimately needs.  The hook routes
# (/api/hook/..., /api/codex/...) are loopback-only on the tokenserver and are
# deliberately not reachable from here.
ALLOWED_GET = frozenset({
    "/", "/api/tokens", "/api/agent-status", "/api/max-tracker", "/api/github",
})
# The panel is informational: it never answers an agent, so the bridge carries
# no POST at all. This is not merely unused capability -- a bridge that could
# forward an answer route would be a way to reach it from off the machine.
ALLOWED_POST_PREFIX = None
ALLOWED_POST_EXACT = frozenset()

MAX_FRAME = 1 << 20
# The panel polls once a second; a request that outlives that is already stale.
HTTP_TIMEOUT_S = 5.0


def _read_exactly(sock, count):
    """RFCOMM hands back short reads. Loop until the frame is whole."""
    chunks = []
    remaining = count
    while remaining > 0:
        chunk = sock.recv(min(remaining, 4096))
        if not chunk:
            raise ConnectionError("peer closed mid-frame")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_frame(sock):
    (length,) = struct.unpack(">I", _read_exactly(sock, 4))
    if length > MAX_FRAME:
        raise ValueError(f"frame too large: {length}")
    return json.loads(_read_exactly(sock, length).decode("utf-8"))


def write_frame(sock, payload):
    body = json.dumps(payload).encode("utf-8")
    sock.sendall(struct.pack(">I", len(body)) + body)


def path_allowed(method, path):
    if method == "GET":
        return path in ALLOWED_GET
    return False


def forward(base, request):
    """One framed request -> one HTTP call -> one framed response."""
    method = request.get("method", "GET")
    path = request.get("path", "")
    body = request.get("body")

    if not isinstance(path, str) or not path.startswith("/"):
        return {"status": 400, "body": '{"error":"bad path"}'}
    if not path_allowed(method, path):
        # Refused here rather than passed on: the bridge's whole security
        # value is that it is narrower than the server behind it.
        return {"status": 403, "body": '{"error":"path not allowed over bluetooth"}'}

    data = body.encode("utf-8") if isinstance(body, str) else None
    req = urllib.request.Request(
        base.rstrip("/") + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as response:
            return {"status": response.status,
                    "body": response.read().decode("utf-8", "replace")}
    except urllib.error.HTTPError as exc:
        # A 409 carries the refusal reason the phone needs to show, so error
        # bodies are forwarded rather than collapsed.
        return {"status": exc.code,
                "body": exc.read().decode("utf-8", "replace")}
    except Exception as exc:  # noqa: BLE001 - reported to the phone, not raised
        return {"status": 0, "body": json.dumps({"error": str(exc)})}


def serve_client(conn, addr, base):
    print(f"[bridge] phone connected: {addr}", flush=True)
    try:
        while True:
            try:
                request = read_frame(conn)
            except (ConnectionError, OSError, ValueError, json.JSONDecodeError):
                break
            write_frame(conn, forward(base, request))
    finally:
        try:
            conn.close()
        except OSError:
            pass
        print(f"[bridge] phone disconnected: {addr}", flush=True)


def bind_channel(preferred):
    """Bind an RFCOMM channel, falling back when one is taken.

    Channel 1 is usually reserved and 2-3 are commonly occupied by the system's
    own profiles, so a fixed constant is not dependable. The channel that was
    actually bound is printed, because the phone must be told the number.
    """
    candidates = [preferred] + [c for c in (5, 11, 17, 23, 30) if c != preferred]
    last_error = None
    for channel in candidates:
        sock = socket.socket(
            socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        try:
            sock.bind((socket.BDADDR_ANY, channel))
            sock.listen(1)
            return sock, channel
        except OSError as exc:
            last_error = exc
            sock.close()
    raise SystemExit(f"could not bind any RFCOMM channel: {last_error}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--channel", type=int, default=5,
                        help="preferred RFCOMM channel (default: 5)")
    parser.add_argument("--tokenserver", default="http://127.0.0.1:8737",
                        help="tokenserver base URL (default: %(default)s)")
    args = parser.parse_args(argv)

    if not hasattr(socket, "AF_BLUETOOTH"):
        raise SystemExit("this Python build has no Bluetooth socket support")

    server, channel = bind_channel(args.channel)
    local = server.getsockname()[0]
    print(f"[bridge] listening on RFCOMM channel {channel} (adapter {local})")
    print(f"[bridge] forwarding to {args.tokenserver}")
    print(f"[bridge] enter address {local} and channel {channel} in the app")

    try:
        while True:
            conn, addr = server.accept()
            threading.Thread(
                target=serve_client, args=(conn, addr, args.tokenserver),
                daemon=True,
            ).start()
    except KeyboardInterrupt:
        print("\n[bridge] stopped")
    finally:
        server.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
