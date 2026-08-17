#include "torget_http.h"

#include <stdatomic.h>
#include <string.h>

#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "net_source_policy.h"

static const char *TAG = "torget-http";

typedef struct {
  char *buf;
  size_t cap;
  size_t len;
  bool overflow;
} body_t;

static esp_err_t on_event(esp_http_client_event_t *evt) {
  if (evt->event_id != HTTP_EVENT_ON_DATA) return ESP_OK;

  body_t *b = (body_t *)evt->user_data;
  if (!b || b->overflow) return ESP_OK;

  if (b->len + (size_t)evt->data_len >= b->cap) {
    b->overflow = true;
    return ESP_OK;
  }
  memcpy(b->buf + b->len, evt->data, (size_t)evt->data_len);
  b->len += (size_t)evt->data_len;
  return ESP_OK;
}

static bool http_get_timeout(const char *url, char *buf, size_t cap,
                             size_t *len_out, int timeout_ms) {
  body_t body = { .buf = buf, .cap = cap };

  esp_http_client_config_t cfg = {
    .url = url,
    .method = HTTP_METHOD_GET,
    .event_handler = on_event,
    .user_data = &body,
    .crt_bundle_attach = esp_crt_bundle_attach,
    .timeout_ms = timeout_ms,
    /* Följ en eventuell omdirigering (apex → www och liknande) men inte i
     * all evighet. */
    .max_redirection_count = 3,
  };

  esp_http_client_handle_t client = esp_http_client_init(&cfg);
  if (!client) return false;

  bool ok = false;
  esp_err_t err = esp_http_client_perform(client);
  int status = esp_http_client_get_status_code(client);

  if (err != ESP_OK) {
    ESP_LOGW(TAG, "hämtning misslyckades: %s (%s)", esp_err_to_name(err), url);
  } else if (status != 200) {
    ESP_LOGW(TAG, "oväntad statuskod %d (%s)", status, url);
  } else if (body.overflow) {
    ESP_LOGW(TAG, "kroppen större än %u byte, avvisad (%s)", (unsigned)cap, url);
  } else {
    buf[body.len] = '\0';
    if (len_out) *len_out = body.len;
    ok = true;
  }

  esp_http_client_cleanup(client);
  return ok;
}

bool torget_http_get(const char *url, char *buf, size_t cap, size_t *len_out) {
  return http_get_timeout(url, buf, cap, len_out, TG_NET_LOCAL_TIMEOUT_MS);
}

/*
 * Växlingstillståndet delas av alla hämttasker, och avsiktligt utan lås:
 * fälten är två, båda skrivs bara med hela värden, och en kapad läsning av
 * tidsstämpeln kostar som mest ETT extra LAN-återprov. Ett mutex här hade
 * lagt en låsordning mellan apptaskarna för att skydda en optimering —
 * dyrare än felet det förhindrar. Atomära fält räcker för att undvika
 * odefinierat beteende på de 64 bitarna.
 */
static _Atomic bool s_relay_won;
static _Atomic int64_t s_last_local_try_us;

bool torget_http_get_failover(const char *lan_url, const char *relay_url,
                              char *buf, size_t cap, size_t *len_out) {
  if (!relay_url || !relay_url[0])
    return torget_http_get(lan_url, buf, cap, len_out);

  const int64_t now = esp_timer_get_time();
  tg_net_source_state state = {
    .relay_won = atomic_load(&s_relay_won),
    .last_local_try_us = atomic_load(&s_last_local_try_us),
  };

  tg_net_source source = tg_net_source_first(&state, now);
  const char *url = (source == TG_NET_SOURCE_LOCAL) ? lan_url : relay_url;
  bool ok = http_get_timeout(url, buf, cap, len_out,
                             tg_net_source_timeout_ms(&state, source));

  tg_net_source_note(&state, source, ok, now);
  atomic_store(&s_relay_won, state.relay_won);
  atomic_store(&s_last_local_try_us, state.last_local_try_us);

  if (ok || !tg_net_source_may_fall_back(source)) return ok;

  /* LAN föll — reläet är hela poängen med att vara på resa. */
  ESP_LOGI(TAG, "LAN svarade inte, provar reläet");
  ok = http_get_timeout(relay_url, buf, cap, len_out,
                        TG_NET_LOCAL_TIMEOUT_MS);
  tg_net_source_note(&state, TG_NET_SOURCE_RELAY, ok, now);
  atomic_store(&s_relay_won, state.relay_won);
  return ok;
}
