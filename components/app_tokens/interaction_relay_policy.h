#ifndef TK_INTERACTION_RELAY_POLICY_H
#define TK_INTERACTION_RELAY_POLICY_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "agent_status.h"

#ifdef __cplusplus
extern "C" {
#endif

#define TK_IR_ANSWERED_IDS 8u
#define TK_IR_RETRY_ENVELOPE_CAP 4096u
#define TK_IR_BACKOFF_MIN_MS 500u
#define TK_IR_BACKOFF_MAX_MS 5000u

typedef struct {
  bool active;
  uint64_t expires_at_ms;
  tk_pending_interaction pending;
} tk_ir_pending_slot;

typedef struct {
  char request_id[TK_PENDING_ID_CAP];
  uint64_t expires_at_ms;
} tk_ir_answered_id;

typedef struct {
  tk_ir_pending_slot lan;
  tk_ir_pending_slot relay;
  tk_ir_answered_id answered[TK_IR_ANSWERED_IDS];
  uint8_t answered_next;
} tk_ir_policy;

typedef struct {
  tk_agent_provider provider;
  tk_pending_source source;
  bool can_approve;
  bool has_view_sha256;
  bool has_relay_binding;
  uint64_t expires_at_ms;
  char request_id[TK_PENDING_ID_CAP];
  char view_sha256[TK_PENDING_VIEW_SHA256_CAP];
  uint8_t challenge[32];
  uint8_t relay_view_sha256[32];
} tk_ir_decision_context;

void tk_ir_policy_init(tk_ir_policy *policy);
bool tk_ir_policy_update_lan(tk_ir_policy *policy,
                             const tk_pending_interaction *pending,
                             uint64_t now_ms);
bool tk_ir_policy_update_relay(tk_ir_policy *policy,
                               const tk_pending_interaction *pending,
                               uint64_t now_ms);
bool tk_ir_policy_current(tk_ir_policy *policy, uint64_t now_ms,
                          tk_pending_interaction *out);
bool tk_ir_policy_capture_visible(tk_ir_policy *policy, uint64_t now_ms,
                                  tk_ir_decision_context *out);
bool tk_ir_policy_mark_answered(tk_ir_policy *policy,
                                const tk_pending_interaction *visible,
                                uint64_t now_ms);
size_t tk_ir_policy_answered_count(tk_ir_policy *policy, uint64_t now_ms);

typedef enum {
  TK_IR_DIRECT_SUCCESS,
  TK_IR_DIRECT_HARD_REJECT,
  TK_IR_DIRECT_UNCERTAIN,
} tk_ir_direct_result;

typedef enum {
  TK_IR_DELIVER_DONE,
  TK_IR_DELIVER_DIRECT,
  TK_IR_DELIVER_RELAY,
} tk_ir_delivery;

tk_ir_delivery tk_ir_delivery_initial(const tk_ir_decision_context *context);
tk_ir_delivery tk_ir_delivery_after_direct(
    const tk_ir_decision_context *context, tk_ir_direct_result result);
tk_ir_direct_result tk_ir_direct_result_from_http(bool transport_ok,
                                                   int status);

typedef struct {
  bool active;
  uint32_t attempts;
  uint64_t expires_at_ms;
  size_t len;
  uint8_t envelope[TK_IR_RETRY_ENVELOPE_CAP];
} tk_ir_retry;

void tk_ir_retry_init(tk_ir_retry *retry);
bool tk_ir_retry_begin(tk_ir_retry *retry, const uint8_t *envelope,
                       size_t len, uint64_t expires_at_ms);
const uint8_t *tk_ir_retry_body(tk_ir_retry *retry, uint64_t now_ms,
                                size_t *len);
void tk_ir_retry_note_failure(tk_ir_retry *retry);
uint32_t tk_ir_retry_attempts(const tk_ir_retry *retry);
void tk_ir_retry_clear(tk_ir_retry *retry);

typedef struct {
  uint8_t failures;
  uint64_t ready_at_ms;
} tk_ir_backoff;

void tk_ir_backoff_init(tk_ir_backoff *backoff);
bool tk_ir_backoff_ready(const tk_ir_backoff *backoff, uint64_t now_ms);
uint32_t tk_ir_backoff_fail(tk_ir_backoff *backoff, uint64_t now_ms,
                            uint32_t jitter_ms);
void tk_ir_backoff_wifi_recovered(tk_ir_backoff *backoff);

#ifdef __cplusplus
}
#endif

#endif
