#!/usr/bin/env python3
"""Generate one temporary C fixture and run the real Mbed TLS boundary."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.tokenserver.interaction_relay_crypto import (
    REQUEST_FRAME_BYTES,
    b64url_decode,
    b64url_encode,
    decode_device_key,
    decode_request,
    decode_status,
    derive_keys,
    encode_verdict,
    request_aad,
    status_aad,
    verdict_mac_bytes,
)


VECTOR_PATH = ROOT / "test-vectors/interaction-relay-v1.json"
STATUS_VECTOR_PATH = ROOT / "test-vectors/agent-status-relay-v1.json"
MBED_SOURCES = (
    "aes.c", "base64.c", "cipher.c", "cipher_wrap.c", "constant_time.c",
    "gcm.c", "hkdf.c", "md.c", "platform.c", "platform_util.c",
    "sha256.c",
)


def c_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def outer(envelope: bytes) -> dict:
    return json.loads(envelope.decode("ascii"))


def encode_outer(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode(
        "ascii")


def authenticated_request(keys, mailbox, request_id, envelope, *,
                          mutate_value=None, mutate_frame=None):
    value = outer(envelope)
    nonce = b64url_decode(value["nonce"])
    frame = AESGCM(keys.request_aead).decrypt(
        nonce, b64url_decode(value["ciphertext"]),
        request_aad(mailbox, request_id))
    if mutate_frame is not None:
        changed = mutate_frame(frame)
    else:
        length = int.from_bytes(frame[:2], "big")
        inner = json.loads(frame[2:2 + length])
        inner = mutate_value(inner)
        encoded = json.dumps(
            inner, sort_keys=True, separators=(",", ":")).encode("ascii")
        assert len(encoded) <= REQUEST_FRAME_BYTES - 2
        changed = (len(encoded).to_bytes(2, "big") + encoded +
                   b"\xa5" * (REQUEST_FRAME_BYTES - 2 - len(encoded)))
    value["ciphertext"] = b64url_encode(AESGCM(keys.request_aead).encrypt(
        nonce, changed, request_aad(mailbox, request_id)))
    return encode_outer(value)


def authenticated_status(keys, mailbox, envelope, mutate_frame):
    value = outer(envelope)
    nonce = b64url_decode(value["nonce"])
    frame = AESGCM(keys.status_aead).decrypt(
        nonce, b64url_decode(value["ciphertext"]), status_aad(mailbox))
    changed = mutate_frame(bytearray(frame))
    value["ciphertext"] = b64url_encode(AESGCM(keys.status_aead).encrypt(
        nonce, bytes(changed), status_aad(mailbox)))
    return encode_outer(value)


def vector_values():
    vector = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))
    status_vector = json.loads(
        STATUS_VECTOR_PATH.read_text(encoding="utf-8"))
    inputs = vector["inputs"]
    expected = vector["expected"]
    keys = derive_keys(
        decode_device_key(inputs["deviceKeyHex"]), inputs["mailbox"])
    envelope = expected["requestEnvelopeUtf8"].encode("ascii")
    request = decode_request(
        keys, inputs["mailbox"], inputs["requestId"], envelope)
    request_outer = outer(envelope)
    ciphertext = b64url_decode(request_outer["ciphertext"])

    def changed_outer(**changes):
        return encode_outer({**request_outer, **changes}).decode("ascii")

    values = {
        "VECTOR_DEVICE_KEY_HEX": inputs["deviceKeyHex"],
        "VECTOR_MAILBOX": inputs["mailbox"],
        "VECTOR_REQUEST_ID": inputs["requestId"],
        "VECTOR_VIEW_UTF8": inputs["viewUtf8"],
        "VECTOR_REQUEST_ENVELOPE": expected["requestEnvelopeUtf8"],
        "VECTOR_REQUEST_KEY_HEX": expected["requestKeyHex"],
        "VECTOR_VERDICT_KEY_HEX": expected["verdictKeyHex"],
        "VECTOR_VERDICT_MAC_KEY_HEX": expected["verdictMacKeyHex"],
        "VECTOR_VIEW_SHA256_HEX": expected["viewSha256Hex"],
        "VECTOR_REQUEST_PADDED_B64": changed_outer(
            nonce=request_outer["nonce"] + "="),
        "VECTOR_REQUEST_NONCE_11": changed_outer(
            nonce=b64url_encode(bytes(range(11)))),
        "VECTOR_REQUEST_NONCE_13": changed_outer(
            nonce=b64url_encode(bytes(range(13)))),
        "VECTOR_REQUEST_SHORT_TAG": changed_outer(
            ciphertext=b64url_encode(ciphertext[:-1])),
        "VECTOR_REQUEST_BAD_TAG": changed_outer(
            ciphertext=b64url_encode(ciphertext[:-1] +
                                     bytes((ciphertext[-1] ^ 1,)))),
        "VECTOR_REQUEST_BAD_LENGTH": authenticated_request(
            keys, inputs["mailbox"], inputs["requestId"], envelope,
            mutate_frame=lambda frame: b"\xff\xff" + frame[2:]
        ).decode("ascii"),
        "VECTOR_REQUEST_UNKNOWN_KEY": authenticated_request(
            keys, inputs["mailbox"], inputs["requestId"], envelope,
            mutate_value=lambda value: {**value, "extra": 1}
        ).decode("ascii"),
        "VECTOR_REQUEST_BAD_CHALLENGE": authenticated_request(
            keys, inputs["mailbox"], inputs["requestId"], envelope,
            mutate_value=lambda value: {
                **value, "challenge": b64url_encode(b"x" * 31)}
        ).decode("ascii"),
        "VECTOR_REQUEST_OVERSIZED_VIEW": authenticated_request(
            keys, inputs["mailbox"], inputs["requestId"], envelope,
            mutate_value=lambda value: {
                **value, "view": b64url_encode(b"x" * 641),
                "viewSha256": b64url_encode(__import__("hashlib").sha256(
                    b"x" * 641).digest())}
        ).decode("ascii"),
        "VECTOR_REQUEST_BAD_DIGEST": authenticated_request(
            keys, inputs["mailbox"], inputs["requestId"], envelope,
            mutate_value=lambda value: {
                **value, "viewSha256": b64url_encode(b"\0" * 32)}
        ).decode("ascii"),
    }
    for verdict in ("approve", "deny", "terminal", "panic"):
        upper = verdict.upper()
        verdict_envelope = encode_verdict(
            keys, inputs["mailbox"], request, verdict,
            nonce=bytes.fromhex(inputs["verdictNonceHex"]),
            padding=lambda size: b"\xa5" * size)
        values[f"VECTOR_VERDICT_{upper}_ENVELOPE"] = \
            verdict_envelope.decode("ascii")
        values[f"VECTOR_VERDICT_{upper}_HMAC_HEX"] = verdict_mac_bytes(
            keys, inputs["mailbox"], request, verdict).hex()

    status_inputs = status_vector["inputs"]
    status_expected = status_vector["expected"]
    status_envelope = status_expected["statusEnvelopeUtf8"].encode("ascii")
    status_outer = outer(status_envelope)
    status_ciphertext = b64url_decode(status_outer["ciphertext"])

    def status_changed_outer(**changes):
        return encode_outer({**status_outer, **changes}).decode("ascii")

    def replace(start, end, value):
        def mutate(frame):
            frame[start:end] = value
            return frame
        return mutate

    values.update({
        "VECTOR_STATUS_UTF8": status_inputs["statusUtf8"],
        "VECTOR_STATUS_ENVELOPE": status_expected["statusEnvelopeUtf8"],
        "VECTOR_STATUS_KEY_HEX": status_expected["statusKeyHex"],
        "VECTOR_STATUS_SHA256_HEX": status_expected["statusSha256Hex"],
        "VECTOR_STATUS_BAD_TAG": status_changed_outer(
            ciphertext=b64url_encode(
                status_ciphertext[:-1] +
                bytes((status_ciphertext[-1] ^ 1,)))),
        "VECTOR_STATUS_SHORT_CIPHERTEXT": status_changed_outer(
            ciphertext=b64url_encode(status_ciphertext[:-1])),
        "VECTOR_STATUS_BAD_MAGIC": authenticated_status(
            keys, inputs["mailbox"], status_envelope,
            replace(0, 4, b"BAD!")).decode("ascii"),
        "VECTOR_STATUS_ZERO_PUBLICATION": authenticated_status(
            keys, inputs["mailbox"], status_envelope,
            replace(4, 12, b"\0" * 8)).decode("ascii"),
        "VECTOR_STATUS_ZERO_EXPIRY": authenticated_status(
            keys, inputs["mailbox"], status_envelope,
            replace(12, 16, b"\0" * 4)).decode("ascii"),
        "VECTOR_STATUS_ZERO_LENGTH": authenticated_status(
            keys, inputs["mailbox"], status_envelope,
            replace(16, 18, b"\0" * 2)).decode("ascii"),
        "VECTOR_STATUS_OVER_LENGTH": authenticated_status(
            keys, inputs["mailbox"], status_envelope,
            replace(16, 18, (2561).to_bytes(2, "big"))).decode("ascii"),
        "VECTOR_STATUS_BAD_DIGEST": authenticated_status(
            keys, inputs["mailbox"], status_envelope,
            replace(18, 50, b"\0" * 32)).decode("ascii"),
    })
    decoded_status = decode_status(keys, inputs["mailbox"], status_envelope)
    assert decoded_status.publication_id == status_inputs["publicationId"]
    return vector, status_vector, values


def locate_idf() -> Path:
    candidates = []
    if os.environ.get("IDF_PATH"):
        candidates.append(Path(os.environ["IDF_PATH"]))
    candidates.append(Path.home() / "esp" / "esp-idf")
    for candidate in candidates:
        if (candidate / "components/mbedtls/mbedtls/library/gcm.c").is_file():
            return candidate.resolve()
    raise SystemExit("ESP-IDF with bundled Mbed TLS is required for C vectors")


def write_generated_header(path: Path, vector: dict, status_vector: dict,
                           values: dict):
    inputs = vector["inputs"]
    status_inputs = status_vector["inputs"]
    lines = [
        "#ifndef INTERACTION_RELAY_VECTOR_GENERATED_H",
        "#define INTERACTION_RELAY_VECTOR_GENERATED_H",
        f"#define VECTOR_EXPIRES_AT UINT32_C({inputs['expiresAt']})",
        "#define VECTOR_CHALLENGE {" + ",".join(
            f"0x{value:02x}" for value in bytes.fromhex(
                inputs["challengeHex"])) + "}",
        "#define VECTOR_VERDICT_NONCE {" + ",".join(
            f"0x{value:02x}" for value in bytes.fromhex(
                inputs["verdictNonceHex"])) + "}",
        f"#define VECTOR_STATUS_PUBLICATION_ID UINT64_C({status_inputs['publicationId']})",
        f"#define VECTOR_STATUS_EXPIRES_AT UINT32_C({status_inputs['expiresAt']})",
        "#define VECTOR_STATUS_NONCE {" + ",".join(
            f"0x{value:02x}" for value in bytes.fromhex(
                status_inputs["statusNonceHex"])) + "}",
    ]
    lines.extend(
        f"#define {name} {c_string(value)}" for name, value in values.items())
    lines.extend(("#endif", ""))
    path.write_text("\n".join(lines), encoding="utf-8")


def compile_and_run(temp: Path):
    idf = locate_idf()
    mbed = idf / "components/mbedtls/mbedtls"
    library = mbed / "library"
    config = temp / "torget_mbedtls_config.h"
    config.write_text("\n".join((
        "#define MBEDTLS_AES_C",
        "#define MBEDTLS_BASE64_C",
        "#define MBEDTLS_CIPHER_C",
        "#define MBEDTLS_GCM_C",
        "#define MBEDTLS_HKDF_C",
        "#define MBEDTLS_MD_C",
        "#define MBEDTLS_PLATFORM_C",
        "#define MBEDTLS_SHA256_C",
        "",
    )), encoding="ascii")
    common = [
        "-std=c11", "-O1",
        '-DMBEDTLS_CONFIG_FILE="torget_mbedtls_config.h"',
        "-I", str(temp), "-I", str(mbed / "include"),
        "-I", str(library),
    ]
    objects = []
    for name in MBED_SOURCES:
        output = temp / (name + ".o")
        subprocess.run([
            "cc", *common, "-w", "-c", str(library / name),
            "-o", str(output)], check=True)
        objects.append(output)
    binary = temp / "interaction-relay-crypto-test"
    subprocess.run([
        "cc", *common, "-Wall", "-Wextra", "-Werror",
        "-I", str(ROOT / "components/app_tokens"),
        str(ROOT / "components/app_tokens/interaction_relay_crypto.c"),
        str(ROOT / "test/test_interaction_relay_crypto.c"),
        *(str(value) for value in objects), "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)


def main():
    vector, status_vector, values = vector_values()
    with tempfile.TemporaryDirectory(prefix="torget-ir-c-vector-") as tmp:
        temp = Path(tmp)
        write_generated_header(
            temp / "interaction_relay_vector_generated.h", vector,
            status_vector, values)
        compile_and_run(temp)
    print("OK: Python and panel relay vectors are byte-identical")


if __name__ == "__main__":
    main()
