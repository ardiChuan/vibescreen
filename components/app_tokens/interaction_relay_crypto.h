#ifndef TK_INTERACTION_RELAY_CRYPTO_H
#define TK_INTERACTION_RELAY_CRYPTO_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define TK_IR_NONCE_BYTES 12u
#define TK_IR_TAG_BYTES 16u
#define TK_IR_KEY_BYTES 32u
#define TK_IR_REQUEST_ID_CHARS 22u
#define TK_IR_REQUEST_ID_CAP 23u
#define TK_IR_MAX_VIEW_BYTES 640u
#define TK_IR_REQUEST_FRAME_BYTES 2048u
#define TK_IR_VERDICT_FRAME_BYTES 1024u
#define TK_IR_MAX_ENVELOPE_BYTES 4096u

/* One caller-owned scratch region holds padded base64, ciphertext and the
 * authenticated fixed-size plaintext frame. It is wiped on every return. */
#define TK_IR_WORK_BYTES 6912u

typedef enum {
  TK_IR_OK = 0,
  TK_IR_ERR_ARGUMENT,
  TK_IR_ERR_CAPACITY,
  TK_IR_ERR_FORMAT,
  TK_IR_ERR_AUTH,
  TK_IR_ERR_CRYPTO,
  TK_IR_ERR_DIGEST,
  TK_IR_ERR_RANDOM,
} tk_ir_error_t;

typedef enum {
  TK_IR_VERDICT_APPROVE = 1,
  TK_IR_VERDICT_DENY = 2,
  TK_IR_VERDICT_TERMINAL = 3,
  TK_IR_VERDICT_PANIC = 4,
} tk_ir_verdict_t;

typedef struct {
  uint8_t request_aead[TK_IR_KEY_BYTES];
  uint8_t verdict_aead[TK_IR_KEY_BYTES];
  uint8_t verdict_mac[TK_IR_KEY_BYTES];
} tk_ir_keys_t;

typedef struct {
  char request_id[TK_IR_REQUEST_ID_CAP];
  uint8_t challenge[TK_IR_KEY_BYTES];
  uint32_t expires_at;
  uint8_t view[TK_IR_MAX_VIEW_BYTES];
  size_t view_len;
  uint8_t view_sha256[TK_IR_KEY_BYTES];
} tk_ir_request_t;

/* Minimal authenticated request state carried through the UI. The panel
 * creates this only from a successfully decoded relay request; verdict wire
 * bytes bind exactly these three immutable values. */
typedef struct {
  char request_id[TK_IR_REQUEST_ID_CAP];
  uint8_t challenge[TK_IR_KEY_BYTES];
  uint8_t view_sha256[TK_IR_KEY_BYTES];
} tk_ir_verdict_binding_t;

typedef bool (*tk_ir_random_fn)(void *context, uint8_t *out, size_t len);

/* The device key must be exactly 64 hexadecimal characters. The mailbox is
 * the canonical vp_ plus 16 base64url characters. */
tk_ir_error_t tk_ir_derive_keys(const char *device_key_hex,
                                const char *mailbox,
                                tk_ir_keys_t *out);
void tk_ir_keys_zero(tk_ir_keys_t *keys);

/* Strict, canonical, unpadded base64url. Decode needs caller scratch because
 * Mbed TLS consumes padded standard base64; scratch is always wiped. */
tk_ir_error_t tk_ir_b64url_decode(const char *input, size_t input_len,
                                  uint8_t *out, size_t out_cap,
                                  size_t *out_len,
                                  uint8_t *scratch, size_t scratch_cap);
tk_ir_error_t tk_ir_b64url_encode(const uint8_t *input, size_t input_len,
                                  char *out, size_t out_cap,
                                  size_t *out_len);

tk_ir_error_t tk_ir_sha256(const uint8_t *input, size_t input_len,
                           uint8_t out[TK_IR_KEY_BYTES]);

/* Decrypt, authenticate, enforce canonical schemas, decode the bounded public
 * view, and verify its SHA-256. On failure `out` is all zero. */
tk_ir_error_t tk_ir_decode_request(
    const tk_ir_keys_t *keys, const char *mailbox, const char *request_id,
    const uint8_t *envelope, size_t envelope_len, tk_ir_request_t *out,
    uint8_t *work, size_t work_cap);

/* Bind the panel decision to mailbox, request ID, challenge, view digest and
 * one of the four protocol verdict codes. */
tk_ir_error_t tk_ir_verdict_hmac(
    const tk_ir_keys_t *keys, const char *mailbox,
    const tk_ir_request_t *request, tk_ir_verdict_t verdict,
    uint8_t out[TK_IR_KEY_BYTES]);

/* Build the fixed 1024-byte verdict frame, fill nonce and padding through the
 * injected RNG, authenticate with AES-256-GCM and emit canonical outer JSON.
 * Production callers inject an esp_fill_random-backed function; host tests
 * inject deterministic bytes. Scratch is wiped on every return. */
tk_ir_error_t tk_ir_encode_verdict(
    const tk_ir_keys_t *keys, const char *mailbox,
    const tk_ir_request_t *request, tk_ir_verdict_t verdict,
    tk_ir_random_fn random_fill, void *random_context,
    uint8_t *out, size_t out_cap, size_t *out_len,
    uint8_t *work, size_t work_cap);

/* Equivalent verdict encoder for the minimal binding copied through the UI.
 * It does not accept plaintext view bytes and therefore cannot accidentally
 * expose them on the tap path. */
tk_ir_error_t tk_ir_encode_verdict_binding(
    const tk_ir_keys_t *keys, const char *mailbox,
    const tk_ir_verdict_binding_t *binding, tk_ir_verdict_t verdict,
    tk_ir_random_fn random_fill, void *random_context,
    uint8_t *out, size_t out_cap, size_t *out_len,
    uint8_t *work, size_t work_cap);

#ifdef __cplusplus
}
#endif

#endif
