#ifndef TORGET_WIFI_SIGNAL_STATE_H
#define TORGET_WIFI_SIGNAL_STATE_H

#include <limits.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>

/* Low two bits carry 0..3 bars; every link event advances the upper-bit
 * generation. An RSSI result can therefore commit only against the exact link
 * generation it sampled, never over a newer DISCONNECTED/GOT_IP event. */
typedef struct {
  atomic_uint packed;
} tg_wifi_signal_state;

#define TG_WIFI_SIGNAL_STATE_INIT { ATOMIC_VAR_INIT(0u) }
#define TG_WIFI_SIGNAL_BARS_MASK 3u
#define TG_WIFI_SIGNAL_GENERATION_STEP 4u
#define TG_WIFI_SIGNAL_TERMINAL_GENERATION \
  (UINT_MAX & ~TG_WIFI_SIGNAL_BARS_MASK)

static inline uint8_t tg_wifi_signal_clamp(uint8_t bars) {
  return bars > 3u ? 3u : bars;
}

static inline uint8_t tg_wifi_signal_bars(const tg_wifi_signal_state *state) {
  return (uint8_t)(atomic_load_explicit(&state->packed, memory_order_acquire) &
                   TG_WIFI_SIGNAL_BARS_MASK);
}

static inline void tg_wifi_signal_event(tg_wifi_signal_state *state,
                                        uint8_t bars) {
  unsigned expected = atomic_load_explicit(&state->packed,
                                           memory_order_relaxed);
  unsigned desired;
  do {
    unsigned generation = expected & ~TG_WIFI_SIGNAL_BARS_MASK;
    unsigned next = generation >= TG_WIFI_SIGNAL_TERMINAL_GENERATION -
                                      TG_WIFI_SIGNAL_GENERATION_STEP
                        ? TG_WIFI_SIGNAL_TERMINAL_GENERATION
                        : generation + TG_WIFI_SIGNAL_GENERATION_STEP;
    desired = next | tg_wifi_signal_clamp(bars);
  } while (!atomic_compare_exchange_weak_explicit(
      &state->packed, &expected, desired, memory_order_release,
      memory_order_relaxed));
}

static inline unsigned tg_wifi_signal_sample_begin(
    const tg_wifi_signal_state *state) {
  return atomic_load_explicit(&state->packed, memory_order_relaxed);
}

static inline bool tg_wifi_signal_sample_commit(tg_wifi_signal_state *state,
                                                unsigned sampled,
                                                uint8_t bars) {
  unsigned desired = (sampled & ~TG_WIFI_SIGNAL_BARS_MASK) |
                     tg_wifi_signal_clamp(bars);
  if ((sampled & ~TG_WIFI_SIGNAL_BARS_MASK) ==
      TG_WIFI_SIGNAL_TERMINAL_GENERATION) return false;
  return atomic_compare_exchange_strong_explicit(
      &state->packed, &sampled, desired, memory_order_release,
      memory_order_relaxed);
}

#endif
