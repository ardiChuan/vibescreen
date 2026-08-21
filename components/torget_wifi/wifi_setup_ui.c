#include "wifi_setup_ui.h"

#include <stdio.h>
#include <string.h>

#include "lvgl.h"

#include "torget.h"
#include "wifi_qr_payload.h"
#include "wifi_slots.h"

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
 * ASCII — samma monofamilj som kommandoraden i Needs You) och de små
 * raderna i plex_ui_21.
 */

extern const lv_font_t plex_attention_52;
extern const lv_font_t plex_body_27;
extern const lv_font_t plex_mono_24;
extern const lv_font_t plex_ui_21;

#define COL_MUTED lv_color_hex(0x9298A2) /* palette.muted */

/* Innehållet hålls i en mittkolumn: glaset har klippta hörn, så text som
 * söker kanterna tappar tecken (hörnlärdomen från brödsmulorna). */
#define CONTENT_W 400

/* Saved in design/vibepulse/wifi-onboarding-design.json and checked against
 * it in test_wifi_onboarding_design.py. Keep these raw integer lines simple:
 * the validator deliberately parses them instead of trusting comments. */
#define WIFI_OPEN_WORD_Y        24
#define WIFI_OPEN_INSTRUCTION_Y 82
#define WIFI_OPEN_QR_X          142
#define WIFI_OPEN_QR_Y          108
#define WIFI_OPEN_QR_SIZE       196
#define WIFI_OPEN_SSID_Y        316
#define WIFI_OPEN_PASSWORD_Y    350
#define WIFI_OPEN_ADDRESS_Y     404
#define WIFI_OPEN_FOOTER_Y      442

static struct {
  lv_obj_t *overlay;
  lv_obj_t *qr;        /* one reusable I1 canvas; never churned per tick       */
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
  char rendered_qr_payload[TG_WIFI_QR_PAYLOAD_CAP];
  bool qr_available;
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

  ui.qr = lv_qrcode_create(ui.overlay);
  lv_qrcode_set_size(ui.qr, WIFI_OPEN_QR_SIZE);
  lv_qrcode_set_dark_color(ui.qr, lv_color_black());
  lv_qrcode_set_light_color(ui.qr, lv_color_white());
  lv_qrcode_set_quiet_zone(ui.qr, true);
  lv_obj_set_pos(ui.qr, WIFI_OPEN_QR_X, WIFI_OPEN_QR_Y);
  lv_obj_add_flag(ui.qr, LV_OBJ_FLAG_HIDDEN);

  ui.word = line(ui.overlay, &plex_attention_52, lv_color_white(), 52);
  ui.lead = line(ui.overlay, &plex_ui_21, COL_MUTED, 140);
  ui.primary = line(ui.overlay, &plex_body_27, lv_color_white(), 170);
  ui.secondary = line(ui.overlay, &plex_mono_24, lv_color_white(), 214);
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
    case TG_WIFI_UI_STARTING:  return "STARTING";
    case TG_WIFI_UI_OPEN:      return "WIFI SETUP";
    case TG_WIFI_UI_JOINING:   return "JOINING";
    case TG_WIFI_UI_JOINED:    return "ON THE NET";
    case TG_WIFI_UI_FAILED:    return "SETUP FAILED";
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

static void position(lv_obj_t *obj, int y) {
  lv_obj_align(obj, LV_ALIGN_TOP_MID, 0, y);
}

static bool update_qr(const char *ssid, const char *password) {
  char payload[TG_WIFI_QR_PAYLOAD_CAP];
  if (!tg_wifi_qr_payload(payload, sizeof payload, ssid, password)) {
    ui.rendered_qr_payload[0] = '\0';
    ui.qr_available = false;
    return false;
  }
  if (strcmp(payload, ui.rendered_qr_payload) == 0) return ui.qr_available;

  lv_result_t result = lv_qrcode_update(ui.qr, payload, strlen(payload));
  if (result != LV_RESULT_OK) {
    ui.rendered_qr_payload[0] = '\0';
    ui.qr_available = false;
    return false;
  }
  store(ui.rendered_qr_payload, sizeof ui.rendered_qr_payload, payload);
  ui.qr_available = true;
  return true;
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
    /* AP-lösenordet och QR-payloaden är bara till för det fysiska fönstret.
     * Döljning måste radera hela buffertarna, inte bara skriva ett NUL först. */
    memset(ui.rendered_secondary, 0, sizeof ui.rendered_secondary);
    memset(ui.rendered_qr_payload, 0, sizeof ui.rendered_qr_payload);
    ui.qr_available = false;
    lv_label_set_text(ui.secondary, "");
    lv_canvas_fill_bg(ui.qr, lv_color_white(), LV_OPA_COVER);
    lv_obj_add_flag(ui.overlay, LV_OBJ_FLAG_HIDDEN);
    torget_ui_unlock();
    return;
  }

  lv_label_set_text(ui.word, state_word(state));
  lv_label_set_text(ui.primary, primary ? primary : "");
  lv_label_set_text(ui.detail, detail ? detail : "");

  const bool open = (state == TG_WIFI_UI_OPEN);
  const bool qr_open = open && update_qr(primary, secondary);
  char password_line[TG_WIFI_PASS_CAP + 16];
  if (open && secondary && secondary[0])
    snprintf(password_line, sizeof password_line, "PASSWORD  %s", secondary);
  else
    snprintf(password_line, sizeof password_line, "OPEN NETWORK");
  lv_label_set_text(ui.secondary, open ? password_line : "");

  if (qr_open) {
    position(ui.word, WIFI_OPEN_WORD_Y);
    position(ui.lead, WIFI_OPEN_INSTRUCTION_Y);
    position(ui.primary, WIFI_OPEN_SSID_Y);
    position(ui.secondary, WIFI_OPEN_PASSWORD_Y);
    position(ui.hint1, WIFI_OPEN_ADDRESS_Y);
    position(ui.foot, WIFI_OPEN_FOOTER_Y);
    lv_label_set_text(ui.lead, "SCAN WITH YOUR PHONE");
    lv_label_set_text(ui.hint1, "OPEN  192.168.4.1  IF NEEDED");
    lv_label_set_text(ui.hint2, "");
  } else {
    position(ui.word, 52);
    position(ui.lead, 140);
    position(ui.primary, 170);
    position(ui.secondary, 214);
    position(ui.hint1, 278);
    position(ui.hint2, 306);
    position(ui.foot, 396);
    lv_label_set_text(ui.lead, open ? "JOIN THIS NETWORK" : "");
    lv_label_set_text(ui.hint1, open ? "THEN OPEN  192.168.4.1" : "");
    lv_label_set_text(ui.hint2, open ? "OR RUN  tools/wifi-here.sh" : "");
  }

  show(ui.lead, open);
  show(ui.qr, qr_open);
  show(ui.secondary, open);
  show(ui.hint1, open);
  show(ui.hint2, open && !qr_open);
  /* Orsaksraden och lösenordsraden delar y — bara ett av lägena har båda. */
  show(ui.detail, !open && detail && detail[0]);

  /* Foten: nedräkningen är ärlig data i båda lägena — kvarvarande lucktid
   * när fönstret är öppet, tid kvar tills det öppnar sig självt när
   * panelen letar. Utgången nämns bara när det finns en. */
  if (state == TG_WIFI_UI_STARTING) {
    lv_label_set_text(ui.foot, "PLEASE WAIT");
  } else if (state == TG_WIFI_UI_FAILED) {
    lv_label_set_text(ui.foot, "KEY3 CLOSES");
  } else if (seconds_left > 0) {
    char foot[48];
    bool closable = open || state == TG_WIFI_UI_JOINING ||
                    state == TG_WIFI_UI_JOINED;
    snprintf(foot, sizeof foot, closable ? "%02d:%02d   KEY3 CLOSES" : "%02d:%02d",
             seconds_left / 60, seconds_left % 60);
    lv_label_set_text(ui.foot, foot);
  } else {
    bool closable = open || state == TG_WIFI_UI_JOINING ||
                    state == TG_WIFI_UI_JOINED;
    lv_label_set_text(ui.foot, closable ? "KEY3 CLOSES"
                                        : "HOLD KEY3 FOR SETUP");
  }

  lv_obj_remove_flag(ui.overlay, LV_OBJ_FLAG_HIDDEN);
  /* Framför apparna, men OTA-overlayn skapas EFTER det här lagret och
   * hämtar sig själv längst fram i sin egen set() — READY-ringen vinner. */
  lv_obj_move_foreground(ui.overlay);
  torget_ui_unlock();
}
