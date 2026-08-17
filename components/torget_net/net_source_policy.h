#ifndef TORGET_NET_SOURCE_POLICY_H
#define TORGET_NET_SOURCE_POLICY_H

/*
 * Vilken källa hämtningarna ska fråga: tjänsten på LAN:et, eller reläet på
 * internet. Ren policy utan ESP-IDF — värdtestad i test/run.sh
 * (test_net_source_policy.c).
 *
 * Varför två källor alls: panelen kunde bara nå tokenservern på samma nät.
 * Ett gästnät med klientisolering, ett IoT-VLAN eller en Mac som bytt IP
 * räckte för att glaset skulle visa streck fast allt annat fungerade
 * (verkligt fall 2026-08-17: Solelkollen hämtade glatt över internet medan
 * VibePulse stod tomt). Reläet är en brevlåda dit tjänsten LÄGGER sina
 * färdiga siffror; panelen hämtar därifrån när LAN:et inte svarar.
 *
 * Två egenskaper som INTE får glida:
 *
 *  - Reläet är LÄSNING ONLY. Needs You-verdikt signeras med enhetsnyckeln
 *    och postas alltid till LAN-tjänsten, aldrig till reläet. Kan panelen
 *    inte nå LAN:et kan den inte svara — och då faller frågan tillbaka till
 *    terminalen, precis som när panelen är avstängd. Det är den befintliga,
 *    ärliga semantiken; den ska inte tänjas för bekvämlighet.
 *  - LAN först när LAN finns. Hemma ska datan komma från hemmet.
 *
 * Kostnaden att prova en död LAN-adress är en timeout per hämtning, och
 * fyra endpoints som var och en bränner tio sekunder gör panelen trög. När
 * reläet vunnit provas därför LAN bara med jämna mellanrum, och då med kort
 * tålamod.
 */

#include <stdbool.h>
#include <stdint.h>

typedef enum {
  TG_NET_SOURCE_LOCAL = 0, /* tokenservern på LAN:et */
  TG_NET_SOURCE_RELAY = 1, /* brevlådan på internet  */
} tg_net_source;

/* Hur ofta LAN provas igen när reläet är den som fungerar. Fem minuter:
 * kort nog att en hemkomst märks innan man hunnit undra, långt nog att en
 * bortarest inte betalar en timeout var 30:e sekund. */
#define TG_NET_LOCAL_REPROBE_US (300LL * 1000000LL)

/* Tålamod med LAN-adressen. Full väntan medan LAN är den som gäller; kort
 * väntan när det bara är ett återprov och reläet redan levererar. */
#define TG_NET_LOCAL_TIMEOUT_MS  10000
#define TG_NET_REPROBE_TIMEOUT_MS 2000

typedef struct {
  bool relay_won;          /* reläet är den som levererar just nu     */
  int64_t last_local_try_us; /* när LAN senast provades (0 = aldrig) */
} tg_net_source_state;

/* Vilken källa hämtningen ska börja med. */
tg_net_source tg_net_source_first(const tg_net_source_state *state,
                                  int64_t now_us);

/* Hur länge den källan får ta på sig. */
int tg_net_source_timeout_ms(const tg_net_source_state *state,
                             tg_net_source source);

/* Får vi falla vidare till reläet efter ett misslyckat försök? Bara om det
 * var LAN som föll — ett dött relä ska inte studsa tillbaka till ett LAN vi
 * just konstaterat är borta, i en evig runda. */
bool tg_net_source_may_fall_back(tg_net_source tried);

/* Bokför utfallet. Anropas EN gång per försök, i den ordning försöken
 * gjordes. */
void tg_net_source_note(tg_net_source_state *state, tg_net_source tried,
                        bool ok, int64_t now_us);

#endif
