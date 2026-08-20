#include "interaction_relay_policy.h"

#include <limits.h>
#include <string.h>

static uint64_t add_deadline(uint64_t now_ms, uint32_t remaining_ms) {
  if (UINT64_MAX - now_ms < remaining_ms) return UINT64_MAX;
  return now_ms + remaining_ms;
}

static bool bounded_id(const char id[TK_PENDING_ID_CAP]) {
  return id != NULL && id[0] != '\0' &&
         memchr(id, '\0', TK_PENDING_ID_CAP) != NULL;
}

static bool same_id(const char left[TK_PENDING_ID_CAP],
                    const char right[TK_PENDING_ID_CAP]) {
  return bounded_id(left) && bounded_id(right) &&
         strncmp(left, right, TK_PENDING_ID_CAP) == 0;
}

static void slot_clear(tk_ir_pending_slot *slot) {
  if (slot != NULL) memset(slot, 0, sizeof *slot);
}

static bool slot_update(tk_ir_pending_slot *slot,
                        const tk_pending_interaction *pending,
                        tk_pending_source source, uint64_t now_ms) {
  if (slot == NULL) return false;
  slot_clear(slot);
  if (pending == NULL || !pending->present) return true;
  if (!bounded_id(pending->request_id) || pending->expires_in_ms == 0) {
    return false;
  }
  if (source == TK_PENDING_SOURCE_RELAY && !pending->has_relay_binding) {
    return false;
  }
  slot->pending = *pending;
  slot->pending.source = source;
  slot->pending.present = true;
  slot->expires_at_ms = add_deadline(now_ms, pending->expires_in_ms);
  slot->active = true;
  return true;
}

void tk_ir_policy_init(tk_ir_policy *policy) {
  if (policy != NULL) memset(policy, 0, sizeof *policy);
}

bool tk_ir_policy_update_lan(tk_ir_policy *policy,
                             const tk_pending_interaction *pending,
                             uint64_t now_ms) {
  return policy != NULL &&
         slot_update(&policy->lan, pending, TK_PENDING_SOURCE_LAN, now_ms);
}

bool tk_ir_policy_update_relay(tk_ir_policy *policy,
                               const tk_pending_interaction *pending,
                               uint64_t now_ms) {
  return policy != NULL && slot_update(
      &policy->relay, pending, TK_PENDING_SOURCE_RELAY, now_ms);
}

static void expire_answered(tk_ir_policy *policy, uint64_t now_ms) {
  if (policy == NULL) return;
  for (size_t i = 0; i < TK_IR_ANSWERED_IDS; ++i) {
    if (policy->answered[i].request_id[0] != '\0' &&
        now_ms >= policy->answered[i].expires_at_ms) {
      memset(&policy->answered[i], 0, sizeof policy->answered[i]);
    }
  }
}

static tk_ir_answered_id *answered_record(tk_ir_policy *policy,
                                          const char *request_id) {
  for (size_t i = 0; i < TK_IR_ANSWERED_IDS; ++i) {
    if (same_id(policy->answered[i].request_id, request_id)) {
      return &policy->answered[i];
    }
  }
  return NULL;
}

static bool suppressed(tk_ir_policy *policy, const char *request_id,
                       uint64_t deadline, uint64_t now_ms) {
  tk_ir_answered_id *record = answered_record(policy, request_id);
  if (record == NULL) return false;
  if (deadline > record->expires_at_ms) record->expires_at_ms = deadline;
  return now_ms < record->expires_at_ms;
}

static bool slot_available(tk_ir_policy *policy, tk_ir_pending_slot *slot,
                           uint64_t now_ms) {
  if (slot == NULL || !slot->active || !slot->pending.present) return false;
  if (now_ms >= slot->expires_at_ms) {
    slot_clear(slot);
    return false;
  }
  return !suppressed(policy, slot->pending.request_id, slot->expires_at_ms,
                     now_ms);
}

static uint32_t remaining_ms(uint64_t deadline, uint64_t now_ms) {
  if (deadline <= now_ms) return 0;
  uint64_t remaining = deadline - now_ms;
  return remaining > UINT32_MAX ? UINT32_MAX : (uint32_t)remaining;
}

static bool digest_matches(const tk_pending_interaction *lan,
                           const tk_pending_interaction *relay) {
  return lan->has_view_sha256 && relay->has_view_sha256 &&
         memchr(lan->view_sha256, '\0', sizeof lan->view_sha256) != NULL &&
         memchr(relay->view_sha256, '\0', sizeof relay->view_sha256) != NULL &&
         strcmp(lan->view_sha256, relay->view_sha256) == 0;
}

bool tk_ir_policy_current(tk_ir_policy *policy, uint64_t now_ms,
                          tk_pending_interaction *out) {
  if (out != NULL) memset(out, 0, sizeof *out);
  if (policy == NULL || out == NULL) return false;
  expire_answered(policy, now_ms);
  bool has_lan = slot_available(policy, &policy->lan, now_ms);
  bool has_relay = slot_available(policy, &policy->relay, now_ms);
  if (!has_lan && !has_relay) return false;

  if (has_lan && has_relay && same_id(
          policy->lan.pending.request_id, policy->relay.pending.request_id)) {
    *out = policy->lan.pending;
    uint64_t deadline = policy->lan.expires_at_ms < policy->relay.expires_at_ms
                            ? policy->lan.expires_at_ms
                            : policy->relay.expires_at_ms;
    out->expires_in_ms = remaining_ms(deadline, now_ms);
    if (!out->has_relay_binding && policy->relay.pending.has_relay_binding &&
        digest_matches(&policy->lan.pending, &policy->relay.pending)) {
      out->has_relay_binding = true;
      memcpy(out->relay_challenge, policy->relay.pending.relay_challenge,
             sizeof out->relay_challenge);
      memcpy(out->relay_view_sha256,
             policy->relay.pending.relay_view_sha256,
             sizeof out->relay_view_sha256);
    }
    return out->expires_in_ms != 0;
  }

  tk_ir_pending_slot *selected = NULL;
  if (has_lan && (!has_relay ||
                  policy->lan.expires_at_ms <= policy->relay.expires_at_ms)) {
    selected = &policy->lan;
  } else {
    selected = &policy->relay;
  }
  *out = selected->pending;
  out->expires_in_ms = remaining_ms(selected->expires_at_ms, now_ms);
  return out->expires_in_ms != 0;
}

static uint64_t matching_deadline(const tk_ir_policy *policy,
                                  const char *request_id,
                                  uint64_t fallback) {
  uint64_t deadline = fallback;
  if (policy->lan.active &&
      same_id(policy->lan.pending.request_id, request_id) &&
      policy->lan.expires_at_ms > deadline) {
    deadline = policy->lan.expires_at_ms;
  }
  if (policy->relay.active &&
      same_id(policy->relay.pending.request_id, request_id) &&
      policy->relay.expires_at_ms > deadline) {
    deadline = policy->relay.expires_at_ms;
  }
  return deadline;
}

bool tk_ir_policy_mark_answered(tk_ir_policy *policy,
                                const tk_pending_interaction *visible,
                                uint64_t now_ms) {
  if (policy == NULL || visible == NULL || !visible->present ||
      !bounded_id(visible->request_id) || visible->expires_in_ms == 0) {
    return false;
  }
  expire_answered(policy, now_ms);
  uint64_t deadline = matching_deadline(
      policy, visible->request_id,
      add_deadline(now_ms, visible->expires_in_ms));
  tk_ir_answered_id *record = answered_record(policy, visible->request_id);
  if (record == NULL) {
    record = &policy->answered[policy->answered_next];
    policy->answered_next = (uint8_t)(
        (policy->answered_next + 1u) % TK_IR_ANSWERED_IDS);
    memset(record, 0, sizeof *record);
    memcpy(record->request_id, visible->request_id,
           sizeof record->request_id);
    record->request_id[sizeof record->request_id - 1] = '\0';
  }
  if (deadline > record->expires_at_ms) record->expires_at_ms = deadline;
  return true;
}

size_t tk_ir_policy_answered_count(tk_ir_policy *policy, uint64_t now_ms) {
  if (policy == NULL) return 0;
  expire_answered(policy, now_ms);
  size_t count = 0;
  for (size_t i = 0; i < TK_IR_ANSWERED_IDS; ++i) {
    if (policy->answered[i].request_id[0] != '\0') ++count;
  }
  return count;
}

bool tk_ir_policy_capture_visible(tk_ir_policy *policy, uint64_t now_ms,
                                  tk_ir_decision_context *out) {
  if (out != NULL) memset(out, 0, sizeof *out);
  if (policy == NULL || out == NULL) return false;
  tk_pending_interaction current;
  if (!tk_ir_policy_current(policy, now_ms, &current)) return false;
  out->provider = current.provider;
  out->source = current.source;
  out->can_approve = current.can_approve;
  out->has_view_sha256 = current.has_view_sha256;
  out->has_relay_binding = current.has_relay_binding;
  out->expires_at_ms = add_deadline(now_ms, current.expires_in_ms);
  memcpy(out->request_id, current.request_id, sizeof out->request_id);
  memcpy(out->view_sha256, current.view_sha256, sizeof out->view_sha256);
  if (current.has_relay_binding) {
    memcpy(out->challenge, current.relay_challenge, sizeof out->challenge);
    memcpy(out->relay_view_sha256, current.relay_view_sha256,
           sizeof out->relay_view_sha256);
  }
  return true;
}

tk_ir_delivery tk_ir_delivery_initial(const tk_ir_decision_context *context) {
  if (context == NULL || !bounded_id(context->request_id)) {
    return TK_IR_DELIVER_DONE;
  }
  return context->source == TK_PENDING_SOURCE_RELAY
             ? (context->has_relay_binding ? TK_IR_DELIVER_RELAY
                                           : TK_IR_DELIVER_DONE)
             : (context->source == TK_PENDING_SOURCE_LAN
                    ? TK_IR_DELIVER_DIRECT : TK_IR_DELIVER_DONE);
}

tk_ir_delivery tk_ir_delivery_after_direct(
    const tk_ir_decision_context *context, tk_ir_direct_result result) {
  if (context == NULL || result == TK_IR_DIRECT_SUCCESS ||
      result == TK_IR_DIRECT_HARD_REJECT) {
    return TK_IR_DELIVER_DONE;
  }
  return result == TK_IR_DIRECT_UNCERTAIN && context->has_relay_binding
             ? TK_IR_DELIVER_RELAY : TK_IR_DELIVER_DONE;
}

tk_ir_direct_result tk_ir_direct_result_from_http(bool transport_ok,
                                                   int status) {
  if (!transport_ok || status < 0 || status == 408 || status == 429 ||
      status >= 500) {
    return TK_IR_DIRECT_UNCERTAIN;
  }
  return status == 200 ? TK_IR_DIRECT_SUCCESS : TK_IR_DIRECT_HARD_REJECT;
}

void tk_ir_retry_init(tk_ir_retry *retry) {
  if (retry != NULL) memset(retry, 0, sizeof *retry);
}

bool tk_ir_retry_begin(tk_ir_retry *retry, const uint8_t *envelope,
                       size_t len, uint64_t expires_at_ms) {
  if (retry == NULL || envelope == NULL || len == 0 ||
      len > sizeof retry->envelope || expires_at_ms == 0) {
    if (retry != NULL) tk_ir_retry_clear(retry);
    return false;
  }
  tk_ir_retry_clear(retry);
  memcpy(retry->envelope, envelope, len);
  retry->len = len;
  retry->expires_at_ms = expires_at_ms;
  retry->active = true;
  return true;
}

const uint8_t *tk_ir_retry_body(tk_ir_retry *retry, uint64_t now_ms,
                                size_t *len) {
  if (len != NULL) *len = 0;
  if (retry == NULL || len == NULL || !retry->active) return NULL;
  if (now_ms >= retry->expires_at_ms) {
    tk_ir_retry_clear(retry);
    return NULL;
  }
  *len = retry->len;
  return retry->envelope;
}

void tk_ir_retry_note_failure(tk_ir_retry *retry) {
  if (retry != NULL && retry->active && retry->attempts < UINT32_MAX) {
    ++retry->attempts;
  }
}

uint32_t tk_ir_retry_attempts(const tk_ir_retry *retry) {
  return retry != NULL && retry->active ? retry->attempts : 0;
}

void tk_ir_retry_clear(tk_ir_retry *retry) {
  if (retry == NULL) return;
  volatile uint8_t *bytes = (volatile uint8_t *)retry;
  for (size_t i = 0; i < sizeof *retry; ++i) bytes[i] = 0;
}

void tk_ir_backoff_init(tk_ir_backoff *backoff) {
  if (backoff != NULL) memset(backoff, 0, sizeof *backoff);
}

bool tk_ir_backoff_ready(const tk_ir_backoff *backoff, uint64_t now_ms) {
  return backoff == NULL || backoff->failures == 0 ||
         now_ms >= backoff->ready_at_ms;
}

uint32_t tk_ir_backoff_fail(tk_ir_backoff *backoff, uint64_t now_ms,
                            uint32_t jitter_ms) {
  if (backoff == NULL) return TK_IR_BACKOFF_MAX_MS;
  uint32_t base = TK_IR_BACKOFF_MIN_MS;
  unsigned shift = backoff->failures;
  if (shift > 4u) shift = 4u;
  base <<= shift;
  if (base > TK_IR_BACKOFF_MAX_MS) base = TK_IR_BACKOFF_MAX_MS;
  uint32_t room = TK_IR_BACKOFF_MAX_MS - base;
  uint32_t delay = base + (jitter_ms > room ? room : jitter_ms);
  if (backoff->failures < UINT8_MAX) ++backoff->failures;
  backoff->ready_at_ms = add_deadline(now_ms, delay);
  return delay;
}

void tk_ir_backoff_wifi_recovered(tk_ir_backoff *backoff) {
  tk_ir_backoff_init(backoff);
}
