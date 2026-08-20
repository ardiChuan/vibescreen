#ifndef NEEDS_YOU_NET_H
#define NEEDS_YOU_NET_H

#include <stdbool.h>

#include "interaction_relay_policy.h"
#include "needs_you_policy.h"

/* The device's answer channel. Registers the takeover's verdict callback and
 * sends signed POSTs to the bridge on a worker task, so a tap never blocks the
 * UI on the network. Compiled to no-ops without TK_VIBEPULSE_DEVICE_KEY, which
 * leaves the screens display-only (LEAVE IT and the private tap still dismiss
 * locally, they just tell no one). */
void tokens_needs_you_net_start(void);

/* KEY3 panic: deny everything parked, from the platform's button handler. */
void tk_needs_you_send_panic(void);

/* Optional strong implementation supplied by the encrypted relay client in
 * Task 9. The default weak implementation fails closed. Called only from the
 * Needs You network worker, never from LVGL; implementations must copy the
 * immutable decision binding into their own bounded queue. */
bool tk_interaction_relay_queue_verdict(
    tk_needs_you_verdict verdict, const tk_ir_decision_context *context);

#endif
