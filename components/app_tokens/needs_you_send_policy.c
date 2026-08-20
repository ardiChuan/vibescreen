/* See needs_you_send_policy.h. Pure bytes: canonical message, portable
 * HMAC-SHA256, JSON bodies. No LVGL, no network, no clock. */
#include "needs_you_send_policy.h"

#include <stdio.h>
#include <string.h>

/* -- SHA-256 (FIPS 180-4) ------------------------------------------------- */

typedef struct {
  uint32_t state[8];
  uint64_t bits;
  uint8_t buffer[64];
  size_t pending;
} sha256_ctx;

static uint32_t rotr(uint32_t value, unsigned bits) {
  return (value >> bits) | (value << (32u - bits));
}

static const uint32_t SHA256_K[64] = {
  0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u,
  0x923f82a4u, 0xab1c5ed5u, 0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
  0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u, 0xe49b69c1u, 0xefbe4786u,
  0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
  0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u,
  0x06ca6351u, 0x14292967u, 0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
  0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u, 0xa2bfe8a1u, 0xa81a664bu,
  0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
  0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au,
  0x5b9cca4fu, 0x682e6ff3u, 0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
  0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u,
};

static void sha256_init(sha256_ctx *ctx) {
  static const uint32_t iv[8] = {
    0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
    0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u,
  };
  memcpy(ctx->state, iv, sizeof iv);
  ctx->bits = 0;
  ctx->pending = 0;
}

static void sha256_block(sha256_ctx *ctx, const uint8_t *block) {
  uint32_t w[64];
  for (int i = 0; i < 16; i++) {
    w[i] = ((uint32_t)block[i * 4] << 24) | ((uint32_t)block[i * 4 + 1] << 16) |
           ((uint32_t)block[i * 4 + 2] << 8) | (uint32_t)block[i * 4 + 3];
  }
  for (int i = 16; i < 64; i++) {
    uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
    uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  uint32_t a = ctx->state[0], b = ctx->state[1], c = ctx->state[2];
  uint32_t d = ctx->state[3], e = ctx->state[4], f = ctx->state[5];
  uint32_t g = ctx->state[6], h = ctx->state[7];
  for (int i = 0; i < 64; i++) {
    uint32_t S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
    uint32_t ch = (e & f) ^ (~e & g);
    uint32_t t1 = h + S1 + ch + SHA256_K[i] + w[i];
    uint32_t S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
    uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
    uint32_t t2 = S0 + maj;
    h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
  }
  ctx->state[0] += a; ctx->state[1] += b; ctx->state[2] += c;
  ctx->state[3] += d; ctx->state[4] += e; ctx->state[5] += f;
  ctx->state[6] += g; ctx->state[7] += h;
}

static void sha256_update(sha256_ctx *ctx, const uint8_t *data, size_t len) {
  ctx->bits += (uint64_t)len * 8u;
  while (len > 0) {
    size_t take = 64 - ctx->pending;
    if (take > len) take = len;
    memcpy(ctx->buffer + ctx->pending, data, take);
    ctx->pending += take;
    data += take;
    len -= take;
    if (ctx->pending == 64) {
      sha256_block(ctx, ctx->buffer);
      ctx->pending = 0;
    }
  }
}

static void sha256_final(sha256_ctx *ctx, uint8_t out[32]) {
  uint64_t bits = ctx->bits;
  uint8_t pad = 0x80;
  sha256_update(ctx, &pad, 1);
  uint8_t zero = 0;
  while (ctx->pending != 56) sha256_update(ctx, &zero, 1);
  uint8_t length[8];
  for (int i = 0; i < 8; i++) length[i] = (uint8_t)(bits >> (56 - i * 8));
  sha256_update(ctx, length, 8);
  for (int i = 0; i < 8; i++) {
    out[i * 4] = (uint8_t)(ctx->state[i] >> 24);
    out[i * 4 + 1] = (uint8_t)(ctx->state[i] >> 16);
    out[i * 4 + 2] = (uint8_t)(ctx->state[i] >> 8);
    out[i * 4 + 3] = (uint8_t)ctx->state[i];
  }
}

/* -- HMAC-SHA256 (RFC 2104) ----------------------------------------------- */

static void hmac_sha256(const uint8_t *key, size_t key_len,
                        const uint8_t *msg, size_t msg_len, uint8_t out[32]) {
  uint8_t block[64];
  memset(block, 0, sizeof block);
  if (key_len > 64) {
    sha256_ctx ctx;
    sha256_init(&ctx);
    sha256_update(&ctx, key, key_len);
    sha256_final(&ctx, block); /* 32 bytes, rest stays zero */
  } else {
    memcpy(block, key, key_len);
  }
  uint8_t ipad[64], opad[64];
  for (int i = 0; i < 64; i++) {
    ipad[i] = (uint8_t)(block[i] ^ 0x36);
    opad[i] = (uint8_t)(block[i] ^ 0x5c);
  }
  uint8_t inner[32];
  sha256_ctx ctx;
  sha256_init(&ctx);
  sha256_update(&ctx, ipad, 64);
  sha256_update(&ctx, msg, msg_len);
  sha256_final(&ctx, inner);
  sha256_init(&ctx);
  sha256_update(&ctx, opad, 64);
  sha256_update(&ctx, inner, 32);
  sha256_final(&ctx, out);
}

/* -- policy --------------------------------------------------------------- */

const char *tk_needs_you_verdict_name(tk_needs_you_verdict verdict) {
  switch (verdict) {
    case TK_NEEDS_YOU_VERDICT_APPROVE: return "approve";
    case TK_NEEDS_YOU_VERDICT_DENY: return "deny";
    case TK_NEEDS_YOU_VERDICT_LEAVE_IT: return "leave_it";
    default: return NULL;
  }
}

int tk_needs_you_canonical_message(char *out, size_t cap,
                                   const char *request_id,
                                   const char *verdict_name, uint64_t ts) {
  if (!out || !request_id || !verdict_name) return -1;
  int written = snprintf(out, cap, "%s|%s|%llu", request_id, verdict_name,
                         (unsigned long long)ts);
  if (written < 0 || (size_t)written >= cap) return -1;
  return written;
}

static bool provider_valid(const char *provider) {
  return provider &&
         (strcmp(provider, "claude") == 0 || strcmp(provider, "codex") == 0);
}

static bool digest_valid(const char *digest) {
  if (!digest || strlen(digest) != 64) return false;
  for (size_t i = 0; i < 64; i++) {
    char byte = digest[i];
    if (!((byte >= '0' && byte <= '9') || (byte >= 'a' && byte <= 'f'))) {
      return false;
    }
  }
  return true;
}

static bool request_id_valid(const char *request_id) {
  if (!request_id) return false;
  size_t length = strlen(request_id);
  if (length == 0 || length >= 33) return false;
  for (size_t i = 0; i < length; i++) {
    char byte = request_id[i];
    if (!((byte >= 'a' && byte <= 'z') ||
          (byte >= 'A' && byte <= 'Z') ||
          (byte >= '0' && byte <= '9') || byte == '_' || byte == '-')) {
      return false;
    }
  }
  return true;
}

static bool verdict_valid(const char *verdict) {
  return verdict &&
         (strcmp(verdict, "approve") == 0 || strcmp(verdict, "deny") == 0 ||
          strcmp(verdict, "leave_it") == 0);
}

int tk_needs_you_canonical_message_v2(
    char *out, size_t cap, const char *provider, const char *request_id,
    const char *view_sha256, const char *verdict_name, uint64_t ts) {
  if (!out || !provider_valid(provider) || !request_id_valid(request_id) ||
      !digest_valid(view_sha256) || !verdict_valid(verdict_name)) {
    return -1;
  }
  int written = snprintf(out, cap, "v2|%s|%s|%s|%s|%llu", provider,
                         request_id, view_sha256, verdict_name,
                         (unsigned long long)ts);
  if (written < 0 || (size_t)written >= cap) return -1;
  return written;
}

void tk_needs_you_hmac_hex(char out[TK_NEEDS_YOU_HMAC_HEX_CAP],
                           const char *key, const char *message) {
  static const char hex[] = "0123456789abcdef";
  uint8_t mac[32];
  const char *safe_key = key ? key : "";
  const char *safe_msg = message ? message : "";
  hmac_sha256((const uint8_t *)safe_key, strlen(safe_key),
              (const uint8_t *)safe_msg, strlen(safe_msg), mac);
  for (int i = 0; i < 32; i++) {
    out[i * 2] = hex[mac[i] >> 4];
    out[i * 2 + 1] = hex[mac[i] & 0x0f];
  }
  out[64] = '\0';
}

int tk_needs_you_answer_body(char *out, size_t cap, const char *verdict_name,
                             uint64_t ts, const char *hmac_hex) {
  if (!out || !verdict_name || !hmac_hex) return -1;
  int written = snprintf(out, cap,
                         "{\"verdict\":\"%s\",\"ts\":%llu,\"hmac\":\"%s\"}",
                         verdict_name, (unsigned long long)ts, hmac_hex);
  if (written < 0 || (size_t)written >= cap) return -1;
  return written;
}

int tk_needs_you_answer_body_v2(
    char *out, size_t cap, const char *provider, const char *view_sha256,
    const char *verdict_name, uint64_t ts, const char *hmac_hex) {
  if (!out || !provider_valid(provider) || !digest_valid(view_sha256) ||
      !verdict_valid(verdict_name) || !digest_valid(hmac_hex)) {
    return -1;
  }
  int written = snprintf(
      out, cap,
      "{\"provider\":\"%s\",\"view_sha256\":\"%s\","
      "\"verdict\":\"%s\",\"ts\":%llu,\"hmac\":\"%s\"}",
      provider, view_sha256, verdict_name, (unsigned long long)ts, hmac_hex);
  if (written < 0 || (size_t)written >= cap) return -1;
  return written;
}

int tk_needs_you_panic_body(char *out, size_t cap, uint64_t ts,
                            const char *hmac_hex) {
  if (!out || !hmac_hex) return -1;
  int written = snprintf(out, cap, "{\"ts\":%llu,\"hmac\":\"%s\"}",
                         (unsigned long long)ts, hmac_hex);
  if (written < 0 || (size_t)written >= cap) return -1;
  return written;
}

bool tk_needs_you_send_should_retry(int http_status) {
  (void)http_status;
  return false;
}
