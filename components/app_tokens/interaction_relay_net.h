#ifndef TK_INTERACTION_RELAY_NET_H
#define TK_INTERACTION_RELAY_NET_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
  uint32_t polls_ok;
  uint32_t requests_applied;
  uint32_t verdicts_acked;
  uint32_t failures;
  int last_http_status;
  bool running;
} tk_interaction_relay_net_status;

/* Present only when CONFIG_TK_VIBEPULSE_INTERACTION_RELAY is enabled; there
 * is deliberately no disabled-build stub or dormant task. */
void tokens_interaction_relay_net_start(void);
tk_interaction_relay_net_status tokens_interaction_relay_net_status(void);

#ifdef __cplusplus
}
#endif

#endif
