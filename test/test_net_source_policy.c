#include <stdio.h>

#include "../components/torget_net/net_source_policy.h"

static int failures;

static void check(const char *what, int condition) {
  if (!condition) {
    printf("FAIL %s\n", what);
    failures++;
  }
}

static const int64_t S = 1000000LL;

static void test_home_uses_the_lan(void) {
  tg_net_source_state st = {0};
  check("a fresh panel asks the LAN first",
        tg_net_source_first(&st, 10 * S) == TG_NET_SOURCE_LOCAL);
  check("and gives it full patience",
        tg_net_source_timeout_ms(&st, TG_NET_SOURCE_LOCAL) ==
            TG_NET_LOCAL_TIMEOUT_MS);

  tg_net_source_note(&st, TG_NET_SOURCE_LOCAL, true, 10 * S);
  check("a working LAN keeps owning the fetches",
        tg_net_source_first(&st, 40 * S) == TG_NET_SOURCE_LOCAL);
  /* Hemma ska datan komma från hemmet — reläet får aldrig ta över så länge
   * LAN svarar, hur bra reläet än fungerar. */
  check("the relay never wins while the LAN answers", !st.relay_won);
}

static void test_away_falls_back_to_the_relay(void) {
  tg_net_source_state st = {0};

  /* Gästnät med klientisolering: LAN dör, reläet räddar hämtningen. */
  check("the LAN may fall through to the relay",
        tg_net_source_may_fall_back(TG_NET_SOURCE_LOCAL));
  tg_net_source_note(&st, TG_NET_SOURCE_LOCAL, false, 10 * S);
  tg_net_source_note(&st, TG_NET_SOURCE_RELAY, true, 10 * S);

  check("the relay now leads", st.relay_won);
  check("the next fetch skips the dead LAN",
        tg_net_source_first(&st, 40 * S) == TG_NET_SOURCE_RELAY);
  /* Poängen med att hoppa över: annars kostar varje hämtning en timeout på
   * en adress vi vet är borta. */
  check("and still skips it just before the reprobe window",
        tg_net_source_first(&st, 10 * S + TG_NET_LOCAL_REPROBE_US - S) ==
            TG_NET_SOURCE_RELAY);
}

static void test_a_dead_relay_does_not_loop_back(void) {
  tg_net_source_state st = {0};
  tg_net_source_note(&st, TG_NET_SOURCE_LOCAL, false, 10 * S);
  tg_net_source_note(&st, TG_NET_SOURCE_RELAY, false, 10 * S);

  /* Båda nere. Reläet får inte utses till vinnare, och det får inte falla
   * vidare till LAN igen — annars snurrar en hämtning i ring mellan två
   * döda adresser tills watchdogen tröttnar. */
  check("a failed relay never becomes the leader", !st.relay_won);
  check("the relay does not fall back onwards",
        !tg_net_source_may_fall_back(TG_NET_SOURCE_RELAY));
  check("the next fetch starts over at the LAN",
        tg_net_source_first(&st, 40 * S) == TG_NET_SOURCE_LOCAL);
}

static void test_coming_home_is_noticed(void) {
  tg_net_source_state st = {0};
  tg_net_source_note(&st, TG_NET_SOURCE_LOCAL, false, 10 * S);
  tg_net_source_note(&st, TG_NET_SOURCE_RELAY, true, 10 * S);

  const int64_t due = 10 * S + TG_NET_LOCAL_REPROBE_US;
  check("the LAN is retried once the window opens",
        tg_net_source_first(&st, due) == TG_NET_SOURCE_LOCAL);
  /* Återprovet får inte hålla upp en hämtning som annars landat. */
  check("a reprobe is impatient",
        tg_net_source_timeout_ms(&st, TG_NET_SOURCE_LOCAL) ==
            TG_NET_REPROBE_TIMEOUT_MS);

  /* Fortfarande borta: stämpeln flyttas fram så nästa återprov dröjer, i
   * stället för att varje hämtning betalar timeouten på nytt. */
  tg_net_source_note(&st, TG_NET_SOURCE_LOCAL, false, due);
  check("a failed reprobe still counts as an attempt",
        st.last_local_try_us == due);
  check("so the relay keeps serving until the next window",
        tg_net_source_first(&st, due + S) == TG_NET_SOURCE_RELAY);

  /* Hemma igen: LAN svarar och tar tillbaka rodret direkt. */
  const int64_t home = due + TG_NET_LOCAL_REPROBE_US;
  check("the LAN is retried again",
        tg_net_source_first(&st, home) == TG_NET_SOURCE_LOCAL);
  tg_net_source_note(&st, TG_NET_SOURCE_LOCAL, true, home);
  check("and a working LAN takes over immediately", !st.relay_won);
  check("full patience is restored",
        tg_net_source_timeout_ms(&st, TG_NET_SOURCE_LOCAL) ==
            TG_NET_LOCAL_TIMEOUT_MS);
}

int main(void) {
  test_home_uses_the_lan();
  test_away_falls_back_to_the_relay();
  test_a_dead_relay_does_not_loop_back();
  test_coming_home_is_noticed();

  if (failures == 0) {
    printf("OK: all net-source failover policy tests pass\n");
    return 0;
  }
  printf("%d tests failed\n", failures);
  return 1;
}
