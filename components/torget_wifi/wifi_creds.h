#ifndef TORGET_WIFI_CREDS_H
#define TORGET_WIFI_CREDS_H

/*
 * NVS-adaptern för nätverkslistan. All beslutslogik bor i wifi_slots.h —
 * den här filen gör ingenting annat än att läsa och skriva blobben.
 *
 * Lagring: EN blob (namnrymd "tgwifi", nyckel "slots") med hela
 * tg_wifi_slot-arrayen. En skrivning, en commit, ingen halvskriven lista
 * om strömmen går mitt i. Storleken kontrolleras vid läsning; ett blobb
 * med fel storlek (äldre eller nyare format) behandlas som tom lista i
 * stället för att tolkas fel.
 *
 * NVS-partitionen är INTE krypterad, så lösenorden ligger i klartext i
 * flashen. Det är samma exponering som secrets.h redan har (README:
 * "a stolen or lost screen leaks your WiFi password") — inte en ny klass
 * av risk, men skälet att en borttappad panel ska få sina nät roterade.
 *
 * OTA rör aldrig NVS (docs/ota.md), så listan överlever varje uppdatering.
 */

#include <stdbool.h>

#include "wifi_slots.h"

/* Läser hela listan. Saknad eller trasig blob ger en nollad array — en
 * panel utan minne är en panel som kör på secrets.h-botten, inte en panel
 * som fallerar. */
void tg_wifi_creds_load(tg_wifi_slot out[TG_WIFI_SLOTS]);

/* Skriver ett nät på rätt plats (uppdaterar ett känt, vräker det äldsta
 * när listan är full) och stämplar det som det senast lyckade. Validerar
 * via wifi_slots innan något rör flashen. */
bool tg_wifi_creds_remember(const char *ssid, const char *pass);

/* Höjer seq för ett nät som just gett IP, så listan sorterar sig själv
 * med det som faktiskt fungerar först. Okänt SSID (t.ex. hemnätet ur
 * secrets.h) är en tyst no-op — botten ska aldrig hamna i NVS. */
void tg_wifi_creds_mark_ok(const char *ssid);

/* Antal ihågkomna nät just nu — bara för loggen vid boot. */
int tg_wifi_creds_count(void);

#endif
