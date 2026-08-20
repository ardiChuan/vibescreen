#!/usr/bin/env python3
"""Small fail-closed JSON client for explicit HTTP loopback URLs."""

from __future__ import annotations

import http.client
import ipaddress
import json
import re
import urllib.error
import urllib.parse
import urllib.request


MAX_BODY_BYTES = 4096
CONNECT_TIMEOUT_SECONDS = 0.75
READ_TIMEOUT_SECONDS = 125.0
_IPV4_TEXT = re.compile(r"[0-9]+(?:\.[0-9]+){3}\Z")
_JSON_CONTENT_TYPE = re.compile(
    r'[ \t]*application/json[ \t]*'
    r'(?:;[ \t]*charset[ \t]*=[ \t]*(?:"(?:utf-8|ascii)"|utf-8|ascii)'
    r'[ \t]*)?\Z', re.IGNORECASE | re.ASCII)


def _reject_json_constant(value):
    raise ValueError(f"non-standard JSON constant: {value}")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object field")
        result[key] = value
    return result


def strict_json_loads(text):
    """Decode RFC JSON while rejecting duplicate fields and NaN values."""
    return json.loads(text, parse_constant=_reject_json_constant,
                      object_pairs_hook=_unique_object)


def is_loopback_http_url(url: object) -> bool:
    """Accept only canonical, explicit HTTP loopback URLs with a valid port."""
    if not isinstance(url, str) or not url or any(ord(char) < 32 for char in url):
        return False
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
        hostname = parsed.hostname
    except (TypeError, ValueError):
        return False
    if parsed.scheme != "http" or not parsed.netloc or not hostname:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if parsed.fragment or parsed.query or port is None or not 1 <= port <= 65535:
        return False
    if not parsed.path.startswith("/"):
        return False
    host = hostname.casefold()
    if host in {"localhost", "localhost."}:
        return True
    if host == "::1":
        return True
    if not _IPV4_TEXT.fullmatch(host):
        return False
    parts = host.split(".")
    if any(str(int(part)) != part for part in parts):
        return False
    try:
        address = ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError:
        return False
    return address.is_loopback


def _has_json_content_type(headers) -> bool:
    values = headers.get_all("Content-Type", [])
    if len(values) != 1:
        return False
    value = values[0]
    try:
        value.encode("ascii", errors="strict")
    except (AttributeError, UnicodeEncodeError):
        return False
    return _JSON_CONTENT_TYPE.fullmatch(value) is not None


class _SplitTimeoutHTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, read_timeout: float, **kwargs):
        self._read_timeout = read_timeout
        super().__init__(*args, **kwargs)

    def connect(self):
        super().connect()
        if self.sock is not None:
            self.sock.settimeout(self._read_timeout)


class _SplitTimeoutHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, read_timeout: float):
        super().__init__()
        self._read_timeout = read_timeout

    def http_open(self, request):
        def connection(host, **kwargs):
            return _SplitTimeoutHTTPConnection(
                host, read_timeout=self._read_timeout, **kwargs)

        return self.do_open(connection, request)


class _LoopbackRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if not is_loopback_http_url(newurl):
            raise urllib.error.HTTPError(
                request.full_url, code, "redirect left loopback", headers, fp)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def post_json(url: str, value: object, *,
              connect_timeout: float = CONNECT_TIMEOUT_SECONDS,
              read_timeout: float = READ_TIMEOUT_SECONDS):
    """POST a bounded object and return a bounded JSON object, or ``None``."""
    if not is_loopback_http_url(url) or not isinstance(value, dict):
        return None
    if not isinstance(connect_timeout, (int, float)) or connect_timeout <= 0:
        return None
    if not isinstance(read_timeout, (int, float)) or read_timeout <= 0:
        return None
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        if len(encoded) > MAX_BODY_BYTES:
            return None
        request = urllib.request.Request(
            url, data=encoded, method="POST",
            headers={"Content-Type": "application/json"})
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _SplitTimeoutHTTPHandler(float(read_timeout)),
            _LoopbackRedirectHandler(),
        )
        with opener.open(request, timeout=float(connect_timeout)) as response:
            if response.status != 200:
                return None
            if not _has_json_content_type(response.headers):
                return None
            length = response.headers.get("Content-Length")
            if length is not None and int(length) > MAX_BODY_BYTES:
                return None
            received = response.read(MAX_BODY_BYTES + 1)
        if len(received) > MAX_BODY_BYTES:
            return None
        decoded = received.decode("utf-8", errors="strict")
        result = strict_json_loads(decoded)
        return result if isinstance(result, dict) else None
    except Exception:
        return None
