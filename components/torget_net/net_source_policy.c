#include "net_source_policy.h"

tg_net_source tg_net_source_first(const tg_net_source_state *state,
                                  int64_t now_us) {
  if (!state || !state->relay_won) return TG_NET_SOURCE_LOCAL;

  /* Reläet levererar. Prova LAN igen med jämna mellanrum så en hemkomst
   * upptäcks — men inte varje hämtning, för varje förlorat försök kostar
   * en timeout innan reläet ens tillfrågas. */
  if (state->last_local_try_us == 0) return TG_NET_SOURCE_LOCAL;
  if (now_us - state->last_local_try_us >= TG_NET_LOCAL_REPROBE_US)
    return TG_NET_SOURCE_LOCAL;
  return TG_NET_SOURCE_RELAY;
}

int tg_net_source_timeout_ms(const tg_net_source_state *state,
                             tg_net_source source) {
  if (source != TG_NET_SOURCE_LOCAL) return TG_NET_LOCAL_TIMEOUT_MS;
  /* Ett återprov medan reläet fungerar får inte hålla upp en hämtning som
   * annars hade landat: två sekunder räcker gott på ett LAN, och missar vi
   * hemkomsten just den gången tas den om fem minuter senare. */
  if (state && state->relay_won) return TG_NET_REPROBE_TIMEOUT_MS;
  return TG_NET_LOCAL_TIMEOUT_MS;
}

bool tg_net_source_may_fall_back(tg_net_source tried) {
  return tried == TG_NET_SOURCE_LOCAL;
}

void tg_net_source_note(tg_net_source_state *state, tg_net_source tried,
                        bool ok, int64_t now_us) {
  if (!state) return;

  if (tried == TG_NET_SOURCE_LOCAL) {
    /* Stämpla ALLTID försöket, lyckat som misslyckat — annars provas LAN om
     * och om igen i varje hämtning så fort återprovsfönstret öppnat sig. */
    state->last_local_try_us = now_us;
    if (ok) state->relay_won = false; /* hemma igen: LAN äger */
    return;
  }

  /* Reläet lyckades = det är den som gäller tills LAN svarar igen. Ett
   * misslyckat relä ändrar ingenting: då är BÅDA nere, och nästa hämtning
   * ska börja om från LAN i stället för att fastna på reläet. */
  if (ok) state->relay_won = true;
}
