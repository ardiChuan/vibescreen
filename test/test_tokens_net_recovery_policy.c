#include <stdbool.h>
#include <stdio.h>

#include "../components/app_tokens/tokens_net_recovery_policy.h"

static int failures;

static void check(const char *name, bool condition) {
  if (!condition) {
    fprintf(stderr, "FAIL: %s\n", name);
    ++failures;
  }
}

int main(void) {
  tk_tokens_net_recovery_state state;
  tk_tokens_net_recovery_init(&state);

  check("cold start never recovers",
        !tk_tokens_net_recovery_should_recover(
            &state, TK_TOKENS_HTTP_STALL_US * 2, true, true));

  tk_tokens_net_recovery_note_success(&state, 1000000);
  check("healthy feed waits",
        !tk_tokens_net_recovery_should_recover(
            &state, 1000000 + TK_TOKENS_HTTP_STALL_US - 1, true, true));
  check("disassociated station waits",
        !tk_tokens_net_recovery_should_recover(
            &state, 1000000 + TK_TOKENS_HTTP_STALL_US, false, true));
  check("LAN-only install waits",
        !tk_tokens_net_recovery_should_recover(
            &state, 1000000 + TK_TOKENS_HTTP_STALL_US, true, false));
  check("associated redundant transport recovers at threshold",
        tk_tokens_net_recovery_should_recover(
            &state, 1000000 + TK_TOKENS_HTTP_STALL_US, true, true));

  const int64_t recovered_at = 1000000 + TK_TOKENS_HTTP_STALL_US;
  tk_tokens_net_recovery_note_recovery(&state, recovered_at);
  check("recovery cooldown suppresses loops",
        !tk_tokens_net_recovery_should_recover(
            &state, recovered_at + TK_TOKENS_HTTP_RECOVERY_COOLDOWN_US - 1,
            true, true));
  check("recovery allowed after cooldown",
        tk_tokens_net_recovery_should_recover(
            &state, recovered_at + TK_TOKENS_HTTP_RECOVERY_COOLDOWN_US,
            true, true));

  tk_tokens_net_recovery_note_success(
      &state, recovered_at + TK_TOKENS_HTTP_RECOVERY_COOLDOWN_US);
  check("new success rearms from its own timestamp",
        !tk_tokens_net_recovery_should_recover(
            &state,
            recovered_at + TK_TOKENS_HTTP_RECOVERY_COOLDOWN_US +
                TK_TOKENS_HTTP_STALL_US - 1,
            true, true));
  check("clock regression fails closed",
        !tk_tokens_net_recovery_should_recover(
            &state, state.last_success_us - 1, true, true));

  if (failures == 0) {
    printf("OK: VibePulse HTTP-recoverypolicyn är bounded och fail-closed\n");
    return 0;
  }
  return 1;
}
