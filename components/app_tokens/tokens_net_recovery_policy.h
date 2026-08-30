#ifndef TOKENS_NET_RECOVERY_POLICY_H
#define TOKENS_NET_RECOVERY_POLICY_H

#include <stdbool.h>
#include <stdint.h>

/* The UI declares quota data stale after 120 seconds. Give the ordinary
 * 30-second poll one extra attempt before recycling the transport. */
#define TK_TOKENS_HTTP_STALL_US (150LL * 1000000LL)
/* A real upstream outage must not turn into a reconnect loop. */
#define TK_TOKENS_HTTP_RECOVERY_COOLDOWN_US (10LL * 60LL * 1000000LL)

typedef struct {
  bool has_success;
  int64_t last_success_us;
  int64_t last_recovery_us;
} tk_tokens_net_recovery_state;

void tk_tokens_net_recovery_init(tk_tokens_net_recovery_state *state);
void tk_tokens_net_recovery_note_success(
    tk_tokens_net_recovery_state *state, int64_t now_us);
void tk_tokens_net_recovery_note_recovery(
    tk_tokens_net_recovery_state *state, int64_t now_us);

/* Recovery is deliberately conservative: a known-good feed must first have
 * gone quiet, the station must still claim to be associated, and the build
 * must have a redundant numbers relay. A LAN-only installation may
 * legitimately have a sleeping computer and is never recycled for that. */
bool tk_tokens_net_recovery_should_recover(
    const tk_tokens_net_recovery_state *state, int64_t now_us,
    bool wifi_associated, bool redundant_path_configured);

#endif
