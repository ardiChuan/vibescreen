#ifndef TORGET_WIFI_SETUP_UI_H
#define TORGET_WIFI_SETUP_UI_H

#include <stdbool.h>

/*
 * Glasets nätverkslager. Två jobb i ETT lager:
 *
 *  1. Den ärliga nätsidan. Utan nät visade panelen förut bara streck och
 *     NO DATA, utan ett ord om varför (docs/agent-setup.md: "shows dashes
 *     forever, with no error anywhere to tell you why"). Nu står det vilket
 *     nät den jagar och vad radion faktiskt svarade.
 *  2. Setupfönstret. När panelen rest sin egen accesspunkt står nätnamnet
 *     och lösenordet i läsbar typ på glaset — det är den fysiska närvaron
 *     som är grinden, precis som KEY3-hållet är det för OTA.
 *
 * Lagerordning: skapas på lv_layer_top FÖRE torget_ota_ui_create, så en
 * OTA-omstarts READY-ring alltid vinner över nätlagret.
 *
 * Trådregel: set() tar UI-låset självt med samma 200 ms-tålamod som
 * torget_ota_ui_set — anropas från setupvakten, aldrig LVGL-tasken.
 */

typedef enum {
  TG_WIFI_UI_HIDDEN = 0,
  TG_WIFI_UI_SEARCHING, /* inget nät än; fönstret är inte öppet          */
  TG_WIFI_UI_STARTING,  /* begärt; skanning/AP/portal startar            */
  TG_WIFI_UI_OPEN,      /* accesspunkten uppe, väntar på uppgifter       */
  TG_WIFI_UI_JOINING,   /* uppgifter mottagna, provar dem                */
  TG_WIFI_UI_JOINED,    /* IP! lagret kliver av om ett ögonblick         */
  TG_WIFI_UI_FAILED,    /* startgrinden eller AP-starten vägrade         */
} tg_wifi_ui_state;

void torget_wifi_ui_create(void);

/*
 * primary  — nätnamnet raden handlar om (jagat, erbjudet eller anslutet).
 * secondary— setupfönstrets lösenord, eller NULL.
 * detail   — en ärlig rad om varför det inte gick, eller NULL.
 * seconds_left — nedräkning i foten; <= 0 döljer den.
 */
void torget_wifi_ui_set(tg_wifi_ui_state state, const char *primary,
                        const char *secondary, const char *detail,
                        int seconds_left);

/* Växlar enbart den lokala presentationen mellan QR och manuell reservväg.
 * Inga nätuppgifter ändras och anrop utanför ett öppet setupfönster ignoreras. */
void torget_wifi_ui_set_manual_details(bool visible);

#endif
