#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "../components/app_tokens/agent_status_source_policy.h"

int main(void) {
  tk_agent_source_policy policy;
  tk_agent_source_policy_init(&policy);

  assert(tk_agent_source_allow_relay(&policy, 0));
  assert(!tk_agent_source_should_clear_relay(&policy, 0));

  tk_agent_source_note_lan(&policy, 1000);
  assert(!tk_agent_source_allow_relay(&policy, 5999));
  assert(tk_agent_source_allow_relay(&policy, 6000));

  tk_agent_source_note_relay(&policy, 6000);
  assert(!tk_agent_source_should_clear_relay(&policy, 25999));
  assert(tk_agent_source_should_clear_relay(&policy, 26000));
  assert(!tk_agent_source_should_clear_relay(&policy, 26000));

  tk_agent_source_note_relay(&policy, 30000);
  tk_agent_source_note_lan(&policy, 31000);
  assert(!tk_agent_source_allow_relay(&policy, 35999));
  assert(!tk_agent_source_should_clear_relay(&policy, UINT64_MAX));

  tk_agent_source_note_lan(&policy, UINT64_MAX - 2u);
  assert(!tk_agent_source_allow_relay(&policy, UINT64_MAX));
  assert(!tk_agent_source_allow_relay(&policy, 1));

  tk_agent_source_note_relay(&policy, UINT64_MAX - 10u);
  assert(!tk_agent_source_should_clear_relay(&policy, UINT64_MAX));
  assert(!tk_agent_source_should_clear_relay(&policy, 5));

  puts("OK: LAN precedence and relay expiry are wrap-safe");
  return 0;
}
