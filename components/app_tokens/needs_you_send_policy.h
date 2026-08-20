#ifndef NEEDS_YOU_SEND_POLICY_H
#define NEEDS_YOU_SEND_POLICY_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "needs_you_policy.h"

/* The pure half of the device's answer path: the exact bytes a verdict becomes
 * on the wire, host-testable so the panel and the bridge pin the same bytes.
 *
 * The signature is HMAC-SHA256 over "<request_id>|<verdict>|<ts>", keyed with
 * the device key STRING (the 64 hex characters themselves, exactly as
 * tools/tokenserver interactions.sign_answer keys it). The HMAC lives here, in
 * portable C, on purpose: the host gate has no mbedtls, and the only way to
 * prove the panel would send the same bytes the bridge verifies is to run the
 * identical code under test against the bridge's own vectors.
 *
 * Nothing here talks to the network or decides what may be sent — the takeover
 * already gated every verdict through tk_needs_you_allows before the app layer
 * reaches this. */

/* 64 lowercase hex + NUL. */
#define TK_NEEDS_YOU_HMAC_HEX_CAP 65
/* Largest v2 canonical message plus NUL, with explicit headroom. */
#define TK_NEEDS_YOU_MESSAGE_CAP 160
/* Largest v2 answer JSON plus NUL, with explicit headroom. */
#define TK_NEEDS_YOU_BODY_CAP 256

/* The wire name of a verdict, or NULL for one this build does not send. */
const char *tk_needs_you_verdict_name(tk_needs_you_verdict verdict);

/* The exact bytes the HMAC is taken over. Returns the length written, or -1 on
 * a bad argument or overflow (in which case nothing should be sent). */
int tk_needs_you_canonical_message(char *out, size_t cap,
                                   const char *request_id,
                                   const char *verdict_name, uint64_t ts);

/* v2 binds the answer to both provider and the exact public view rendered by
 * the panel. Codex answers always use this form; there is no v1 downgrade. */
int tk_needs_you_canonical_message_v2(
    char *out, size_t cap, const char *provider, const char *request_id,
    const char *view_sha256, const char *verdict_name, uint64_t ts);

/* HMAC-SHA256(key, message) as 64 lowercase hex plus NUL. `out` must hold
 * TK_NEEDS_YOU_HMAC_HEX_CAP bytes. */
void tk_needs_you_hmac_hex(char out[TK_NEEDS_YOU_HMAC_HEX_CAP],
                           const char *key, const char *message);

/* SHA-256 over an exact byte span, as 64 lowercase hex plus NUL. Shared with
 * the agent-status parser so the panel independently binds the public view it
 * decoded rather than trusting the digest supplied beside it. */
void tk_needs_you_sha256_hex(char out[TK_NEEDS_YOU_HMAC_HEX_CAP],
                             const void *data, size_t len);

/* The JSON body the device POSTs to /api/interaction/<request_id>. Returns the
 * length written, or -1 on a bad argument or overflow. */
int tk_needs_you_answer_body(char *out, size_t cap, const char *verdict_name,
                             uint64_t ts, const char *hmac_hex);

int tk_needs_you_answer_body_v2(
    char *out, size_t cap, const char *provider, const char *view_sha256,
    const char *verdict_name, uint64_t ts, const char *hmac_hex);

/* The JSON body the device POSTs to /api/panic. The signed message is always
 * "panic|deny|<ts>", so the body carries only ts and the signature. */
int tk_needs_you_panic_body(char *out, size_t cap, uint64_t ts,
                            const char *hmac_hex);

/* No client-side retry. A failed send leaves the takeover on the glass until
 * the service state changes; the bridge deletes on resolve, so a later human
 * tap is safe and a stale one is refused server-side. Always false — present so
 * the decision is stated, and tested, rather than implied by a missing loop. */
bool tk_needs_you_send_should_retry(int http_status);

#endif
