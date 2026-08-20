#include "interaction_relay_policy.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static const char k_digest_a[] =
    "000102030405060708090a0b0c0d0e0f"
    "101112131415161718191a1b1c1d1e1f";
static const char k_digest_b[] =
    "ffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffff";

static tk_pending_interaction pending(const char *id,
                                      tk_pending_source source,
                                      uint32_t expires_in_ms,
                                      const char *title) {
  tk_pending_interaction value = {0};
  value.present = true;
  value.provider = TK_AGENT_PROVIDER_CODEX;
  value.source = source;
  value.kind = TK_PENDING_APPROVAL;
  value.can_approve = true;
  value.has_title = true;
  value.has_view_sha256 = true;
  value.expires_in_ms = expires_in_ms;
  value.hold_ms = expires_in_ms;
  snprintf(value.request_id, sizeof value.request_id, "%s", id);
  snprintf(value.title, sizeof value.title, "%s", title);
  memcpy(value.view_sha256, k_digest_a, sizeof value.view_sha256);
  if (source == TK_PENDING_SOURCE_RELAY) {
    value.has_relay_binding = true;
    for (size_t i = 0; i < sizeof value.relay_challenge; ++i) {
      value.relay_challenge[i] = (uint8_t)(0x80u + i);
      value.relay_view_sha256[i] = (uint8_t)i;
    }
  }
  return value;
}

static void test_selection_and_mirror(void) {
  tk_ir_policy policy;
  tk_pending_interaction current;
  tk_ir_policy_init(&policy);
  assert(!tk_ir_policy_current(&policy, 1000, &current));

  tk_pending_interaction lan = pending(
      "AAAAAAAAAAAAAAAAAAAAAA", TK_PENDING_SOURCE_LAN, 10000, "LAN");
  tk_ir_policy_update_lan(&policy, &lan, 1000);
  assert(tk_ir_policy_current(&policy, 1000, &current));
  assert(current.source == TK_PENDING_SOURCE_LAN);
  assert(strcmp(current.title, "LAN") == 0);
  assert(!current.has_relay_binding);

  tk_ir_policy_init(&policy);
  tk_pending_interaction relay = pending(
      "BBBBBBBBBBBBBBBBBBBBBB", TK_PENDING_SOURCE_RELAY, 9000, "RELAY");
  tk_ir_policy_update_relay(&policy, &relay, 1000);
  assert(tk_ir_policy_current(&policy, 1000, &current));
  assert(current.source == TK_PENDING_SOURCE_RELAY);
  assert(strcmp(current.title, "RELAY") == 0);
  assert(current.has_relay_binding);

  /* Mirrored requests show the LAN copy but retain the authenticated relay
   * binding. The earlier deadline is authoritative. */
  tk_ir_policy_init(&policy);
  lan = pending("CCCCCCCCCCCCCCCCCCCCCC", TK_PENDING_SOURCE_LAN,
                10000, "LAN wins glass");
  relay = pending("CCCCCCCCCCCCCCCCCCCCCC", TK_PENDING_SOURCE_RELAY,
                  7000, "relay copy");
  tk_ir_policy_update_lan(&policy, &lan, 1000);
  tk_ir_policy_update_relay(&policy, &relay, 1000);
  assert(tk_ir_policy_current(&policy, 2000, &current));
  assert(current.source == TK_PENDING_SOURCE_LAN);
  assert(strcmp(current.title, "LAN wins glass") == 0);
  assert(current.has_relay_binding);
  assert(current.expires_in_ms == 6000);
  assert(memcmp(current.relay_challenge, relay.relay_challenge,
                sizeof current.relay_challenge) == 0);

  /* A relay binding for different visible bytes is never borrowed. */
  memcpy(relay.view_sha256, k_digest_b, sizeof relay.view_sha256);
  tk_ir_policy_update_relay(&policy, &relay, 1000);
  assert(tk_ir_policy_current(&policy, 2000, &current));
  assert(!current.has_relay_binding);

  /* Different IDs are oldest-deadline first; exact ties prefer LAN. */
  tk_ir_policy_init(&policy);
  lan = pending("DDDDDDDDDDDDDDDDDDDDDD", TK_PENDING_SOURCE_LAN,
                8000, "later LAN");
  relay = pending("EEEEEEEEEEEEEEEEEEEEEE", TK_PENDING_SOURCE_RELAY,
                  5000, "earlier relay");
  tk_ir_policy_update_lan(&policy, &lan, 1000);
  tk_ir_policy_update_relay(&policy, &relay, 1000);
  assert(tk_ir_policy_current(&policy, 1500, &current));
  assert(strcmp(current.request_id, relay.request_id) == 0);
  relay.expires_in_ms = lan.expires_in_ms;
  tk_ir_policy_update_relay(&policy, &relay, 1000);
  assert(tk_ir_policy_current(&policy, 1500, &current));
  assert(strcmp(current.request_id, lan.request_id) == 0);
}

static void test_answered_suppression_is_bounded(void) {
  tk_ir_policy policy;
  tk_pending_interaction current;
  tk_ir_policy_init(&policy);

  for (unsigned i = 0; i < TK_IR_ANSWERED_IDS; ++i) {
    char id[TK_PENDING_ID_CAP];
    snprintf(id, sizeof id, "answered-%u", i);
    tk_pending_interaction value = pending(
        id, TK_PENDING_SOURCE_RELAY, 10000 + i, "answer");
    tk_ir_policy_update_relay(&policy, &value, 1000);
    assert(tk_ir_policy_current(&policy, 1000, &current));
    assert(tk_ir_policy_mark_answered(&policy, &current, 1000));
    assert(!tk_ir_policy_current(&policy, 1000, &current));
    /* A delayed or refreshed poll cannot resurrect the same ID. */
    value.expires_in_ms = 20000 + i;
    tk_ir_policy_update_relay(&policy, &value, 1000);
    assert(!tk_ir_policy_current(&policy, 2000, &current));
  }
  assert(tk_ir_policy_answered_count(&policy, 2000) == TK_IR_ANSWERED_IDS);

  /* The ninth answer replaces the oldest bounded record, never grows state. */
  tk_pending_interaction ninth = pending(
      "answered-8", TK_PENDING_SOURCE_RELAY, 30000, "ninth");
  tk_ir_policy_update_relay(&policy, &ninth, 1000);
  assert(tk_ir_policy_current(&policy, 1000, &current));
  assert(tk_ir_policy_mark_answered(&policy, &current, 1000));
  assert(tk_ir_policy_answered_count(&policy, 2000) == TK_IR_ANSWERED_IDS);
}

static void test_context_and_source_routing(void) {
  tk_ir_policy policy;
  tk_ir_decision_context context;
  tk_ir_policy_init(&policy);

  tk_pending_interaction relay = pending(
      "FFFFFFFFFFFFFFFFFFFFFF", TK_PENDING_SOURCE_RELAY, 9000, "relay");
  tk_ir_policy_update_relay(&policy, &relay, 1000);
  assert(tk_ir_policy_capture_visible(&policy, 2000, &context));
  assert(context.source == TK_PENDING_SOURCE_RELAY);
  assert(context.has_relay_binding);
  assert(context.can_approve);
  assert(strcmp(context.request_id, relay.request_id) == 0);
  assert(tk_ir_delivery_initial(&context) == TK_IR_DELIVER_RELAY);

  /* Panic is anchored by capturing the same exact visible ID/binding. */
  tk_ir_decision_context panic = {0};
  assert(tk_ir_policy_capture_visible(&policy, 2000, &panic));
  assert(strcmp(panic.request_id, context.request_id) == 0);
  assert(memcmp(panic.challenge, context.challenge,
                sizeof panic.challenge) == 0);

  tk_pending_interaction lan = pending(
      relay.request_id, TK_PENDING_SOURCE_LAN, 9000, "LAN");
  tk_ir_policy_update_lan(&policy, &lan, 1000);
  assert(tk_ir_policy_capture_visible(&policy, 2000, &context));
  assert(context.source == TK_PENDING_SOURCE_LAN);
  assert(context.has_relay_binding);
  assert(tk_ir_delivery_initial(&context) == TK_IR_DELIVER_DIRECT);
  assert(tk_ir_delivery_after_direct(
             &context, TK_IR_DIRECT_SUCCESS) == TK_IR_DELIVER_DONE);
  assert(tk_ir_delivery_after_direct(
             &context, TK_IR_DIRECT_HARD_REJECT) == TK_IR_DELIVER_DONE);
  assert(tk_ir_delivery_after_direct(
             &context, TK_IR_DIRECT_UNCERTAIN) == TK_IR_DELIVER_RELAY);

  /* LAN-only uncertain delivery cannot invent a cloud retry. */
  tk_ir_policy_init(&policy);
  lan = pending("GGGGGGGGGGGGGGGGGGGGGG", TK_PENDING_SOURCE_LAN,
                9000, "LAN only");
  tk_ir_policy_update_lan(&policy, &lan, 1000);
  assert(tk_ir_policy_capture_visible(&policy, 2000, &context));
  assert(tk_ir_delivery_after_direct(
             &context, TK_IR_DIRECT_UNCERTAIN) == TK_IR_DELIVER_DONE);

  assert(tk_ir_direct_result_from_http(true, 200) == TK_IR_DIRECT_SUCCESS);
  assert(tk_ir_direct_result_from_http(false, -1) == TK_IR_DIRECT_UNCERTAIN);
  assert(tk_ir_direct_result_from_http(true, 408) == TK_IR_DIRECT_UNCERTAIN);
  assert(tk_ir_direct_result_from_http(true, 429) == TK_IR_DIRECT_UNCERTAIN);
  assert(tk_ir_direct_result_from_http(true, 503) == TK_IR_DIRECT_UNCERTAIN);
  assert(tk_ir_direct_result_from_http(true, 400) ==
         TK_IR_DIRECT_HARD_REJECT);
  assert(tk_ir_direct_result_from_http(true, 401) ==
         TK_IR_DIRECT_HARD_REJECT);
  assert(tk_ir_direct_result_from_http(true, 409) ==
         TK_IR_DIRECT_HARD_REJECT);
}

static void test_exact_retry_and_backoff(void) {
  static const uint8_t body[] = "fixed-ciphertext-envelope";
  tk_ir_retry retry;
  tk_ir_retry_init(&retry);
  assert(tk_ir_retry_begin(&retry, body, sizeof body - 1, 9000));
  size_t len = 0;
  const uint8_t *first = tk_ir_retry_body(&retry, 1000, &len);
  assert(first != NULL && len == sizeof body - 1);
  assert(memcmp(first, body, len) == 0);
  tk_ir_retry_note_failure(&retry);
  const uint8_t *second = tk_ir_retry_body(&retry, 2000, &len);
  assert(second == first);
  assert(memcmp(second, body, len) == 0);
  assert(tk_ir_retry_attempts(&retry) == 1);
  assert(tk_ir_retry_body(&retry, 9000, &len) == NULL);
  tk_ir_retry_clear(&retry);
  assert(tk_ir_retry_body(&retry, 2000, &len) == NULL);

  tk_ir_backoff backoff;
  tk_ir_backoff_init(&backoff);
  assert(tk_ir_backoff_ready(&backoff, 1000));
  assert(tk_ir_backoff_fail(&backoff, 1000, 0) == 500);
  assert(!tk_ir_backoff_ready(&backoff, 1499));
  assert(tk_ir_backoff_fail(&backoff, 1500, 100) == 1100);
  assert(tk_ir_backoff_fail(&backoff, 2600, 0) == 2000);
  assert(tk_ir_backoff_fail(&backoff, 4600, 0) == 4000);
  assert(tk_ir_backoff_fail(&backoff, 8600, 900) == 5000);
  tk_ir_backoff_wifi_recovered(&backoff);
  assert(tk_ir_backoff_ready(&backoff, 0));
  assert(tk_ir_backoff_fail(&backoff, 0, 0) == 500);
}

int main(void) {
  test_selection_and_mirror();
  test_answered_suppression_is_bounded();
  test_context_and_source_routing();
  test_exact_retry_and_backoff();
  puts("OK: interaction relay source, suppression, retry and backoff policy");
  return 0;
}
