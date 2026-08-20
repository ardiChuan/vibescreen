#include <stdio.h>

#include "../main/wifi_signal_state.h"

static int failures;

static void check(const char *name, int condition) {
  if (!condition) {
    printf("FAIL %s\n", name);
    failures++;
  }
}

int main(void) {
  tg_wifi_signal_state state = TG_WIFI_SIGNAL_STATE_INIT;

  check("initial state is disconnected", tg_wifi_signal_bars(&state) == 0);

  tg_wifi_signal_event(&state, 1); /* GOT_IP */
  check("GOT_IP publishes at least one bar", tg_wifi_signal_bars(&state) == 1);

  unsigned stale_before_disconnect = tg_wifi_signal_sample_begin(&state);
  tg_wifi_signal_event(&state, 0); /* DISCONNECTED while RSSI query runs */
  check("stale RSSI cannot overwrite disconnect",
        !tg_wifi_signal_sample_commit(&state, stale_before_disconnect, 3));
  check("disconnect remains visible", tg_wifi_signal_bars(&state) == 0);

  unsigned stale_before_ip = tg_wifi_signal_sample_begin(&state);
  tg_wifi_signal_event(&state, 1); /* GOT_IP while failed AP query runs */
  check("stale failed sample cannot overwrite GOT_IP",
        !tg_wifi_signal_sample_commit(&state, stale_before_ip, 0));
  check("GOT_IP remains visible", tg_wifi_signal_bars(&state) == 1);

  unsigned current = tg_wifi_signal_sample_begin(&state);
  check("current RSSI sample commits", tg_wifi_signal_sample_commit(&state,
                                                                     current, 3));
  check("current RSSI is visible", tg_wifi_signal_bars(&state) == 3);

  current = tg_wifi_signal_sample_begin(&state);
  check("bars clamp to three", tg_wifi_signal_sample_commit(&state, current, 9));
  check("clamped RSSI is visible", tg_wifi_signal_bars(&state) == 3);

  /* The last representable generation is absorbing: it cannot wrap back to a
   * value held by a very old sampler (the 30-bit ABA case). */
  atomic_store(&state.packed,
               (TG_WIFI_SIGNAL_TERMINAL_GENERATION -
                TG_WIFI_SIGNAL_GENERATION_STEP) | 2u);
  unsigned near_max = tg_wifi_signal_sample_begin(&state);
  tg_wifi_signal_event(&state, 0);
  check("near-max event saturates generation",
        atomic_load(&state.packed) == TG_WIFI_SIGNAL_TERMINAL_GENERATION);
  check("pre-saturation sample cannot commit",
        !tg_wifi_signal_sample_commit(&state, near_max, 3));
  unsigned terminal = tg_wifi_signal_sample_begin(&state);
  check("terminal generation rejects every sample",
        !tg_wifi_signal_sample_commit(&state, terminal, 3));
  tg_wifi_signal_event(&state, 1);
  check("terminal GOT_IP still owns bars", tg_wifi_signal_bars(&state) == 1);
  tg_wifi_signal_event(&state, 0);
  check("terminal disconnect still owns bars", tg_wifi_signal_bars(&state) == 0);

  if (failures) return 1;
  printf("OK: Wi-Fi events order samples without generation wrap\n");
  return 0;
}
