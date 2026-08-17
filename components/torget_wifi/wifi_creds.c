#include "wifi_creds.h"

#include <string.h>

#include "esp_log.h"
#include "nvs.h"
#include "nvs_flash.h"

static const char *TAG = "wifi-creds";

/* NVS-nycklar har ett tak på 15 tecken — båda ligger med marginal under. */
#define CREDS_NAMESPACE "tgwifi"
#define CREDS_KEY       "slots"

static bool open_ns(nvs_open_mode_t mode, nvs_handle_t *out) {
  esp_err_t err = nvs_open(CREDS_NAMESPACE, mode, out);
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "kunde inte öppna %s: %s", CREDS_NAMESPACE,
             esp_err_to_name(err));
    return false;
  }
  return true;
}

void tg_wifi_creds_load(tg_wifi_slot out[TG_WIFI_SLOTS]) {
  memset(out, 0, sizeof(tg_wifi_slot) * TG_WIFI_SLOTS);

  nvs_handle_t handle;
  if (!open_ns(NVS_READONLY, &handle)) return;

  size_t len = sizeof(tg_wifi_slot) * TG_WIFI_SLOTS;
  esp_err_t err = nvs_get_blob(handle, CREDS_KEY, out, &len);
  nvs_close(handle);

  if (err == ESP_ERR_NVS_NOT_FOUND) return; /* färsk panel, inte ett fel */
  if (err != ESP_OK || len != sizeof(tg_wifi_slot) * TG_WIFI_SLOTS) {
    /* Fel storlek = annat format än det här bygget känner. Hellre tom
     * lista (och secrets.h-botten) än fält tolkade på fel offset. */
    ESP_LOGW(TAG, "listan förkastad (%s, %u byte) — kör på secrets.h",
             esp_err_to_name(err), (unsigned)len);
    memset(out, 0, sizeof(tg_wifi_slot) * TG_WIFI_SLOTS);
    return;
  }

  /* Upstream är fientlig, även när upstream är vår egen flash: NUL-terminera
   * varje sträng innan någon annan läser dem som text (läxan 2026-08-13). */
  for (int i = 0; i < TG_WIFI_SLOTS; i++) {
    out[i].ssid[TG_WIFI_SSID_CAP - 1] = '\0';
    out[i].pass[TG_WIFI_PASS_CAP - 1] = '\0';
  }
}

static bool save(const tg_wifi_slot *slots) {
  nvs_handle_t handle;
  if (!open_ns(NVS_READWRITE, &handle)) return false;

  esp_err_t err =
      nvs_set_blob(handle, CREDS_KEY, slots,
                   sizeof(tg_wifi_slot) * TG_WIFI_SLOTS);
  if (err == ESP_OK) err = nvs_commit(handle);
  nvs_close(handle);

  if (err != ESP_OK) {
    ESP_LOGW(TAG, "listan kunde inte sparas: %s", esp_err_to_name(err));
    return false;
  }
  return true;
}

bool tg_wifi_creds_remember(const char *ssid, const char *pass) {
  if (!tg_wifi_ssid_valid(ssid) || !tg_wifi_pass_valid(pass)) {
    /* SSID:t loggas inte här: en ogiltig sträng är per definition en
     * sträng vi inte vill skriva ut. Storleken räcker som diagnos. */
    ESP_LOGW(TAG, "avvisade ogiltiga uppgifter");
    return false;
  }

  tg_wifi_slot slots[TG_WIFI_SLOTS];
  tg_wifi_creds_load(slots);

  int idx = tg_wifi_slot_for_write(slots, TG_WIFI_SLOTS, ssid);
  if (idx < 0) return false;

  uint32_t seq = tg_wifi_seq_next(slots, TG_WIFI_SLOTS);
  memset(&slots[idx], 0, sizeof slots[idx]);
  strncpy(slots[idx].ssid, ssid, TG_WIFI_SSID_CAP - 1);
  strncpy(slots[idx].pass, pass, TG_WIFI_PASS_CAP - 1);
  slots[idx].seq = seq;

  if (!save(slots)) return false;
  /* Lösenordet skrivs aldrig ut; nätets namn gör felsökning möjlig. */
  ESP_LOGI(TAG, "minns \"%s\" på plats %d", ssid, idx);
  return true;
}

void tg_wifi_creds_mark_ok(const char *ssid) {
  tg_wifi_slot slots[TG_WIFI_SLOTS];
  tg_wifi_creds_load(slots);

  int idx = tg_wifi_slot_find(slots, TG_WIFI_SLOTS, ssid);
  if (idx < 0) return; /* secrets.h-botten hamnar aldrig i NVS */

  uint32_t seq = tg_wifi_seq_next(slots, TG_WIFI_SLOTS);
  /* Ligger den redan överst är skrivningen ren flashslitage: listan
   * sorterar likadant vare sig seq är 9 eller 10. */
  if (slots[idx].seq >= seq - 1) return;
  slots[idx].seq = seq;
  save(slots);
}

int tg_wifi_creds_count(void) {
  tg_wifi_slot slots[TG_WIFI_SLOTS];
  tg_wifi_creds_load(slots);
  int n = 0;
  for (int i = 0; i < TG_WIFI_SLOTS; i++)
    if (slots[i].seq != 0 && slots[i].ssid[0] != '\0') n++;
  return n;
}
