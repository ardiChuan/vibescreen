#include "interaction_relay_crypto.h"

#include "mbedtls/base64.h"
#include "mbedtls/gcm.h"
#include "mbedtls/hkdf.h"
#include "mbedtls/md.h"
#include "mbedtls/platform_util.h"
#include "mbedtls/sha256.h"

#include <limits.h>
#include <stdio.h>
#include <string.h>

#define TK_IR_B64_TEMP_BYTES 3800u
#define TK_IR_REQUEST_CIPHERTEXT_BYTES \
  (TK_IR_REQUEST_FRAME_BYTES + TK_IR_TAG_BYTES)
#define TK_IR_VERDICT_CIPHERTEXT_BYTES \
  (TK_IR_VERDICT_FRAME_BYTES + TK_IR_TAG_BYTES)
#define TK_IR_STATUS_CIPHERTEXT_BYTES \
  (TK_IR_STATUS_FRAME_BYTES + TK_IR_TAG_BYTES)

static const uint8_t k_protocol[] = "vibepulse-ir/v1";
static const uint8_t k_salt_input[] = "VibePulse interaction relay v1";
static const uint8_t k_verdict_domain[] = "vibepulse-ir-verdict-v1";

typedef struct {
  const uint8_t *ciphertext;
  size_t ciphertext_len;
  const uint8_t *nonce;
  size_t nonce_len;
} outer_fields_t;

static void wipe(void *value, size_t len) {
  if (value != NULL && len != 0) mbedtls_platform_zeroize(value, len);
}

static bool fixed_ascii(const char *value, size_t len) {
  if (value == NULL) return false;
  for (size_t i = 0; i < len; ++i) {
    unsigned char c = (unsigned char)value[i];
    if (c == 0 || c < 0x21 || c > 0x7e) return false;
  }
  return value[len] == '\0';
}

static bool b64url_char(uint8_t value) {
  return (value >= 'A' && value <= 'Z') ||
         (value >= 'a' && value <= 'z') ||
         (value >= '0' && value <= '9') || value == '-' || value == '_';
}

static bool mailbox_valid(const char *mailbox) {
  if (!fixed_ascii(mailbox, 19) || mailbox[0] != 'v' ||
      mailbox[1] != 'p' || mailbox[2] != '_') {
    return false;
  }
  for (size_t i = 3; i < 19; ++i) {
    if (!b64url_char((uint8_t)mailbox[i])) return false;
  }
  return true;
}

static bool constant_equal(const uint8_t *left, const uint8_t *right,
                           size_t len) {
  uint8_t difference = 0;
  if (left == NULL || right == NULL) return false;
  for (size_t i = 0; i < len; ++i) difference |= left[i] ^ right[i];
  return difference == 0;
}

static int hex_value(unsigned char value) {
  if (value >= '0' && value <= '9') return value - '0';
  if (value >= 'a' && value <= 'f') return value - 'a' + 10;
  if (value >= 'A' && value <= 'F') return value - 'A' + 10;
  return -1;
}

static tk_ir_error_t decode_device_key(const char *hex, uint8_t out[32]) {
  if (hex == NULL || out == NULL) return TK_IR_ERR_ARGUMENT;
  for (size_t i = 0; i < 64; ++i) {
    if (hex[i] == '\0' || hex_value((unsigned char)hex[i]) < 0) {
      wipe(out, 32);
      return TK_IR_ERR_FORMAT;
    }
  }
  if (hex[64] != '\0') {
    wipe(out, 32);
    return TK_IR_ERR_FORMAT;
  }
  for (size_t i = 0; i < 32; ++i) {
    out[i] = (uint8_t)((hex_value((unsigned char)hex[i * 2]) << 4) |
                       hex_value((unsigned char)hex[i * 2 + 1]));
  }
  return TK_IR_OK;
}

tk_ir_error_t tk_ir_sha256(const uint8_t *input, size_t input_len,
                           uint8_t out[TK_IR_KEY_BYTES]) {
  if (out == NULL || (input == NULL && input_len != 0)) {
    if (out != NULL) wipe(out, TK_IR_KEY_BYTES);
    return TK_IR_ERR_ARGUMENT;
  }
  if (mbedtls_sha256(input, input_len, out, 0) != 0) {
    wipe(out, TK_IR_KEY_BYTES);
    return TK_IR_ERR_CRYPTO;
  }
  return TK_IR_OK;
}

void tk_ir_keys_zero(tk_ir_keys_t *keys) {
  if (keys != NULL) wipe(keys, sizeof *keys);
}

static tk_ir_error_t hkdf_label(const uint8_t device_key[32],
                                const uint8_t salt[32],
                                const char *mailbox, const char *label,
                                uint8_t out[32]) {
  uint8_t info[96];
  int length = snprintf((char *)info, sizeof info, "%s|%s|%s",
                        (const char *)k_protocol, mailbox, label);
  if (length < 0 || (size_t)length >= sizeof info) {
    wipe(info, sizeof info);
    return TK_IR_ERR_CAPACITY;
  }
  const mbedtls_md_info_t *sha = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  int result = sha == NULL ? -1 : mbedtls_hkdf(
      sha, salt, 32, device_key, 32, info, (size_t)length, out, 32);
  wipe(info, sizeof info);
  if (result != 0) {
    wipe(out, 32);
    return TK_IR_ERR_CRYPTO;
  }
  return TK_IR_OK;
}

tk_ir_error_t tk_ir_derive_keys(const char *device_key_hex,
                                const char *mailbox,
                                tk_ir_keys_t *out) {
  uint8_t device_key[32] = {0};
  uint8_t salt[32] = {0};
  tk_ir_error_t result = TK_IR_ERR_ARGUMENT;
  if (out == NULL) return result;
  tk_ir_keys_zero(out);
  if (!mailbox_valid(mailbox)) return TK_IR_ERR_FORMAT;
  result = decode_device_key(device_key_hex, device_key);
  if (result != TK_IR_OK) goto done;
  result = tk_ir_sha256(k_salt_input, sizeof k_salt_input - 1, salt);
  if (result != TK_IR_OK) goto done;
  result = hkdf_label(device_key, salt, mailbox, "mac-to-panel-aead",
                      out->request_aead);
  if (result != TK_IR_OK) goto done;
  result = hkdf_label(device_key, salt, mailbox, "panel-to-mac-aead",
                      out->verdict_aead);
  if (result != TK_IR_OK) goto done;
  result = hkdf_label(device_key, salt, mailbox, "panel-verdict-mac",
                      out->verdict_mac);
  if (result != TK_IR_OK) goto done;
  result = hkdf_label(device_key, salt, mailbox,
                      "mac-to-panel-status-aead", out->status_aead);
done:
  wipe(device_key, sizeof device_key);
  wipe(salt, sizeof salt);
  if (result != TK_IR_OK) tk_ir_keys_zero(out);
  return result;
}

tk_ir_error_t tk_ir_b64url_encode(const uint8_t *input, size_t input_len,
                                  char *out, size_t out_cap,
                                  size_t *out_len) {
  size_t written = 0;
  if (out_len != NULL) *out_len = 0;
  if (out == NULL || out_len == NULL ||
      (input == NULL && input_len != 0)) {
    return TK_IR_ERR_ARGUMENT;
  }
  if (mbedtls_base64_encode((uint8_t *)out, out_cap, &written,
                            input, input_len) != 0) {
    if (out_cap != 0) out[0] = '\0';
    return TK_IR_ERR_CAPACITY;
  }
  while (written != 0 && out[written - 1] == '=') --written;
  for (size_t i = 0; i < written; ++i) {
    if (out[i] == '+') out[i] = '-';
    if (out[i] == '/') out[i] = '_';
  }
  if (written >= out_cap) {
    if (out_cap != 0) out[0] = '\0';
    return TK_IR_ERR_CAPACITY;
  }
  out[written] = '\0';
  *out_len = written;
  return TK_IR_OK;
}

tk_ir_error_t tk_ir_b64url_decode(const char *input, size_t input_len,
                                  uint8_t *out, size_t out_cap,
                                  size_t *out_len,
                                  uint8_t *scratch, size_t scratch_cap) {
  tk_ir_error_t result = TK_IR_ERR_ARGUMENT;
  size_t written = 0;
  size_t encoded = 0;
  size_t padding = 0;
  if (out_len != NULL) *out_len = 0;
  if (out == NULL || out_len == NULL || scratch == NULL ||
      (input == NULL && input_len != 0)) {
    goto done;
  }
  if (input_len % 4 == 1) {
    result = TK_IR_ERR_FORMAT;
    goto done;
  }
  for (size_t i = 0; i < input_len; ++i) {
    if (!b64url_char((uint8_t)input[i])) {
      result = TK_IR_ERR_FORMAT;
      goto done;
    }
  }
  padding = (4 - input_len % 4) % 4;
  if (input_len > SIZE_MAX - padding - 1 ||
      scratch_cap < input_len + padding + 1) {
    result = TK_IR_ERR_CAPACITY;
    goto done;
  }
  for (size_t i = 0; i < input_len; ++i) {
    scratch[i] = input[i] == '-' ? '+' :
                 (input[i] == '_' ? '/' : (uint8_t)input[i]);
  }
  for (size_t i = 0; i < padding; ++i) scratch[input_len + i] = '=';
  scratch[input_len + padding] = '\0';
  int decoded = mbedtls_base64_decode(
      out, out_cap, &written, scratch, input_len + padding);
  if (decoded != 0) {
    result = decoded == MBEDTLS_ERR_BASE64_BUFFER_TOO_SMALL ?
             TK_IR_ERR_CAPACITY : TK_IR_ERR_FORMAT;
    goto done;
  }
  if (mbedtls_base64_encode(scratch, scratch_cap, &encoded,
                            out, written) != 0) {
    result = TK_IR_ERR_CAPACITY;
    goto done;
  }
  while (encoded != 0 && scratch[encoded - 1] == '=') --encoded;
  if (encoded != input_len) {
    result = TK_IR_ERR_FORMAT;
    goto done;
  }
  for (size_t i = 0; i < encoded; ++i) {
    uint8_t canonical = scratch[i] == '+' ? '-' :
                        (scratch[i] == '/' ? '_' : scratch[i]);
    if (canonical != (uint8_t)input[i]) {
      result = TK_IR_ERR_FORMAT;
      goto done;
    }
  }
  *out_len = written;
  result = TK_IR_OK;
done:
  if (result != TK_IR_OK && out != NULL && out_cap != 0) wipe(out, out_cap);
  if (scratch != NULL) wipe(scratch, scratch_cap);
  return result;
}

static bool consume(const uint8_t **cursor, const uint8_t *end,
                    const char *literal) {
  size_t len = strlen(literal);
  if ((size_t)(end - *cursor) < len || memcmp(*cursor, literal, len) != 0) {
    return false;
  }
  *cursor += len;
  return true;
}

static bool quoted_b64(const uint8_t **cursor, const uint8_t *end,
                       const uint8_t **value, size_t *len) {
  const uint8_t *start = *cursor;
  while (*cursor < end && **cursor != '"') {
    if (!b64url_char(**cursor)) return false;
    ++*cursor;
  }
  if (*cursor >= end || **cursor != '"') return false;
  *value = start;
  *len = (size_t)(*cursor - start);
  ++*cursor;
  return true;
}

static tk_ir_error_t parse_outer(const uint8_t *envelope, size_t len,
                                 outer_fields_t *out) {
  const uint8_t *cursor = envelope;
  const uint8_t *end = envelope + len;
  if (!consume(&cursor, end, "{\"ciphertext\":\"") ||
      !quoted_b64(&cursor, end, &out->ciphertext, &out->ciphertext_len) ||
      !consume(&cursor, end, ",\"nonce\":\"") ||
      !quoted_b64(&cursor, end, &out->nonce, &out->nonce_len) ||
      !consume(&cursor, end, ",\"v\":1}") || cursor != end) {
    return TK_IR_ERR_FORMAT;
  }
  return TK_IR_OK;
}

static tk_ir_error_t validate_request_id(const char *request_id,
                                         uint8_t raw[16]) {
  uint8_t scratch[32];
  size_t length = 0;
  if (!fixed_ascii(request_id, TK_IR_REQUEST_ID_CHARS)) {
    wipe(raw, 16);
    return TK_IR_ERR_FORMAT;
  }
  tk_ir_error_t result = tk_ir_b64url_decode(
      request_id, TK_IR_REQUEST_ID_CHARS, raw, 16, &length,
      scratch, sizeof scratch);
  if (result != TK_IR_OK || length != 16) {
    wipe(raw, 16);
    return TK_IR_ERR_FORMAT;
  }
  return TK_IR_OK;
}

static tk_ir_error_t make_aad(const char *mailbox, const char *request_id,
                              const char *suffix, uint8_t *out,
                              size_t cap, size_t *len) {
  uint8_t raw_id[16];
  if (!mailbox_valid(mailbox) ||
      validate_request_id(request_id, raw_id) != TK_IR_OK) {
    wipe(raw_id, sizeof raw_id);
    return TK_IR_ERR_FORMAT;
  }
  wipe(raw_id, sizeof raw_id);
  int written = snprintf((char *)out, cap, "%s|%s|%s|%s",
                         (const char *)k_protocol, mailbox,
                         request_id, suffix);
  if (written < 0 || (size_t)written >= cap) return TK_IR_ERR_CAPACITY;
  *len = (size_t)written;
  return TK_IR_OK;
}

static tk_ir_error_t make_status_aad(const char *mailbox, uint8_t *out,
                                     size_t cap, size_t *len) {
  if (!mailbox_valid(mailbox)) return TK_IR_ERR_FORMAT;
  int written = snprintf((char *)out, cap, "%s|%s|status",
                         (const char *)k_protocol, mailbox);
  if (written < 0 || (size_t)written >= cap) return TK_IR_ERR_CAPACITY;
  *len = (size_t)written;
  return TK_IR_OK;
}

static tk_ir_error_t gcm_decrypt_request(
    const tk_ir_keys_t *keys, const uint8_t nonce[TK_IR_NONCE_BYTES],
    const uint8_t *ciphertext, const uint8_t *aad, size_t aad_len,
    uint8_t *frame) {
  mbedtls_gcm_context context;
  mbedtls_gcm_init(&context);
  int result = mbedtls_gcm_setkey(
      &context, MBEDTLS_CIPHER_ID_AES, keys->request_aead, 256);
  if (result == 0) {
    result = mbedtls_gcm_auth_decrypt(
        &context, TK_IR_REQUEST_FRAME_BYTES,
        nonce, TK_IR_NONCE_BYTES, aad, aad_len,
        ciphertext + TK_IR_REQUEST_FRAME_BYTES, TK_IR_TAG_BYTES,
        ciphertext, frame);
  }
  mbedtls_gcm_free(&context);
  return result == 0 ? TK_IR_OK : TK_IR_ERR_AUTH;
}

static tk_ir_error_t gcm_decrypt_status(
    const tk_ir_keys_t *keys, const uint8_t nonce[TK_IR_NONCE_BYTES],
    const uint8_t *ciphertext, const uint8_t *aad, size_t aad_len,
    uint8_t *frame) {
  mbedtls_gcm_context context;
  mbedtls_gcm_init(&context);
  int result = mbedtls_gcm_setkey(
      &context, MBEDTLS_CIPHER_ID_AES, keys->status_aead, 256);
  if (result == 0) {
    result = mbedtls_gcm_auth_decrypt(
        &context, TK_IR_STATUS_FRAME_BYTES,
        nonce, TK_IR_NONCE_BYTES, aad, aad_len,
        ciphertext + TK_IR_STATUS_FRAME_BYTES, TK_IR_TAG_BYTES,
        ciphertext, frame);
  }
  mbedtls_gcm_free(&context);
  return result == 0 ? TK_IR_OK : TK_IR_ERR_AUTH;
}

static bool parse_u32(const uint8_t **cursor, const uint8_t *end,
                      uint32_t *value) {
  if (*cursor >= end || **cursor < '0' || **cursor > '9') return false;
  if (**cursor == '0' && *cursor + 1 < end && (*cursor)[1] >= '0' &&
      (*cursor)[1] <= '9') return false;
  uint64_t result = 0;
  while (*cursor < end && **cursor >= '0' && **cursor <= '9') {
    result = result * 10 + (uint64_t)(**cursor - '0');
    if (result > UINT32_MAX) return false;
    ++*cursor;
  }
  if (result == 0) return false;
  *value = (uint32_t)result;
  return true;
}

static tk_ir_error_t parse_request_frame(
    const uint8_t *frame, const char *request_id, tk_ir_request_t *out,
    uint8_t *b64_scratch, size_t b64_scratch_cap) {
  size_t json_len = ((size_t)frame[0] << 8) | frame[1];
  if (json_len == 0 || json_len > TK_IR_REQUEST_FRAME_BYTES - 2) {
    return TK_IR_ERR_FORMAT;
  }
  const uint8_t *cursor = frame + 2;
  const uint8_t *end = cursor + json_len;
  const uint8_t *challenge = NULL;
  const uint8_t *inner_id = NULL;
  const uint8_t *view = NULL;
  const uint8_t *digest = NULL;
  size_t challenge_len = 0, inner_id_len = 0, view_len = 0, digest_len = 0;
  if (!consume(&cursor, end, "{\"challenge\":\"") ||
      !quoted_b64(&cursor, end, &challenge, &challenge_len) ||
      !consume(&cursor, end, ",\"expiresAt\":") ||
      !parse_u32(&cursor, end, &out->expires_at) ||
      !consume(&cursor, end, ",\"requestId\":\"") ||
      !quoted_b64(&cursor, end, &inner_id, &inner_id_len) ||
      !consume(&cursor, end, ",\"v\":1,\"view\":\"") ||
      !quoted_b64(&cursor, end, &view, &view_len) ||
      !consume(&cursor, end, ",\"viewSha256\":\"") ||
      !quoted_b64(&cursor, end, &digest, &digest_len) ||
      !consume(&cursor, end, "}") || cursor != end ||
      inner_id_len != TK_IR_REQUEST_ID_CHARS ||
      memcmp(inner_id, request_id, TK_IR_REQUEST_ID_CHARS) != 0) {
    return TK_IR_ERR_FORMAT;
  }
  size_t decoded = 0;
  tk_ir_error_t result = tk_ir_b64url_decode(
      (const char *)challenge, challenge_len, out->challenge,
      sizeof out->challenge, &decoded, b64_scratch, b64_scratch_cap);
  if (result != TK_IR_OK || decoded != sizeof out->challenge) {
    return TK_IR_ERR_FORMAT;
  }
  result = tk_ir_b64url_decode(
      (const char *)view, view_len, out->view, sizeof out->view,
      &out->view_len, b64_scratch, b64_scratch_cap);
  if (result == TK_IR_ERR_CAPACITY) return TK_IR_ERR_FORMAT;
  if (result != TK_IR_OK || out->view_len == 0 ||
      out->view_len > TK_IR_MAX_VIEW_BYTES) {
    return TK_IR_ERR_FORMAT;
  }
  result = tk_ir_b64url_decode(
      (const char *)digest, digest_len, out->view_sha256,
      sizeof out->view_sha256, &decoded, b64_scratch, b64_scratch_cap);
  if (result != TK_IR_OK || decoded != sizeof out->view_sha256) {
    return TK_IR_ERR_FORMAT;
  }
  uint8_t calculated[32];
  result = tk_ir_sha256(out->view, out->view_len, calculated);
  if (result == TK_IR_OK &&
      !constant_equal(calculated, out->view_sha256, sizeof calculated)) {
    result = TK_IR_ERR_DIGEST;
  }
  wipe(calculated, sizeof calculated);
  if (result != TK_IR_OK) return result;
  memcpy(out->request_id, request_id, TK_IR_REQUEST_ID_CHARS + 1);
  return TK_IR_OK;
}

tk_ir_error_t tk_ir_decode_request(
    const tk_ir_keys_t *keys, const char *mailbox, const char *request_id,
    const uint8_t *envelope, size_t envelope_len, tk_ir_request_t *out,
    uint8_t *work, size_t work_cap) {
  tk_ir_error_t result = TK_IR_ERR_ARGUMENT;
  uint8_t nonce[TK_IR_NONCE_BYTES] = {0};
  uint8_t aad[128] = {0};
  size_t nonce_len = 0, cipher_len = 0, aad_len = 0;
  outer_fields_t fields = {0};
  if (out != NULL) wipe(out, sizeof *out);
  if (keys == NULL || mailbox == NULL || request_id == NULL ||
      envelope == NULL || out == NULL || work == NULL) {
    goto done;
  }
  if (work_cap < TK_IR_WORK_BYTES || envelope_len > TK_IR_MAX_ENVELOPE_BYTES) {
    result = TK_IR_ERR_CAPACITY;
    goto done;
  }
  uint8_t *b64 = work;
  uint8_t *ciphertext = work + TK_IR_B64_TEMP_BYTES;
  uint8_t *frame = ciphertext + TK_IR_REQUEST_CIPHERTEXT_BYTES;
  result = parse_outer(envelope, envelope_len, &fields);
  if (result != TK_IR_OK) goto done;
  result = tk_ir_b64url_decode(
      (const char *)fields.nonce, fields.nonce_len,
      nonce, sizeof nonce, &nonce_len, b64, TK_IR_B64_TEMP_BYTES);
  if (result != TK_IR_OK || nonce_len != sizeof nonce) {
    result = TK_IR_ERR_FORMAT;
    goto done;
  }
  result = tk_ir_b64url_decode(
      (const char *)fields.ciphertext, fields.ciphertext_len,
      ciphertext, TK_IR_REQUEST_CIPHERTEXT_BYTES, &cipher_len,
      b64, TK_IR_B64_TEMP_BYTES);
  if (result != TK_IR_OK || cipher_len != TK_IR_REQUEST_CIPHERTEXT_BYTES) {
    result = TK_IR_ERR_FORMAT;
    goto done;
  }
  result = make_aad(mailbox, request_id, "request", aad, sizeof aad, &aad_len);
  if (result != TK_IR_OK) goto done;
  result = gcm_decrypt_request(keys, nonce, ciphertext, aad, aad_len, frame);
  if (result != TK_IR_OK) goto done;
  result = parse_request_frame(
      frame, request_id, out, b64, TK_IR_B64_TEMP_BYTES);
done:
  wipe(nonce, sizeof nonce);
  wipe(aad, sizeof aad);
  if (work != NULL) wipe(work, work_cap);
  if (result != TK_IR_OK && out != NULL) wipe(out, sizeof *out);
  return result;
}

static uint32_t read_be32(const uint8_t *value) {
  return ((uint32_t)value[0] << 24) | ((uint32_t)value[1] << 16) |
         ((uint32_t)value[2] << 8) | (uint32_t)value[3];
}

static uint64_t read_be64(const uint8_t *value) {
  uint64_t result = 0;
  for (size_t i = 0; i < 8; ++i) result = (result << 8) | value[i];
  return result;
}

tk_ir_error_t tk_ir_decode_status(
    const tk_ir_keys_t *keys, const char *mailbox,
    const uint8_t *envelope, size_t envelope_len, tk_ir_status_t *out,
    uint8_t *work, size_t work_cap) {
  tk_ir_error_t result = TK_IR_ERR_ARGUMENT;
  uint8_t nonce[TK_IR_NONCE_BYTES] = {0};
  uint8_t aad[96] = {0};
  uint8_t calculated[TK_IR_KEY_BYTES] = {0};
  size_t nonce_len = 0, cipher_len = 0, aad_len = 0;
  outer_fields_t fields = {0};
  if (out != NULL) wipe(out, sizeof *out);
  if (keys == NULL || mailbox == NULL || envelope == NULL || out == NULL ||
      work == NULL) {
    goto done;
  }
  if (work_cap < TK_IR_WORK_BYTES || envelope_len > TK_IR_MAX_ENVELOPE_BYTES) {
    result = TK_IR_ERR_CAPACITY;
    goto done;
  }
  uint8_t *b64 = work;
  uint8_t *ciphertext = work + TK_IR_B64_TEMP_BYTES;
  uint8_t *frame = ciphertext + TK_IR_STATUS_CIPHERTEXT_BYTES;
  result = parse_outer(envelope, envelope_len, &fields);
  if (result != TK_IR_OK) goto done;
  result = tk_ir_b64url_decode(
      (const char *)fields.nonce, fields.nonce_len,
      nonce, sizeof nonce, &nonce_len, b64, TK_IR_B64_TEMP_BYTES);
  if (result != TK_IR_OK || nonce_len != sizeof nonce) {
    result = TK_IR_ERR_FORMAT;
    goto done;
  }
  result = tk_ir_b64url_decode(
      (const char *)fields.ciphertext, fields.ciphertext_len,
      ciphertext, TK_IR_STATUS_CIPHERTEXT_BYTES, &cipher_len,
      b64, TK_IR_B64_TEMP_BYTES);
  if (result != TK_IR_OK || cipher_len != TK_IR_STATUS_CIPHERTEXT_BYTES) {
    result = TK_IR_ERR_FORMAT;
    goto done;
  }
  result = make_status_aad(mailbox, aad, sizeof aad, &aad_len);
  if (result != TK_IR_OK) goto done;
  result = gcm_decrypt_status(keys, nonce, ciphertext, aad, aad_len, frame);
  if (result != TK_IR_OK) goto done;
  if (memcmp(frame, "VPS1", 4) != 0) {
    result = TK_IR_ERR_FORMAT;
    goto done;
  }
  out->publication_id = read_be64(frame + 4);
  out->expires_at = read_be32(frame + 12);
  out->status_len = ((size_t)frame[16] << 8) | frame[17];
  if (out->publication_id == 0 || out->expires_at == 0 ||
      out->status_len == 0 || out->status_len > TK_IR_MAX_STATUS_BYTES) {
    result = TK_IR_ERR_FORMAT;
    goto done;
  }
  memcpy(out->status_sha256, frame + 18, TK_IR_KEY_BYTES);
  memcpy(out->status, frame + 50, out->status_len);
  result = tk_ir_sha256(out->status, out->status_len, calculated);
  if (result == TK_IR_OK && !constant_equal(
          calculated, out->status_sha256, sizeof calculated)) {
    result = TK_IR_ERR_DIGEST;
  }
done:
  wipe(nonce, sizeof nonce);
  wipe(aad, sizeof aad);
  wipe(calculated, sizeof calculated);
  if (work != NULL) wipe(work, work_cap);
  if (result != TK_IR_OK && out != NULL) wipe(out, sizeof *out);
  return result;
}

static const char *verdict_name(tk_ir_verdict_t verdict) {
  switch (verdict) {
    case TK_IR_VERDICT_APPROVE: return "approve";
    case TK_IR_VERDICT_DENY: return "deny";
    case TK_IR_VERDICT_TERMINAL: return "terminal";
    case TK_IR_VERDICT_PANIC: return "panic";
    default: return NULL;
  }
}

static tk_ir_error_t validate_request(const tk_ir_request_t *request) {
  uint8_t raw_id[16];
  uint8_t digest[32];
  tk_ir_error_t result;
  if (request == NULL || request->expires_at == 0 || request->view_len == 0 ||
      request->view_len > sizeof request->view) {
    return TK_IR_ERR_FORMAT;
  }
  result = validate_request_id(request->request_id, raw_id);
  wipe(raw_id, sizeof raw_id);
  if (result != TK_IR_OK) return result;
  result = tk_ir_sha256(request->view, request->view_len, digest);
  if (result == TK_IR_OK && !constant_equal(
          digest, request->view_sha256, sizeof digest)) {
    result = TK_IR_ERR_DIGEST;
  }
  wipe(digest, sizeof digest);
  return result;
}

static tk_ir_error_t verdict_hmac_values(
    const tk_ir_keys_t *keys, const char *mailbox, const char *request_id,
    const uint8_t challenge[TK_IR_KEY_BYTES],
    const uint8_t view_sha256[TK_IR_KEY_BYTES], tk_ir_verdict_t verdict,
    uint8_t out[TK_IR_KEY_BYTES]) {
  uint8_t message[160] = {0};
  uint8_t raw_id[16] = {0};
  size_t offset = 0;
  tk_ir_error_t result = TK_IR_ERR_ARGUMENT;
  if (out != NULL) wipe(out, TK_IR_KEY_BYTES);
  const char *name = verdict_name(verdict);
  if (keys == NULL || mailbox == NULL || request_id == NULL ||
      challenge == NULL || view_sha256 == NULL || out == NULL) {
    goto done;
  }
  if (name == NULL || !mailbox_valid(mailbox)) {
    result = TK_IR_ERR_FORMAT;
    goto done;
  }
  result = validate_request_id(request_id, raw_id);
  if (result != TK_IR_OK) goto done;
  memcpy(message + offset, k_verdict_domain, sizeof k_verdict_domain);
  offset += sizeof k_verdict_domain;
  size_t mailbox_len = strlen(mailbox);
  message[offset++] = (uint8_t)(mailbox_len >> 8);
  message[offset++] = (uint8_t)mailbox_len;
  memcpy(message + offset, mailbox, mailbox_len);
  offset += mailbox_len;
  memcpy(message + offset, raw_id, sizeof raw_id);
  offset += sizeof raw_id;
  memcpy(message + offset, challenge, TK_IR_KEY_BYTES);
  offset += TK_IR_KEY_BYTES;
  memcpy(message + offset, view_sha256, TK_IR_KEY_BYTES);
  offset += TK_IR_KEY_BYTES;
  message[offset++] = (uint8_t)verdict;
  const mbedtls_md_info_t *sha = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  if (sha == NULL || mbedtls_md_hmac(
          sha, keys->verdict_mac, sizeof keys->verdict_mac,
          message, offset, out) != 0) {
    result = TK_IR_ERR_CRYPTO;
    goto done;
  }
  result = TK_IR_OK;
done:
  wipe(message, sizeof message);
  wipe(raw_id, sizeof raw_id);
  if (result != TK_IR_OK && out != NULL) wipe(out, TK_IR_KEY_BYTES);
  return result;
}

tk_ir_error_t tk_ir_verdict_hmac(
    const tk_ir_keys_t *keys, const char *mailbox,
    const tk_ir_request_t *request, tk_ir_verdict_t verdict,
  uint8_t out[TK_IR_KEY_BYTES]) {
  if (out != NULL) wipe(out, TK_IR_KEY_BYTES);
  if (request == NULL) return TK_IR_ERR_ARGUMENT;
  tk_ir_error_t result = validate_request(request);
  if (result != TK_IR_OK) return result;
  return verdict_hmac_values(keys, mailbox, request->request_id,
                             request->challenge, request->view_sha256,
                             verdict, out);
}

static tk_ir_error_t gcm_encrypt_verdict(
    const tk_ir_keys_t *keys, const uint8_t nonce[TK_IR_NONCE_BYTES],
    const uint8_t *aad, size_t aad_len, const uint8_t *frame,
    uint8_t *ciphertext) {
  mbedtls_gcm_context context;
  mbedtls_gcm_init(&context);
  int result = mbedtls_gcm_setkey(
      &context, MBEDTLS_CIPHER_ID_AES, keys->verdict_aead, 256);
  if (result == 0) {
    result = mbedtls_gcm_crypt_and_tag(
        &context, MBEDTLS_GCM_ENCRYPT, TK_IR_VERDICT_FRAME_BYTES,
        nonce, TK_IR_NONCE_BYTES, aad, aad_len, frame, ciphertext,
        TK_IR_TAG_BYTES, ciphertext + TK_IR_VERDICT_FRAME_BYTES);
  }
  mbedtls_gcm_free(&context);
  return result == 0 ? TK_IR_OK : TK_IR_ERR_CRYPTO;
}

tk_ir_error_t tk_ir_encode_verdict_binding(
    const tk_ir_keys_t *keys, const char *mailbox,
    const tk_ir_verdict_binding_t *binding, tk_ir_verdict_t verdict,
    tk_ir_random_fn random_fill, void *random_context,
    uint8_t *out, size_t out_cap, size_t *out_len,
    uint8_t *work, size_t work_cap) {
  uint8_t nonce[TK_IR_NONCE_BYTES] = {0};
  uint8_t mac[TK_IR_KEY_BYTES] = {0};
  uint8_t aad[128] = {0};
  char challenge[48] = {0};
  char digest[48] = {0};
  char hmac[48] = {0};
  char nonce_text[24] = {0};
  size_t challenge_len = 0, digest_len = 0, hmac_len = 0;
  size_t nonce_text_len = 0, cipher_text_len = 0, aad_len = 0;
  tk_ir_error_t result = TK_IR_ERR_ARGUMENT;
  if (out_len != NULL) *out_len = 0;
  if (out != NULL && out_cap != 0) wipe(out, out_cap);
  const char *name = verdict_name(verdict);
  if (keys == NULL || mailbox == NULL || binding == NULL || name == NULL ||
      random_fill == NULL || out == NULL || out_len == NULL || work == NULL) {
    if (name == NULL && keys != NULL && mailbox != NULL && binding != NULL &&
        random_fill != NULL && out != NULL && out_len != NULL && work != NULL) {
      result = TK_IR_ERR_FORMAT;
    }
    goto done;
  }
  if (work_cap < TK_IR_WORK_BYTES) {
    result = TK_IR_ERR_CAPACITY;
    goto done;
  }
  uint8_t raw_id[16];
  result = validate_request_id(binding->request_id, raw_id);
  wipe(raw_id, sizeof raw_id);
  if (result != TK_IR_OK || !mailbox_valid(mailbox)) {
    if (result == TK_IR_OK) result = TK_IR_ERR_FORMAT;
    goto done;
  }
  result = verdict_hmac_values(keys, mailbox, binding->request_id,
                               binding->challenge, binding->view_sha256,
                               verdict, mac);
  if (result != TK_IR_OK) goto done;
  result = tk_ir_b64url_encode(binding->challenge, sizeof binding->challenge,
                               challenge, sizeof challenge, &challenge_len);
  if (result != TK_IR_OK) goto done;
  result = tk_ir_b64url_encode(binding->view_sha256,
                               sizeof binding->view_sha256,
                               digest, sizeof digest, &digest_len);
  if (result != TK_IR_OK) goto done;
  result = tk_ir_b64url_encode(mac, sizeof mac, hmac, sizeof hmac, &hmac_len);
  if (result != TK_IR_OK) goto done;

  uint8_t *frame = work;
  uint8_t *ciphertext = frame + TK_IR_VERDICT_FRAME_BYTES;
  char *cipher_text = (char *)(ciphertext + TK_IR_VERDICT_CIPHERTEXT_BYTES);
  size_t cipher_text_cap = work_cap -
      (size_t)((uint8_t *)cipher_text - work);
  int json_len = snprintf(
      (char *)frame + 2, TK_IR_VERDICT_FRAME_BYTES - 2,
      "{\"challenge\":\"%s\",\"hmac\":\"%s\","
      "\"requestId\":\"%s\",\"v\":1,\"verdict\":\"%s\","
      "\"viewSha256\":\"%s\"}",
      challenge, hmac, binding->request_id, name, digest);
  if (json_len <= 0 || json_len > (int)TK_IR_VERDICT_FRAME_BYTES - 2) {
    result = TK_IR_ERR_CAPACITY;
    goto done;
  }
  frame[0] = (uint8_t)((unsigned)json_len >> 8);
  frame[1] = (uint8_t)json_len;
  if (!random_fill(random_context, nonce, sizeof nonce) ||
      !random_fill(random_context, frame + 2 + (size_t)json_len,
                   TK_IR_VERDICT_FRAME_BYTES - 2 - (size_t)json_len)) {
    result = TK_IR_ERR_RANDOM;
    goto done;
  }
  result = make_aad(mailbox, binding->request_id, "verdict",
                    aad, sizeof aad, &aad_len);
  if (result != TK_IR_OK) goto done;
  result = gcm_encrypt_verdict(
      keys, nonce, aad, aad_len, frame, ciphertext);
  if (result != TK_IR_OK) goto done;
  result = tk_ir_b64url_encode(
      ciphertext, TK_IR_VERDICT_CIPHERTEXT_BYTES,
      cipher_text, cipher_text_cap, &cipher_text_len);
  if (result != TK_IR_OK) goto done;
  result = tk_ir_b64url_encode(
      nonce, sizeof nonce, nonce_text, sizeof nonce_text, &nonce_text_len);
  if (result != TK_IR_OK) goto done;
  int total = snprintf((char *)out, out_cap,
                       "{\"ciphertext\":\"%s\",\"nonce\":\"%s\","
                       "\"v\":1}", cipher_text, nonce_text);
  if (total < 0 || (size_t)total >= out_cap ||
      (size_t)total > TK_IR_MAX_ENVELOPE_BYTES) {
    result = TK_IR_ERR_CAPACITY;
    goto done;
  }
  *out_len = (size_t)total;
  result = TK_IR_OK;
done:
  wipe(nonce, sizeof nonce);
  wipe(mac, sizeof mac);
  wipe(aad, sizeof aad);
  wipe(challenge, sizeof challenge);
  wipe(digest, sizeof digest);
  wipe(hmac, sizeof hmac);
  wipe(nonce_text, sizeof nonce_text);
  if (work != NULL) wipe(work, work_cap);
  if (result != TK_IR_OK) {
    if (out != NULL && out_cap != 0) wipe(out, out_cap);
    if (out_len != NULL) *out_len = 0;
  }
  return result;
}

tk_ir_error_t tk_ir_encode_verdict(
    const tk_ir_keys_t *keys, const char *mailbox,
    const tk_ir_request_t *request, tk_ir_verdict_t verdict,
    tk_ir_random_fn random_fill, void *random_context,
    uint8_t *out, size_t out_cap, size_t *out_len,
    uint8_t *work, size_t work_cap) {
  if (request == NULL) {
    if (out_len != NULL) *out_len = 0;
    if (out != NULL && out_cap != 0) wipe(out, out_cap);
    if (work != NULL) wipe(work, work_cap);
    return TK_IR_ERR_ARGUMENT;
  }
  tk_ir_error_t result = validate_request(request);
  if (result != TK_IR_OK) {
    if (out_len != NULL) *out_len = 0;
    if (out != NULL && out_cap != 0) wipe(out, out_cap);
    if (work != NULL) wipe(work, work_cap);
    return result;
  }
  tk_ir_verdict_binding_t binding = {0};
  memcpy(binding.request_id, request->request_id, sizeof binding.request_id);
  memcpy(binding.challenge, request->challenge, sizeof binding.challenge);
  memcpy(binding.view_sha256, request->view_sha256,
         sizeof binding.view_sha256);
  result = tk_ir_encode_verdict_binding(
      keys, mailbox, &binding, verdict, random_fill, random_context,
      out, out_cap, out_len, work, work_cap);
  wipe(&binding, sizeof binding);
  return result;
}
