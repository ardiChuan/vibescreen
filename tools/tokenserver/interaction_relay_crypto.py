"""Strict v1 crypto for the optional VibePulse interaction relay.

This module has no network, store, or tokenserver dependency.  Importing it is
therefore the explicit optional-dependency boundary for relay mode.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


REQUEST_FRAME_BYTES = 2048
VERDICT_FRAME_BYTES = 1024
STATUS_FRAME_BYTES = 2816
MAX_VIEW_BYTES = 640
MAX_STATUS_BYTES = 2560
MAX_ENVELOPE_BYTES = 4096
GCM_NONCE_BYTES = 12
GCM_TAG_BYTES = 16

_PROTOCOL = b"vibepulse-ir/v1"
_SALT = hashlib.sha256(b"VibePulse interaction relay v1").digest()
_MAILBOX_RE = re.compile(r"vp_[A-Za-z0-9_-]{16}\Z")
_HEX_KEY_RE = re.compile(r"[0-9A-Fa-f]{64}\Z")
_B64URL_RE = re.compile(r"[A-Za-z0-9_-]*\Z")
_OUTER_KEYS = frozenset(("v", "nonce", "ciphertext"))
_REQUEST_KEYS = frozenset((
    "v", "requestId", "challenge", "expiresAt", "view", "viewSha256",
))
_VERDICT_KEYS = frozenset((
    "v", "requestId", "challenge", "viewSha256", "verdict", "hmac",
))
_VERDICT_CODES = {"approve": 1, "deny": 2, "terminal": 3, "panic": 4}
_STATUS_MAGIC = b"VPS1"
_STATUS_HEADER_BYTES = 50


@dataclass(frozen=True)
class RelayKeys:
    request_aead: bytes
    verdict_aead: bytes
    verdict_mac: bytes
    status_aead: bytes


@dataclass(frozen=True)
class RelayRequest:
    request_id: str
    challenge: bytes
    expires_at: int
    view_bytes: bytes
    view_sha256: bytes


@dataclass(frozen=True)
class RelayVerdict:
    request_id: str
    challenge: bytes
    view_sha256: bytes
    verdict: str
    mac: bytes


@dataclass(frozen=True)
class RelayStatus:
    publication_id: int
    expires_at: int
    status_bytes: bytes
    status_sha256: bytes


def b64url_encode(raw: bytes) -> str:
    if not isinstance(raw, bytes):
        raise ValueError("base64url input must be bytes")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    if not isinstance(text, str) or not _B64URL_RE.fullmatch(text):
        raise ValueError("invalid base64url")
    if len(text) % 4 == 1:
        raise ValueError("invalid base64url length")
    try:
        decoded = base64.b64decode(
            text + "=" * ((4 - len(text) % 4) % 4),
            altchars=b"-_", validate=True,
        )
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid base64url") from exc
    if b64url_encode(decoded) != text:
        raise ValueError("non-canonical base64url")
    return decoded


def decode_device_key(hex_text: str) -> bytes:
    if not isinstance(hex_text, str) or not _HEX_KEY_RE.fullmatch(hex_text):
        raise ValueError("device key must be exactly 64 hexadecimal characters")
    return bytes.fromhex(hex_text)


def _mailbox_bytes(mailbox: str) -> bytes:
    if not isinstance(mailbox, str) or not _MAILBOX_RE.fullmatch(mailbox):
        raise ValueError("invalid mailbox")
    return mailbox.encode("ascii")


def _request_id_bytes(request_id: str) -> bytes:
    decoded = b64url_decode(request_id)
    if len(decoded) != 16:
        raise ValueError("request id must encode 16 bytes")
    return decoded


def _fixed_b64(text: str, size: int, name: str) -> bytes:
    value = b64url_decode(text)
    if len(value) != size:
        raise ValueError(f"{name} has the wrong size")
    return value


def derive_keys(device_key: bytes, mailbox: str) -> RelayKeys:
    if not isinstance(device_key, bytes) or len(device_key) != 32:
        raise ValueError("device key must be 32 bytes")
    mailbox_bytes = _mailbox_bytes(mailbox)

    def derive(label: bytes) -> bytes:
        return HKDF(
            algorithm=hashes.SHA256(), length=32, salt=_SALT,
            info=_PROTOCOL + b"|" + mailbox_bytes + b"|" + label,
        ).derive(device_key)

    return RelayKeys(
        request_aead=derive(b"mac-to-panel-aead"),
        verdict_aead=derive(b"panel-to-mac-aead"),
        verdict_mac=derive(b"panel-verdict-mac"),
        status_aead=derive(b"mac-to-panel-status-aead"),
    )


def request_aad(mailbox: str, request_id: str) -> bytes:
    mailbox_bytes = _mailbox_bytes(mailbox)
    _request_id_bytes(request_id)
    return (_PROTOCOL + b"|" + mailbox_bytes + b"|" +
            request_id.encode("ascii") + b"|request")


def verdict_aad(mailbox: str, request_id: str) -> bytes:
    mailbox_bytes = _mailbox_bytes(mailbox)
    _request_id_bytes(request_id)
    return (_PROTOCOL + b"|" + mailbox_bytes + b"|" +
            request_id.encode("ascii") + b"|verdict")


def status_aad(mailbox: str) -> bytes:
    return _PROTOCOL + b"|" + _mailbox_bytes(mailbox) + b"|status"


def _canonical_json(value: dict) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _object_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _decode_canonical_object(raw: bytes, keys: frozenset[str]) -> dict:
    if not isinstance(raw, bytes) or not raw:
        raise ValueError("invalid JSON")
    try:
        text = raw.decode("utf-8", "strict")
        value = json.loads(
            text, object_pairs_hook=_object_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ValueError("invalid JSON number")),
        )
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError,
            OverflowError) as exc:
        raise ValueError("invalid JSON") from exc
    if not isinstance(value, dict) or frozenset(value) != keys:
        raise ValueError("unexpected JSON shape")
    if _canonical_json(value) != raw:
        raise ValueError("non-canonical JSON")
    return value


def _padding_bytes(padding, size: int) -> bytes:
    if size < 0:
        raise ValueError("frame overflow")
    if padding is None:
        value = secrets.token_bytes(size)
    elif callable(padding):
        value = padding(size)
    else:
        value = padding
    if not isinstance(value, bytes) or len(value) != size:
        raise ValueError("padding has the wrong size")
    return value


def _frame(value: dict, frame_size: int, padding=None) -> bytes:
    encoded = _canonical_json(value)
    padding_size = frame_size - 2 - len(encoded)
    if len(encoded) > 0xFFFF or padding_size < 0:
        raise ValueError("frame overflow")
    return (len(encoded).to_bytes(2, "big") + encoded +
            _padding_bytes(padding, padding_size))


def _unframe(frame: bytes, frame_size: int, keys: frozenset[str]) -> dict:
    if not isinstance(frame, bytes) or len(frame) != frame_size:
        raise ValueError("invalid frame size")
    length = int.from_bytes(frame[:2], "big")
    if length == 0 or length > frame_size - 2:
        raise ValueError("invalid frame length")
    return _decode_canonical_object(frame[2:2 + length], keys)


def _outer_envelope(nonce: bytes, ciphertext: bytes) -> bytes:
    return _canonical_json({
        "v": 1,
        "nonce": b64url_encode(nonce),
        "ciphertext": b64url_encode(ciphertext),
    })


def _decode_outer(envelope: bytes, ciphertext_size: int) -> tuple[bytes, bytes]:
    if not isinstance(envelope, bytes) or not envelope or \
            len(envelope) > MAX_ENVELOPE_BYTES:
        raise ValueError("invalid envelope size")
    outer = _decode_canonical_object(envelope, _OUTER_KEYS)
    if type(outer["v"]) is not int or outer["v"] != 1:
        raise ValueError("unsupported envelope version")
    nonce = _fixed_b64(outer["nonce"], GCM_NONCE_BYTES, "nonce")
    ciphertext = _fixed_b64(
        outer["ciphertext"], ciphertext_size, "ciphertext")
    return nonce, ciphertext


def _validate_request_fields(request_id: str, challenge: bytes,
                             expires_at: int, view_bytes: bytes) -> bytes:
    _request_id_bytes(request_id)
    if not isinstance(challenge, bytes) or len(challenge) != 32:
        raise ValueError("challenge must be 32 bytes")
    # The ESP-IDF side parses JSON numbers through cJSON's double.  Pin the
    # protocol to uint32 Unix seconds so both languages preserve every value
    # exactly (and so overflow is rejected before encryption).
    if type(expires_at) is not int or not (0 < expires_at <= 0xFFFFFFFF):
        raise ValueError("invalid expiry")
    if not isinstance(view_bytes, bytes) or not (
            0 < len(view_bytes) <= MAX_VIEW_BYTES):
        raise ValueError("invalid view size")
    return hashlib.sha256(view_bytes).digest()


def encode_request(keys: RelayKeys, mailbox: str, request_id: str,
                   challenge: bytes, expires_at: int, view_bytes: bytes,
                   nonce: bytes | None = None, padding=None) -> bytes:
    if not isinstance(keys, RelayKeys):
        raise ValueError("invalid relay keys")
    _mailbox_bytes(mailbox)
    digest = _validate_request_fields(
        request_id, challenge, expires_at, view_bytes)
    nonce = secrets.token_bytes(GCM_NONCE_BYTES) if nonce is None else nonce
    if not isinstance(nonce, bytes) or len(nonce) != GCM_NONCE_BYTES:
        raise ValueError("nonce must be 12 bytes")
    value = {
        "v": 1,
        "requestId": request_id,
        "challenge": b64url_encode(challenge),
        "expiresAt": expires_at,
        "view": b64url_encode(view_bytes),
        "viewSha256": b64url_encode(digest),
    }
    frame = _frame(value, REQUEST_FRAME_BYTES, padding)
    ciphertext = AESGCM(keys.request_aead).encrypt(
        nonce, frame, request_aad(mailbox, request_id))
    return _outer_envelope(nonce, ciphertext)


def decode_request(keys: RelayKeys, mailbox: str, request_id: str,
                   envelope: bytes) -> RelayRequest:
    try:
        if not isinstance(keys, RelayKeys):
            raise ValueError("invalid relay keys")
        nonce, ciphertext = _decode_outer(
            envelope, REQUEST_FRAME_BYTES + GCM_TAG_BYTES)
        frame = AESGCM(keys.request_aead).decrypt(
            nonce, ciphertext, request_aad(mailbox, request_id))
        value = _unframe(frame, REQUEST_FRAME_BYTES, _REQUEST_KEYS)
        if type(value["v"]) is not int or value["v"] != 1:
            raise ValueError("unsupported request version")
        if value["requestId"] != request_id:
            raise ValueError("request id mismatch")
        challenge = _fixed_b64(value["challenge"], 32, "challenge")
        view = b64url_decode(value["view"])
        digest = _fixed_b64(value["viewSha256"], 32, "view digest")
        calculated = _validate_request_fields(
            request_id, challenge, value["expiresAt"], view)
        if not hmac.compare_digest(digest, calculated):
            raise ValueError("view digest mismatch")
        return RelayRequest(
            request_id=request_id,
            challenge=challenge,
            expires_at=value["expiresAt"],
            view_bytes=view,
            view_sha256=digest,
        )
    except (InvalidTag, ValueError, TypeError, OverflowError) as exc:
        raise ValueError("invalid request envelope") from exc


def _validate_status_fields(publication_id: int, expires_at: int,
                            status_bytes: bytes) -> bytes:
    if type(publication_id) is not int or not (
            0 < publication_id <= 0xFFFFFFFFFFFFFFFF):
        raise ValueError("invalid publication id")
    if type(expires_at) is not int or not (0 < expires_at <= 0xFFFFFFFF):
        raise ValueError("invalid expiry")
    if not isinstance(status_bytes, bytes) or not (
            0 < len(status_bytes) <= MAX_STATUS_BYTES):
        raise ValueError("invalid status size")
    return hashlib.sha256(status_bytes).digest()


def encode_status(keys: RelayKeys, mailbox: str, publication_id: int,
                  expires_at: int, status_bytes: bytes,
                  nonce: bytes | None = None, padding=None) -> bytes:
    if not isinstance(keys, RelayKeys):
        raise ValueError("invalid relay keys")
    digest = _validate_status_fields(
        publication_id, expires_at, status_bytes)
    nonce = secrets.token_bytes(GCM_NONCE_BYTES) if nonce is None else nonce
    if not isinstance(nonce, bytes) or len(nonce) != GCM_NONCE_BYTES:
        raise ValueError("nonce must be 12 bytes")
    padding_size = STATUS_FRAME_BYTES - _STATUS_HEADER_BYTES - len(status_bytes)
    frame = (
        _STATUS_MAGIC +
        publication_id.to_bytes(8, "big") +
        expires_at.to_bytes(4, "big") +
        len(status_bytes).to_bytes(2, "big") +
        digest + status_bytes + _padding_bytes(padding, padding_size)
    )
    ciphertext = AESGCM(keys.status_aead).encrypt(
        nonce, frame, status_aad(mailbox))
    return _outer_envelope(nonce, ciphertext)


def decode_status(keys: RelayKeys, mailbox: str,
                  envelope: bytes) -> RelayStatus:
    try:
        if not isinstance(keys, RelayKeys):
            raise ValueError("invalid relay keys")
        nonce, ciphertext = _decode_outer(
            envelope, STATUS_FRAME_BYTES + GCM_TAG_BYTES)
        frame = AESGCM(keys.status_aead).decrypt(
            nonce, ciphertext, status_aad(mailbox))
        if len(frame) != STATUS_FRAME_BYTES or frame[:4] != _STATUS_MAGIC:
            raise ValueError("invalid status frame")
        publication_id = int.from_bytes(frame[4:12], "big")
        expires_at = int.from_bytes(frame[12:16], "big")
        status_len = int.from_bytes(frame[16:18], "big")
        if status_len > STATUS_FRAME_BYTES - _STATUS_HEADER_BYTES:
            raise ValueError("invalid status length")
        status_bytes = frame[50:50 + status_len]
        calculated = _validate_status_fields(
            publication_id, expires_at, status_bytes)
        digest = frame[18:50]
        if not hmac.compare_digest(digest, calculated):
            raise ValueError("status digest mismatch")
        return RelayStatus(
            publication_id=publication_id,
            expires_at=expires_at,
            status_bytes=status_bytes,
            status_sha256=digest,
        )
    except (InvalidTag, ValueError, TypeError, OverflowError) as exc:
        raise ValueError("invalid status envelope") from exc


def _validate_request_object(request: RelayRequest) -> None:
    if not isinstance(request, RelayRequest):
        raise ValueError("invalid relay request")
    calculated = _validate_request_fields(
        request.request_id, request.challenge, request.expires_at,
        request.view_bytes)
    if not isinstance(request.view_sha256, bytes) or \
            not hmac.compare_digest(calculated, request.view_sha256):
        raise ValueError("invalid relay request digest")


def _verdict_code(verdict: str) -> int:
    if not isinstance(verdict, str) or verdict not in _VERDICT_CODES:
        raise ValueError("unsupported verdict")
    return _VERDICT_CODES[verdict]


def verdict_mac_message(mailbox: str, request: RelayRequest,
                        verdict: str) -> bytes:
    _validate_request_object(request)
    mailbox_bytes = _mailbox_bytes(mailbox)
    code = _verdict_code(verdict)
    return (b"vibepulse-ir-verdict-v1\0" +
            len(mailbox_bytes).to_bytes(2, "big") + mailbox_bytes +
            _request_id_bytes(request.request_id) + request.challenge +
            request.view_sha256 + bytes((code,)))


def verdict_mac_bytes(keys: RelayKeys, mailbox: str, request: RelayRequest,
                      verdict: str) -> bytes:
    if not isinstance(keys, RelayKeys):
        raise ValueError("invalid relay keys")
    return hmac.new(
        keys.verdict_mac,
        verdict_mac_message(mailbox, request, verdict),
        hashlib.sha256,
    ).digest()


def encode_verdict(keys: RelayKeys, mailbox: str, request: RelayRequest,
                   verdict: str, nonce: bytes | None = None,
                   padding=None) -> bytes:
    _validate_request_object(request)
    nonce = secrets.token_bytes(GCM_NONCE_BYTES) if nonce is None else nonce
    if not isinstance(nonce, bytes) or len(nonce) != GCM_NONCE_BYTES:
        raise ValueError("nonce must be 12 bytes")
    mac = verdict_mac_bytes(keys, mailbox, request, verdict)
    value = {
        "v": 1,
        "requestId": request.request_id,
        "challenge": b64url_encode(request.challenge),
        "viewSha256": b64url_encode(request.view_sha256),
        "verdict": verdict,
        "hmac": b64url_encode(mac),
    }
    frame = _frame(value, VERDICT_FRAME_BYTES, padding)
    ciphertext = AESGCM(keys.verdict_aead).encrypt(
        nonce, frame, verdict_aad(mailbox, request.request_id))
    return _outer_envelope(nonce, ciphertext)


def decode_verdict(keys: RelayKeys, mailbox: str, request_id: str,
                   envelope: bytes) -> RelayVerdict:
    try:
        if not isinstance(keys, RelayKeys):
            raise ValueError("invalid relay keys")
        nonce, ciphertext = _decode_outer(
            envelope, VERDICT_FRAME_BYTES + GCM_TAG_BYTES)
        frame = AESGCM(keys.verdict_aead).decrypt(
            nonce, ciphertext, verdict_aad(mailbox, request_id))
        value = _unframe(frame, VERDICT_FRAME_BYTES, _VERDICT_KEYS)
        if type(value["v"]) is not int or value["v"] != 1:
            raise ValueError("unsupported verdict version")
        if value["requestId"] != request_id:
            raise ValueError("request id mismatch")
        challenge = _fixed_b64(value["challenge"], 32, "challenge")
        digest = _fixed_b64(value["viewSha256"], 32, "view digest")
        mac = _fixed_b64(value["hmac"], 32, "verdict HMAC")
        _verdict_code(value["verdict"])
        return RelayVerdict(
            request_id=request_id,
            challenge=challenge,
            view_sha256=digest,
            verdict=value["verdict"],
            mac=mac,
        )
    except (InvalidTag, ValueError, TypeError, OverflowError) as exc:
        raise ValueError("invalid verdict envelope") from exc


def verify_verdict_mac(keys: RelayKeys, mailbox: str, request: RelayRequest,
                       verdict: RelayVerdict) -> bool:
    try:
        if not isinstance(request, RelayRequest) or \
                not isinstance(verdict, RelayVerdict):
            return False
        if verdict.request_id != request.request_id or \
                not hmac.compare_digest(verdict.challenge,
                                        request.challenge) or \
                not hmac.compare_digest(verdict.view_sha256,
                                        request.view_sha256):
            return False
        expected = verdict_mac_bytes(
            keys, mailbox, request, verdict.verdict)
        return hmac.compare_digest(expected, verdict.mac)
    except (ValueError, TypeError, OverflowError):
        return False
