#include "wifi_setup_ui.h"

#include <stdio.h>
#include <string.h>

#include "lvgl.h"

#include "torget.h"

/*
 * Samma raster som OTA-ringen: äkta svart, lägesordet överst i
 * attention-fonten, muted för det som är sammanhang och vitt för det som
 * är svaret. Ingen provideraccent — det här är plattformens läge, inte en
 * apps. Native fontstorlekar, aldrig transformer (lagerläxan 2026-08-16).
 *
 * Fontvalen mot verklig glyftäckning (platform/fonts/fetch-and-convert.sh):
 * lägesordet i plex_attention_52 (bara versaler + mellanslag — därför är
 * varje ord i state_word() A-Z), nätnamnet i plex_body_27 (full ASCII: ett
 * SSID kan innehålla vad som helst), lösenordet i plex_mono_40 (mono, full
 * ASCII — samma hjälte-mono som kommandoraden i Needs You) och de små
 * raderna i plex_ui_21.
 */

extern const lv_font_t plex_attention_52;
extern const lv_font_t plex_body_27;
extern const lv_font_t plex_mono_40;
extern const lv_font_t plex_ui_21;

#define COL_MUTED lv_color_hex(0x9298A2) /* palette.muted */

/* Innehållet hålls i en mittkolumn: glaset har klippta hörn, så text som
 * söker kanterna tappar tecken (hörnlärdomen från brödsmulorna). */
#define CONTENT_W 400

static struct {
  lv_obj_t *overlay;
  lv_obj_t *word;      /* WIFI SETUP / NO NETWORK / JOINING / ON THE NET  */
  lv_obj_t *lead;      /* liten muted rad ovanför nätnamnet               */
  lv_obj_t *primary;   /* nätnamnet                                       */
  lv_obj_t *secondary; /* setupfönstrets lösenord (mono)                  */
  lv_obj_t *hint1;     /* "THEN OPEN 192.168.4.1"                         */
  lv_obj_t *hint2;     /* "OR RUN tools/wifi-here.sh"                     */
  lv_obj_t *detail;    /* ärlig orsaksrad                                 */
  lv_obj_t *foot;      /* nedräkning + utgången                           */
  tg_wifi_ui_state rendered_state;
  char rendered_primary[64];
  char rendered_secondary[32];
  char rendered_detail[64];
  int rendered_seconds;
} ui;

static lv_obj_t *line(lv_obj_t *parent, const lv_font_t *font, lv_color_t color,
                      int y) {
  lv_obj_t *label = lv_label_create(parent);
  lv_obj_set_style_text_font(label, font, 0);
  lv_obj_set_style_text_color(label, color, 0);
  lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, 0);
  /* Bredd + LV_LABEL_LONG_DOT: ett SSID kan vara 32 tecken och får
   * klippas snyggt i stället för att spilla ut över de klippta hörnen. */
  lv_obj_set_width(label, CONTENT_W);
  lv_label_set_long_mode(label, LV_LABEL_LONG_DOT);
  lv_obj_align(label, LV_ALIGN_TOP_MID, 0, y);
  lv_label_set_text(label, "");
  return label;
}

void torget_wifi_ui_create(void) {
  /* Topplagret, inte appträdet — samma regel som OTA-overlayn. Kallas
   * under anroparens UI-lås. */
  ui.overlay = lv_obj_create(lv_layer_top());
  lv_obj_remove_style_all(ui.overlay);
  lv_obj_set_size(ui.overlay, 480, 480);
  lv_obj_set_pos(ui.overlay, 0, 0);
  lv_obj_set_style_bg_color(ui.overlay, lv_color_black(), 0);
  lv_obj_set_style_bg_opa(ui.overlay, LV_OPA_COVER, 0);
  /* Slukar touch: fingret ska inte nå apparna bakom svart glas. Lagret
   * bär medvetet INGEN knapp — allt som kan ändra nätet ska ske via
   * accesspunkten, aldrig via en tapp som råkar landa fel. */
  lv_obj_add_flag(ui.overlay, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_flag(ui.overlay, LV_OBJ_FLAG_HIDDEN);

  ui.word = line(ui.overlay, &plex_attention_52, lv_color_white(), 52);
  ui.lead = line(ui.overlay, &plex_ui_21, COL_MUTED, 140);
  ui.primary = line(ui.overlay, &plex_body_27, lv_color_white(), 170);
  ui.secondary = line(ui.overlay, &plex_mono_40, lv_color_white(), 214);
  ui.hint1 = line(ui.overlay, &plex_ui_21, COL_MUTED, 278);
  ui.hint2 = line(ui.overlay, &plex_ui_21, COL_MUTED, 306);
  ui.detail = line(ui.overlay, &plex_ui_21, COL_MUTED, 214);
  ui.foot = line(ui.overlay, &plex_ui_21, COL_MUTED, 396);

  lv_obj_set_style_text_letter_space(ui.lead, 2, 0);
  lv_obj_set_style_text_letter_space(ui.hint1, 2, 0);
  lv_obj_set_style_text_letter_space(ui.hint2, 2, 0);
  lv_obj_set_style_text_letter_space(ui.foot, 2, 0);

  ui.rendered_state = TG_WIFI_UI_HIDDEN;
}

static const char *state_word(tg_wifi_ui_state state) {
  /* Bara A-Z och mellanslag: plex_attention_52 bär inga andra glyfer. */
  switch (state) {
    case TG_WIFI_UI_SEARCHING: return "NO NETWORK";
    case TG_WIFI_UI_OPEN:      return "WIFI SETUP";
    case TG_WIFI_UI_JOINING:   return "JOINING";
    case TG_WIFI_UI_JOINED:    return "ON THE NET";
    default:                   return "";
  }
}

static void show(lv_obj_t *obj, bool visible) {
  if (visible) lv_obj_remove_flag(obj, LV_OBJ_FLAG_HIDDEN);
  else lv_obj_add_flag(obj, LV_OBJ_FLAG_HIDDEN);
}

static bool same(const char *rendered, const char *incoming) {
  return strcmp(rendered, incoming ? incoming : "") == 0;
}

static void store(char *dst, size_t cap, const char *src) {
  snprintf(dst, cap, "%s", src ? src : "");
}

void torget_wifi_ui_set(tg_wifi_ui_state state, const char *primary,
                        const char *secondary, const char *detail,
                        int seconds_left) {
  if (!ui.overlay) return;
  if (seconds_left < 0) seconds_left = 0;
  if (seconds_left > 99 * 60 + 59) seconds_left = 99 * 60 + 59;

  /* Tidsbegränsat lås: får vi inte UI-låset på 200 ms hoppar vi över den
   * här bildrutan i stället för att blockera. Samma regel som
   * torget_ota_ui_set — en vakt som står fast i ett evigt låsförsök var
   * exakt så panelen frös 2026-08-14. */
  if (!torget_ui_try_lock(200)) return;

  /* Vakten pollar varje halvsekund och får inte invalidera pixlar som inte
   * bytt värde. Nyckeln läses under låset. */
  if (state == ui.rendered_state && same(ui.rendered_primary, primary) &&
      same(ui.rendered_secondary, secondary) &&
      same(ui.rendered_detail, detail) && seconds_left == ui.rendered_seconds) {
    torget_ui_unlock();
    return;
  }
  ui.rendered_state = state;
  store(ui.rendered_primary, sizeof ui.rendered_primary, primary);
  store(ui.rendered_secondary, sizeof ui.rendered_secondary, secondary);
  store(ui.rendered_detail, sizeof ui.rendered_detail, detail);
  ui.rendered_seconds = seconds_left;

  if (state == TG_WIFI_UI_HIDDEN) {
    lv_obj_add_flag(ui.overlay, LV_OBJ_FLAG_HIDDEN);
    torget_ui_unlock();
    return;
  }

  lv_label_set_text(ui.word, state_word(state));
  lv_label_set_text(ui.primary, primary ? primary : "");
  lv_label_set_text(ui.secondary, secondary ? secondary : "");
  lv_label_set_text(ui.detail, detail ? detail : "");

  const bool open = (state == TG_WIFI_UI_OPEN);
  lv_label_set_text(ui.lead, open ? "JOIN THIS NETWORK" : "");
  lv_label_set_text(ui.hint1, open ? "THEN OPEN  192.168.4.1" : "");
  lv_label_set_text(ui.hint2, open ? "OR RUN  tools/wifi-here.sh" : "");

  show(ui.lead, open);
  show(ui.secondary, open && secondary && secondary[0]);
  show(ui.hint1, open);
  show(ui.hint2, open);
  /* Orsaksraden och lösenordsraden delar y — bara ett av lägena har båda. */
  show(ui.detail, !open && detail && detail[0]);

  /* Foten: nedräkningen är ärlig data i båda lägena — kvarvarande lucktid
   * när fönstret är öppet, tid kvar tills det öppnar sig självt när
   * panelen letar. Utgången nämns bara när det finns en. */
  if (seconds_left > 0) {
    char foot[48];
    snprintf(foot, sizeof foot, open ? "%02d:%02d   KEY3 CLOSES" : "%02d:%02d",
             seconds_left / 60, seconds_left % 60);
    lv_label_set_text(ui.foot, foot);
  } else {
    lv_label_set_text(ui.foot, open ? "KEY3 CLOSES" : "HOLD KEY3 FOR SETUP");
  }

  lv_obj_remove_flag(ui.overlay, LV_OBJ_FLAG_HIDDEN);
  /* Framför apparna, men OTA-overlayn skapas EFTER det här lagret och
   * hämtar sig själv längst fram i sin egen set() — READY-ringen vinner. */
  lv_obj_move_foreground(ui.overlay);
  torget_ui_unlock();
}
