/*
 * The Needs You answer channel. A tap resolves the takeover on the glass
 * immediately (agent_monitor marks it answered), then hands the verdict here;
 * a worker task signs it and POSTs it so the UI never waits on the network.
 * Compiled out entirely without a device key: the screens stay display-only.
 */
#include "esp_log.h"

#include "needs_you_net.h"
#include "secrets.h"

static const char *TAG = "needs-you-net";

#ifdef TK_VIBEPULSE_DEVICE_KEY

#include <string.h>
#include <time.h>

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

#include "esp_http_client.h"

#include "agent_monitor.h"
#include "agent_status.h"
#include "needs_you_send_policy.h"

/* The verdict a tap produced, captured on the UI thread and drained by the
 * sender. verdict_name points at a static string, so it is safe to queue. */
typedef struct {
  bool panic;
  tk_agent_provider provider;
  bool has_view_sha256;
  const char *verdict_name;
  uint64_t ts;
  char request_id[TK_PENDING_ID_CAP];
  char view_sha256[TK_PENDING_VIEW_SHA256_CAP];
} verdict_item;

static QueueHandle_t s_queue;

static void enqueue(const verdict_item *item) {
  if (!s_queue) return;
  /* Non-blocking on purpose: if the sender is wedged on a stalled network, a
   * dropped verdict still falls back to the terminal via the bridge timeout.
   * Better a lost answer than a frozen UI thread. */
  if (xQueueSend(s_queue, item, 0) != pdTRUE)
    ESP_LOGW(TAG, "verdict-kön full — hoppar över, terminalen tar över");
}

static void needs_you_send_cb(tk_needs_you_verdict verdict,
                              const tk_pending_interaction *pending) {
  const char *name = tk_needs_you_verdict_name(verdict);
  if (!name || !pending || !pending->present) return;
  if (pending->provider != TK_AGENT_PROVIDER_CLAUDE &&
      pending->provider != TK_AGENT_PROVIDER_CODEX) {
    return;
  }
  /* Codex must never fall through to the legacy signature. The parser already
   * enforces this, and this second gate keeps malformed internal calls safe. */
  if (pending->provider == TK_AGENT_PROVIDER_CODEX &&
      !pending->has_view_sha256) {
    ESP_LOGE(TAG, "Codex-svar saknar vybindning — skickar inte");
    return;
  }
  if (pending->has_view_sha256 &&
      pending->view_sha256[TK_PENDING_VIEW_SHA256_CAP - 1] != '\0') {
    return;
  }
  verdict_item item = {
    .panic = false,
    .provider = pending->provider,
    .has_view_sha256 = pending->has_view_sha256,
    .verdict_name = name,
    .ts = (uint64_t)time(NULL),
  };
  strncpy(item.request_id, pending->request_id, sizeof item.request_id - 1);
  item.request_id[sizeof item.request_id - 1] = '\0';
  if (pending->has_view_sha256) {
    memcpy(item.view_sha256, pending->view_sha256, sizeof item.view_sha256);
  }
  enqueue(&item);
}

void tk_needs_you_send_panic(void) {
  verdict_item item = {
    .panic = true, .verdict_name = "deny", .ts = (uint64_t)time(NULL),
  };
  memcpy(item.request_id, "panic", sizeof "panic");
  enqueue(&item);
}

static void post_verdict(const verdict_item *item) {
  char message[TK_NEEDS_YOU_MESSAGE_CAP];
  char hmac_hex[TK_NEEDS_YOU_HMAC_HEX_CAP];
  char body[TK_NEEDS_YOU_BODY_CAP];
  char url[128];

  if (item->panic) {
    if (tk_needs_you_canonical_message(message, sizeof message,
                                       item->request_id, item->verdict_name,
                                       item->ts) < 0) {
      return;
    }
    tk_needs_you_hmac_hex(hmac_hex, TK_VIBEPULSE_DEVICE_KEY, message);
    if (tk_needs_you_panic_body(body, sizeof body, item->ts, hmac_hex) < 0)
      return;
    int written = snprintf(url, sizeof url, "%s/api/panic",
                           TK_VIBEPULSE_BASE_URL);
    if (written < 0 || (size_t)written >= sizeof url) return;
  } else {
    const char *provider = item->provider == TK_AGENT_PROVIDER_CODEX
                               ? "codex"
                               : "claude";
    if (item->has_view_sha256) {
      if (tk_needs_you_canonical_message_v2(
              message, sizeof message, provider, item->request_id,
              item->view_sha256, item->verdict_name, item->ts) < 0) {
        return;
      }
      tk_needs_you_hmac_hex(hmac_hex, TK_VIBEPULSE_DEVICE_KEY, message);
      if (tk_needs_you_answer_body_v2(
              body, sizeof body, provider, item->view_sha256,
              item->verdict_name, item->ts, hmac_hex) < 0) {
        return;
      }
    } else {
      if (item->provider != TK_AGENT_PROVIDER_CLAUDE) return;
      if (tk_needs_you_canonical_message(message, sizeof message,
                                         item->request_id,
                                         item->verdict_name, item->ts) < 0) {
        return;
      }
      tk_needs_you_hmac_hex(hmac_hex, TK_VIBEPULSE_DEVICE_KEY, message);
      if (tk_needs_you_answer_body(body, sizeof body, item->verdict_name,
                                   item->ts, hmac_hex) < 0) {
        return;
      }
    }
    int written = snprintf(url, sizeof url, "%s/api/interaction/%s",
                           TK_VIBEPULSE_BASE_URL, item->request_id);
    if (written < 0 || (size_t)written >= sizeof url) return;
  }

  esp_http_client_config_t cfg = {
    .url = url,
    .method = HTTP_METHOD_POST,
    .timeout_ms = 2500,
  };
  esp_http_client_handle_t client = esp_http_client_init(&cfg);
  if (!client) return;
  esp_http_client_set_header(client, "Content-Type", "application/json");
  esp_http_client_set_post_field(client, body, strlen(body));
  esp_err_t err = esp_http_client_perform(client);
  int status = err == ESP_OK ? esp_http_client_get_status_code(client) : -1;
  esp_http_client_cleanup(client);

  /* Nothing clever on failure: the takeover already left the glass, the bridge
   * deletes on resolve (so a repeat tap is safe) and refuses a stale one, and
   * an unanswered interaction falls back to the terminal on timeout. */
  if (err != ESP_OK || status != 200) {
    ESP_LOGW(TAG, "%s misslyckades (%s, HTTP %d) — terminalen tar beslutet",
             item->panic ? "panik" : item->verdict_name,
             esp_err_to_name(err), status);
    (void)tk_needs_you_send_should_retry(status); /* documented: never */
  } else {
    ESP_LOGI(TAG, "skickade %s för %s", item->verdict_name, item->request_id);
  }
}

static void needs_you_net_task(void *arg) {
  (void)arg;
  verdict_item item;
  for (;;) {
    if (xQueueReceive(s_queue, &item, portMAX_DELAY) == pdTRUE)
      post_verdict(&item);
  }
}

void tokens_needs_you_net_start(void) {
  s_queue = xQueueCreate(4, sizeof(verdict_item));
  if (!s_queue) {
    ESP_LOGE(TAG, "kunde inte skapa verdict-kön — Needs You blir display-only");
    return;
  }
  tk_agent_monitor_set_needs_you_cb(needs_you_send_cb);
  xTaskCreate(needs_you_net_task, "needs-you-net", 6144, NULL, 5, NULL);
  ESP_LOGI(TAG, "Needs You-svarskanalen igång (enhetsnyckel finns)");
}

#else /* no device key: the screens answer no one */

void tokens_needs_you_net_start(void) {
  ESP_LOGW(TAG, "TK_VIBEPULSE_DEVICE_KEY saknas — Needs You är display-only");
}

void tk_needs_you_send_panic(void) {}

#endif
