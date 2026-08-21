#include "agent_status_source_policy.h"

#include <string.h>

static uint64_t elapsed_saturated(uint64_t now_ms, uint64_t then_ms) {
  return now_ms >= then_ms ? now_ms - then_ms : 0;
}

void tk_agent_source_policy_init(tk_agent_source_policy *policy) {
  if (policy != NULL) memset(policy, 0, sizeof *policy);
}

void tk_agent_source_note_lan(tk_agent_source_policy *policy,
                              uint64_t now_ms) {
  if (policy == NULL) return;
  policy->last_lan_ms = now_ms;
  policy->has_lan = true;
  policy->relay_owns_rows = false;
  policy->relay_clear_consumed = false;
}

bool tk_agent_source_allow_relay(const tk_agent_source_policy *policy,
                                 uint64_t now_ms) {
  if (policy == NULL || !policy->has_lan) return true;
  return elapsed_saturated(now_ms, policy->last_lan_ms) >=
         TK_AGENT_LAN_FRESH_MS;
}

void tk_agent_source_note_relay(tk_agent_source_policy *policy,
                                uint64_t now_ms) {
  if (policy == NULL) return;
  policy->last_relay_ms = now_ms;
  policy->relay_owns_rows = true;
  policy->relay_clear_consumed = false;
}

bool tk_agent_source_should_clear_relay(tk_agent_source_policy *policy,
                                        uint64_t now_ms) {
  if (policy == NULL || !policy->relay_owns_rows ||
      policy->relay_clear_consumed ||
      !tk_agent_source_allow_relay(policy, now_ms) ||
      elapsed_saturated(now_ms, policy->last_relay_ms) <
          TK_AGENT_RELAY_STALE_MS) {
    return false;
  }
  policy->relay_clear_consumed = true;
  policy->relay_owns_rows = false;
  return true;
}
