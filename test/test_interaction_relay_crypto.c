#include "interaction_relay_crypto.h"
#include "interaction_relay_vector_generated.h"

#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint8_t s_work[TK_IR_WORK_BYTES];

static bool all_zero(const uint8_t *value, size_t len) {
  for (size_t i = 0; i < len; ++i) {
    if (value[i] != 0) return false;
  }
  return true;
}

static void hex(char *out, size_t cap, const uint8_t *value, size_t len) {
  static const char digits[] = "0123456789abcdef";
  assert(cap >= len * 2 + 1);
  for (size_t i = 0; i < len; ++i) {
    out[i * 2] = digits[value[i] >> 4];
    out[i * 2 + 1] = digits[value[i] & 15];
  }
  out[len * 2] = '\0';
}

static bool deterministic_random(void *context, uint8_t *out, size_t len) {
  const uint8_t verdict_nonce[TK_IR_NONCE_BYTES] = VECTOR_VERDICT_NONCE;
  (void)context;
  if (len == sizeof verdict_nonce) {
    memcpy(out, verdict_nonce, len);
  } else {
    memset(out, 0xa5, len);
  }
  return true;
}

static bool failed_random(void *context, uint8_t *out, size_t len) {
  (void)context;
  memset(out, 0x5a, len);
  return false;
}

static void test_keys_and_base64(void) {
  tk_ir_keys_t keys;
  char actual[65];
  uint8_t decoded[32];
  size_t decoded_len = 0;
  char encoded[48];
  size_t encoded_len = 0;

  assert(tk_ir_derive_keys(VECTOR_DEVICE_KEY_HEX, VECTOR_MAILBOX, &keys) ==
         TK_IR_OK);
  hex(actual, sizeof actual, keys.request_aead, sizeof keys.request_aead);
  assert(strcmp(actual, VECTOR_REQUEST_KEY_HEX) == 0);
  hex(actual, sizeof actual, keys.verdict_aead, sizeof keys.verdict_aead);
  assert(strcmp(actual, VECTOR_VERDICT_KEY_HEX) == 0);
  hex(actual, sizeof actual, keys.verdict_mac, sizeof keys.verdict_mac);
  assert(strcmp(actual, VECTOR_VERDICT_MAC_KEY_HEX) == 0);

  memset(s_work, 0xcc, sizeof s_work);
  assert(tk_ir_b64url_decode(VECTOR_REQUEST_ID, strlen(VECTOR_REQUEST_ID),
                             decoded, sizeof decoded, &decoded_len,
                             s_work, sizeof s_work) == TK_IR_OK);
  assert(decoded_len == 16);
  assert(all_zero(s_work, sizeof s_work));
  assert(tk_ir_b64url_encode(decoded, decoded_len, encoded, sizeof encoded,
                             &encoded_len) == TK_IR_OK);
  assert(encoded_len == strlen(VECTOR_REQUEST_ID));
  assert(strcmp(encoded, VECTOR_REQUEST_ID) == 0);

  const char *invalid_b64[] = {"AA=", "AA==", "A", "+A", "/A", "AA\n"};
  for (size_t i = 0; i < sizeof invalid_b64 / sizeof invalid_b64[0]; ++i) {
    memset(s_work, 0xcc, sizeof s_work);
    assert(tk_ir_b64url_decode(invalid_b64[i], strlen(invalid_b64[i]),
                               decoded, sizeof decoded, &decoded_len,
                               s_work, sizeof s_work) == TK_IR_ERR_FORMAT);
    assert(all_zero(s_work, sizeof s_work));
  }

  char bad_key[66];
  memset(bad_key, '0', sizeof bad_key);
  bad_key[63] = '\0';
  assert(tk_ir_derive_keys(bad_key, VECTOR_MAILBOX, &keys) ==
         TK_IR_ERR_FORMAT);
  memset(bad_key, '0', 65);
  bad_key[65] = '\0';
  assert(tk_ir_derive_keys(bad_key, VECTOR_MAILBOX, &keys) ==
         TK_IR_ERR_FORMAT);
  memset(bad_key, 'g', 64);
  bad_key[64] = '\0';
  assert(tk_ir_derive_keys(bad_key, VECTOR_MAILBOX, &keys) ==
         TK_IR_ERR_FORMAT);
  tk_ir_keys_zero(&keys);
  assert(all_zero((const uint8_t *)&keys, sizeof keys));
}

static tk_ir_error_t decode_case(const tk_ir_keys_t *keys,
                                 const char *mailbox,
                                 const char *request_id,
                                 const char *envelope,
                                 tk_ir_request_t *request) {
  memset(s_work, 0xcc, sizeof s_work);
  tk_ir_error_t result = tk_ir_decode_request(
      keys, mailbox, request_id, (const uint8_t *)envelope, strlen(envelope),
      request, s_work, sizeof s_work);
  assert(all_zero(s_work, sizeof s_work));
  return result;
}

static void test_request_decode(void) {
  tk_ir_keys_t keys;
  tk_ir_request_t request;
  char digest_hex[65];
  assert(tk_ir_derive_keys(VECTOR_DEVICE_KEY_HEX, VECTOR_MAILBOX, &keys) ==
         TK_IR_OK);

  assert(decode_case(&keys, VECTOR_MAILBOX, VECTOR_REQUEST_ID,
                     VECTOR_REQUEST_ENVELOPE, &request) == TK_IR_OK);
  assert(strcmp(request.request_id, VECTOR_REQUEST_ID) == 0);
  assert(request.expires_at == VECTOR_EXPIRES_AT);
  assert(request.view_len == strlen(VECTOR_VIEW_UTF8));
  assert(memcmp(request.view, VECTOR_VIEW_UTF8, request.view_len) == 0);
  assert(memcmp(request.challenge, (uint8_t[])VECTOR_CHALLENGE, 32) == 0);
  hex(digest_hex, sizeof digest_hex, request.view_sha256, 32);
  assert(strcmp(digest_hex, VECTOR_VIEW_SHA256_HEX) == 0);

  struct {
    const char *name;
    const char *envelope;
    tk_ir_error_t error;
  } invalid[] = {
      {"padded base64", VECTOR_REQUEST_PADDED_B64, TK_IR_ERR_FORMAT},
      {"11-byte nonce", VECTOR_REQUEST_NONCE_11, TK_IR_ERR_FORMAT},
      {"13-byte nonce", VECTOR_REQUEST_NONCE_13, TK_IR_ERR_FORMAT},
      {"short tag", VECTOR_REQUEST_SHORT_TAG, TK_IR_ERR_FORMAT},
      {"bad tag", VECTOR_REQUEST_BAD_TAG, TK_IR_ERR_AUTH},
      {"bad length", VECTOR_REQUEST_BAD_LENGTH, TK_IR_ERR_FORMAT},
      {"unknown key", VECTOR_REQUEST_UNKNOWN_KEY, TK_IR_ERR_FORMAT},
      {"bad challenge", VECTOR_REQUEST_BAD_CHALLENGE, TK_IR_ERR_FORMAT},
      {"oversized view", VECTOR_REQUEST_OVERSIZED_VIEW, TK_IR_ERR_FORMAT},
      {"bad digest", VECTOR_REQUEST_BAD_DIGEST, TK_IR_ERR_DIGEST},
  };
  for (size_t i = 0; i < sizeof invalid / sizeof invalid[0]; ++i) {
    memset(&request, 0xa5, sizeof request);
    assert(decode_case(&keys, VECTOR_MAILBOX, VECTOR_REQUEST_ID,
                       invalid[i].envelope, &request) == invalid[i].error);
    assert(all_zero((const uint8_t *)&request, sizeof request));
  }

  memset(&request, 0xa5, sizeof request);
  assert(decode_case(&keys, "vp_Z9y8X7w6V5u4T3s2", VECTOR_REQUEST_ID,
                     VECTOR_REQUEST_ENVELOPE, &request) == TK_IR_ERR_AUTH);
  assert(all_zero((const uint8_t *)&request, sizeof request));
  memset(&request, 0xa5, sizeof request);
  assert(decode_case(&keys, VECTOR_MAILBOX, "_BEiM0RVZneImaq7zN3u_w",
                     VECTOR_REQUEST_ENVELOPE, &request) == TK_IR_ERR_AUTH);
  assert(all_zero((const uint8_t *)&request, sizeof request));

  uint8_t over[TK_IR_MAX_ENVELOPE_BYTES + 1];
  memset(over, '{', sizeof over);
  memset(s_work, 0xcc, sizeof s_work);
  assert(tk_ir_decode_request(&keys, VECTOR_MAILBOX, VECTOR_REQUEST_ID,
                              over, sizeof over, &request, s_work,
                              sizeof s_work) == TK_IR_ERR_CAPACITY);
  assert(all_zero(s_work, sizeof s_work));
  assert(all_zero((const uint8_t *)&request, sizeof request));
  tk_ir_keys_zero(&keys);
}

static void test_verdicts(void) {
  const tk_ir_verdict_t verdicts[] = {
      TK_IR_VERDICT_APPROVE, TK_IR_VERDICT_DENY,
      TK_IR_VERDICT_TERMINAL, TK_IR_VERDICT_PANIC};
  const char *expected_envelopes[] = {
      VECTOR_VERDICT_APPROVE_ENVELOPE,
      VECTOR_VERDICT_DENY_ENVELOPE,
      VECTOR_VERDICT_TERMINAL_ENVELOPE,
      VECTOR_VERDICT_PANIC_ENVELOPE};
  const char *expected_hmacs[] = {
      VECTOR_VERDICT_APPROVE_HMAC_HEX,
      VECTOR_VERDICT_DENY_HMAC_HEX,
      VECTOR_VERDICT_TERMINAL_HMAC_HEX,
      VECTOR_VERDICT_PANIC_HMAC_HEX};
  tk_ir_keys_t keys;
  tk_ir_request_t request;
  uint8_t mac[32];
  uint8_t envelope[TK_IR_MAX_ENVELOPE_BYTES];
  size_t envelope_len = 0;
  char actual[65];
  assert(tk_ir_derive_keys(VECTOR_DEVICE_KEY_HEX, VECTOR_MAILBOX, &keys) ==
         TK_IR_OK);
  assert(decode_case(&keys, VECTOR_MAILBOX, VECTOR_REQUEST_ID,
                     VECTOR_REQUEST_ENVELOPE, &request) == TK_IR_OK);

  for (size_t i = 0; i < sizeof verdicts / sizeof verdicts[0]; ++i) {
    assert(tk_ir_verdict_hmac(&keys, VECTOR_MAILBOX, &request,
                              verdicts[i], mac) == TK_IR_OK);
    hex(actual, sizeof actual, mac, sizeof mac);
    assert(strcmp(actual, expected_hmacs[i]) == 0);
    memset(s_work, 0xcc, sizeof s_work);
    assert(tk_ir_encode_verdict(
        &keys, VECTOR_MAILBOX, &request, verdicts[i], deterministic_random,
        NULL, envelope, sizeof envelope, &envelope_len, s_work,
        sizeof s_work) == TK_IR_OK);
    assert(all_zero(s_work, sizeof s_work));
    assert(envelope_len == strlen(expected_envelopes[i]));
    assert(memcmp(envelope, expected_envelopes[i], envelope_len) == 0);
  }

  memset(s_work, 0xcc, sizeof s_work);
  assert(tk_ir_encode_verdict(
      &keys, VECTOR_MAILBOX, &request, TK_IR_VERDICT_APPROVE, failed_random,
      NULL, envelope, sizeof envelope, &envelope_len, s_work,
      sizeof s_work) == TK_IR_ERR_RANDOM);
  assert(all_zero(s_work, sizeof s_work));
  assert(tk_ir_verdict_hmac(&keys, VECTOR_MAILBOX, &request,
                            (tk_ir_verdict_t)0, mac) == TK_IR_ERR_FORMAT);
  assert(tk_ir_verdict_hmac(&keys, VECTOR_MAILBOX, &request,
                            (tk_ir_verdict_t)5, mac) == TK_IR_ERR_FORMAT);
  tk_ir_keys_zero(&keys);
}

int main(void) {
  test_keys_and_base64();
  test_request_decode();
  test_verdicts();
  puts("OK: encrypted interaction relay C vectors and hostile inputs");
  return 0;
}
