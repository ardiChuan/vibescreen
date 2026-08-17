#include "wifi_setup.h"

#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#include <sys/time.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "lwip/sockets.h"

#include "esp_heap_caps.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "mbedtls/sha256.h"

#include "ota_service.h"
#include "secrets.h"
#include "wifi_creds.h"
#include "wifi_form.h"
#include "wifi_setup_ui.h"
#include "wifi_slots.h"

static const char *TAG = "wifi-setup";

#define AP_SSID     "VibePulse-setup"
#define AP_ADDRESS  "192.168.4.1" /* esp_netif:s default för AP-gränssnittet */
#define AP_CHANNEL  1
#define AP_MAX_CONN 2

/* Så många nät setupsidan listar. Fler än så är en rullningslista ingen
 * orkar läsa, och listan bor i .bss — inte på en tasks stack. */
#define SCAN_MAX 16

static struct {
  char ssid[SCAN_MAX][TG_WIFI_SSID_CAP];
  int8_t rssi[SCAN_MAX];
  int n;
} s_scan;

static const tg_wifi_setup_hooks *s_hooks;
static httpd_handle_t s_server;
static esp_netif_t *s_ap_netif;
static char s_ap_pass[13]; /* 12 hex + NUL */

/* Fönstrets tillstånd ägs av vakttasken; flaggorna korsar taskgränser och
 * är därför atomära (samma disciplin som ota_service). */
static atomic_bool s_open;
static atomic_bool s_want_open;
static atomic_bool s_want_close;
static atomic_bool s_dns_stop;
static _Atomic int64_t s_joined_at_us; /* satt av POST /join, läst av vakten */
static char s_joined_ssid[TG_WIFI_SSID_CAP];

/* ------------------------------------------------------ AP-lösenordet */

/*
 * Med TG_OTA_TOKEN i secrets.h HÄRLEDS lösenordet ur token, så
 * tools/wifi-here.sh kan räkna fram exakt samma sträng på Macen och
 * ansluta utan att någon läser av glaset. Det ger ingen ny behörighet:
 * den som redan har token kan skriva firmware till panelen.
 *
 * Utan token blir lösenordet slumpat per fönster och finns bara på glaset.
 * Domänsträngen gör härledningen skild från token självt — samma hemlighet,
 * två separata nycklar.
 */
static void derive_ap_password(void) {
#ifdef TG_OTA_TOKEN
  static const char domain[] = "vibepulse-softap-v1";
  unsigned char digest[32];
  mbedtls_sha256_context ctx;
  mbedtls_sha256_init(&ctx);
  mbedtls_sha256_starts(&ctx, 0);
  mbedtls_sha256_update(&ctx, (const unsigned char *)domain, sizeof domain - 1);
  mbedtls_sha256_update(&ctx, (const unsigned char *)TG_OTA_TOKEN,
                        strlen(TG_OTA_TOKEN));
  mbedtls_sha256_finish(&ctx, digest);
  mbedtls_sha256_free(&ctx);
  for (int i = 0; i < 6; i++)
    snprintf(s_ap_pass + i * 2, 3, "%02x", digest[i]);
#else
  for (int i = 0; i < 6; i++)
    snprintf(s_ap_pass + i * 2, 3, "%02x", (unsigned)(esp_random() & 0xFF));
#endif
  s_ap_pass[12] = '\0';
}

/* ------------------------------------------------------------- skanning */

static void scan_networks(void) {
  s_scan.n = 0;
  if (esp_wifi_scan_start(NULL, true) != ESP_OK) {
    ESP_LOGW(TAG, "skanningen gick inte att starta");
    return;
  }
  static wifi_ap_record_t ap[SCAN_MAX]; /* .bss, inte stacken */
  uint16_t n = SCAN_MAX;
  if (esp_wifi_scan_get_ap_records(&n, ap) != ESP_OK) return;

  for (int i = 0; i < (int)n && s_scan.n < SCAN_MAX; i++) {
    const char *ssid = (const char *)ap[i].ssid;
    /* Dolda nät har tomt SSID och kan inte väljas ur en lista; ett SSID
     * med styrtecken hör inte hemma i HTML:en (upstream är fientlig). */
    if (!tg_wifi_ssid_valid(ssid)) continue;
    bool dupe = false;
    for (int j = 0; j < s_scan.n; j++)
      if (strcmp(s_scan.ssid[j], ssid) == 0) dupe = true;
    if (dupe) continue;
    snprintf(s_scan.ssid[s_scan.n], TG_WIFI_SSID_CAP, "%s", ssid);
    s_scan.rssi[s_scan.n] = ap[i].rssi;
    s_scan.n++;
  }

  /* Starkast först. Nätet man står bredvid ska ligga överst i listan, inte
   * på plats nio bland grannarnas — och det är panelens signalstyrka som
   * gäller, inte telefonens. Insättningssortering på högst 16 poster.
   *
   * memcpy, inte snprintf: raderna är fasta och åtskilda, men båda bor i
   * s_scan och GCC:s restrict-analys avvisar (med rätta) en strängkopiering
   * där käll- och målobjekt är samma. En radflytt är en blockkopia. */
  for (int i = 1; i < s_scan.n; i++) {
    char ssid[TG_WIFI_SSID_CAP];
    memcpy(ssid, s_scan.ssid[i], TG_WIFI_SSID_CAP);
    int8_t rssi = s_scan.rssi[i];
    int j = i - 1;
    while (j >= 0 && s_scan.rssi[j] < rssi) {
      memmove(s_scan.ssid[j + 1], s_scan.ssid[j], TG_WIFI_SSID_CAP);
      s_scan.rssi[j + 1] = s_scan.rssi[j];
      j--;
    }
    memcpy(s_scan.ssid[j + 1], ssid, TG_WIFI_SSID_CAP);
    s_scan.rssi[j + 1] = rssi;
  }
  ESP_LOGI(TAG, "setupfönstret ser %d nät", s_scan.n);
}

/* ------------------------------------------------------------ http-sidan */

static const char PAGE_HEAD[] =
    "<!doctype html><html><head><meta charset=\"utf-8\">"
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
    "<title>VibePulse</title><style>"
    "body{font-family:-apple-system,system-ui,sans-serif;background:#0b0b0c;"
    "color:#eaeaea;margin:0;padding:28px 20px;max-width:420px}"
    "h1{font-size:19px;letter-spacing:.08em;text-transform:uppercase}"
    "p{color:#9298a2;font-size:14px;line-height:1.5}"
    "select,input,button{font-size:17px;padding:12px;width:100%;"
    "box-sizing:border-box;margin:6px 0;border-radius:10px;"
    "border:1px solid #303238;background:#151517;color:#eaeaea}"
    "button{background:#eaeaea;color:#0b0b0c;font-weight:600;border:0;"
    "margin-top:14px}"
    "</style></head><body><h1>VibePulse</h1>"
    "<p>Pick the network this panel should join. It is remembered, so the "
    "next time you are here it joins by itself.</p>"
    "<form method=\"POST\" action=\"/join\">"
    "<select name=\"ssid\">";

static const char PAGE_TAIL[] =
    "</select>"
    "<input name=\"pass\" type=\"password\" autocapitalize=\"off\" "
    "autocorrect=\"off\" placeholder=\"Password (leave blank if open)\">"
    "<button type=\"submit\">Join</button></form></body></html>";

static esp_err_t page_get(httpd_req_t *req) {
  httpd_resp_set_type(req, "text/html");
  httpd_resp_send_chunk(req, PAGE_HEAD, HTTPD_RESP_USE_STRLEN);

  char escaped[TG_WIFI_SSID_CAP * 6 + 1];
  char option[sizeof escaped + 64];
  for (int i = 0; i < s_scan.n; i++) {
    tg_wifi_html_escape(s_scan.ssid[i], escaped, sizeof escaped);
    int len = snprintf(option, sizeof option, "<option>%s</option>", escaped);
    if (len > 0) httpd_resp_send_chunk(req, option, (ssize_t)len);
  }
  if (s_scan.n == 0)
    httpd_resp_send_chunk(req, "<option></option>", HTTPD_RESP_USE_STRLEN);

  httpd_resp_send_chunk(req, PAGE_TAIL, HTTPD_RESP_USE_STRLEN);
  httpd_resp_send_chunk(req, NULL, 0);
  return ESP_OK;
}

static esp_err_t join_post(httpd_req_t *req) {
  /* Taket är generöst mot ett långt SSID + PSK och snålt mot allt annat:
   * kroppen bor på stacken i httpd-tasken. */
  char body[320];
  if (req->content_len <= 0 || req->content_len >= (int)sizeof body) {
    httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "body size");
    return ESP_FAIL;
  }
  int got = httpd_req_recv(req, body, (size_t)req->content_len);
  if (got <= 0) {
    httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "short body");
    return ESP_FAIL;
  }
  body[got] = '\0';

  char ssid[TG_WIFI_SSID_CAP] = {0};
  char pass[TG_WIFI_PASS_CAP] = {0};
  if (!tg_wifi_form_field(body, "ssid", ssid, sizeof ssid)) {
    httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "ssid missing");
    return ESP_FAIL;
  }
  /* Lösenordet får saknas helt — det är ett öppet nät, inte ett fel. */
  if (!tg_wifi_form_field(body, "pass", pass, sizeof pass)) pass[0] = '\0';

  if (!tg_wifi_ssid_valid(ssid) || !tg_wifi_pass_valid(pass)) {
    httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "invalid credentials");
    return ESP_FAIL;
  }
  if (!tg_wifi_creds_remember(ssid, pass)) {
    httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "store failed");
    return ESP_FAIL;
  }

  /* Vakten äger radion: den läser flaggan vid nästa poll och byter nät.
   * Att koppla om härifrån vore att röra WiFi-stacken från httpd-tasken. */
  snprintf(s_joined_ssid, sizeof s_joined_ssid, "%s", ssid);
  atomic_store(&s_joined_at_us, esp_timer_get_time());

  char escaped[TG_WIFI_SSID_CAP * 6 + 1];
  tg_wifi_html_escape(ssid, escaped, sizeof escaped);
  char page[sizeof escaped + 512];
  snprintf(page, sizeof page,
           "<!doctype html><html><head><meta charset=\"utf-8\"><title>VibePulse"
           "</title></head><body style=\"font-family:-apple-system,system-ui,"
           "sans-serif;background:#0b0b0c;color:#eaeaea;padding:28px\">"
           "<h1 style=\"font-size:19px\">Joining %s</h1>"
           "<p style=\"color:#9298a2\">Watch the panel. This network is "
           "remembered.</p></body></html>",
           escaped);
  httpd_resp_set_type(req, "text/html");
  httpd_resp_sendstr(req, page);
  ESP_LOGI(TAG, "nya uppgifter för \"%s\" mottagna", ssid);
  return ESP_OK;
}

/* Allt annat pekas tillbaka till sidan. Det är det som får iOS och Android
 * att öppna portalen av sig själva i stället för att bara varna om att
 * nätet saknar internet. */
static esp_err_t catch_all_get(httpd_req_t *req) {
  httpd_resp_set_status(req, "302 Found");
  httpd_resp_set_hdr(req, "Location", "http://" AP_ADDRESS "/");
  httpd_resp_send(req, NULL, 0);
  return ESP_OK;
}

/* ------------------------------------------------------------------- dns */

/*
 * En DNS-lögnare som svarar 192.168.4.1 på ALLT. Bara medan fönstret är
 * öppet, bara på accesspunktens eget nät — den lämnar aldrig glasets
 * räckvidd, och utan den blir portalen en IP-adress man måste skriva av
 * från skärmen.
 */
static void dns_task(void *arg) {
  (void)arg;
  int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  if (sock < 0) {
    ESP_LOGW(TAG, "ingen DNS-socket — portalen nås via " AP_ADDRESS);
    vTaskDelete(NULL);
    return;
  }
  struct sockaddr_in addr = {
    .sin_family = AF_INET,
    .sin_port = htons(53),
    .sin_addr.s_addr = htonl(INADDR_ANY),
  };
  struct timeval tv = { .tv_sec = 1, .tv_usec = 0 };
  setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);

  if (bind(sock, (struct sockaddr *)&addr, sizeof addr) < 0) {
    ESP_LOGW(TAG, "DNS-porten kunde inte tas — portalen nås via " AP_ADDRESS);
    close(sock);
    vTaskDelete(NULL);
    return;
  }

  uint8_t pkt[256];
  while (!atomic_load(&s_dns_stop)) {
    struct sockaddr_in from;
    socklen_t fromlen = sizeof from;
    int n = recvfrom(sock, pkt, sizeof pkt, 0, (struct sockaddr *)&from,
                     &fromlen);
    if (n < 12) continue; /* timeout eller för kort för ett DNS-huvud */

    /* Bara vanliga frågor med exakt en fråga besvaras. Allt annat
     * ignoreras hellre än gissas på. */
    if ((pkt[2] & 0x80) != 0) continue;          /* redan ett svar */
    if (pkt[4] != 0 || pkt[5] != 1) continue;    /* QDCOUNT != 1   */

    /* Hoppa QNAME: längdprefixade etiketter fram till nollbyten. */
    int p = 12;
    while (p < n && pkt[p] != 0) {
      if ((pkt[p] & 0xC0) != 0) { p = n; break; } /* pekare i en fråga */
      p += pkt[p] + 1;
    }
    if (p >= n - 4) continue;
    int qend = p + 1 + 4; /* nollbyte + QTYPE + QCLASS */
    if (qend > n || qend + 16 > (int)sizeof pkt) continue;

    pkt[2] = 0x84; /* QR=1, AA=1 */
    pkt[3] = 0x00; /* ingen rekursion, ingen felkod */
    pkt[6] = 0x00; pkt[7] = 0x01; /* ANCOUNT = 1 */
    pkt[8] = 0x00; pkt[9] = 0x00; /* NSCOUNT = 0 */
    pkt[10] = 0x00; pkt[11] = 0x00; /* ARCOUNT = 0 */

    uint8_t *a = pkt + qend;
    a[0] = 0xC0; a[1] = 0x0C;             /* pekare till frågans namn */
    a[2] = 0x00; a[3] = 0x01;             /* TYPE A                   */
    a[4] = 0x00; a[5] = 0x01;             /* CLASS IN                 */
    a[6] = 0; a[7] = 0; a[8] = 0; a[9] = 60; /* TTL 60 s              */
    a[10] = 0x00; a[11] = 0x04;           /* RDLENGTH 4               */
    a[12] = 192; a[13] = 168; a[14] = 4; a[15] = 1;

    sendto(sock, pkt, qend + 16, 0, (struct sockaddr *)&from, fromlen);
  }
  close(sock);
  vTaskDelete(NULL);
}

/* --------------------------------------------------------------- fönstret */

static void server_start(void) {
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port = 80;
  cfg.lru_purge_enable = true;
  cfg.max_uri_handlers = 4;
  cfg.uri_match_fn = httpd_uri_match_wildcard;
  cfg.stack_size = 4096;

  if (httpd_start(&s_server, &cfg) != ESP_OK) {
    ESP_LOGE(TAG, "http-servern startade inte — glaset visar ändå nätet");
    s_server = NULL;
    return;
  }
  static const httpd_uri_t root = {
    .uri = "/", .method = HTTP_GET, .handler = page_get };
  static const httpd_uri_t join = {
    .uri = "/join", .method = HTTP_POST, .handler = join_post };
  static const httpd_uri_t rest = {
    .uri = "/*", .method = HTTP_GET, .handler = catch_all_get };
  httpd_register_uri_handler(s_server, &root);
  httpd_register_uri_handler(s_server, &join);
  httpd_register_uri_handler(s_server, &rest);
}

/* DMA-läget i loggen vid varje steg av öppningen: accesspunkten är den
 * enda ytan i firmwaren vars minneskostnad aldrig mätts på hårdvara, och
 * kilningen 2026-08-17 (första fysiska körningen) obducerades i blindo.
 * Nästa incident ska peka ut exakt vilket steg som åt blocket. */
static size_t dma_log(const char *stage) {
  size_t largest = heap_caps_get_largest_free_block(MALLOC_CAP_DMA);
  ESP_LOGI(TAG, "DMA största block %s: %u byte", stage, (unsigned)largest);
  return largest;
}

static void window_open(void) {
  /* GRIND 1, före allt: ryms accesspunkten utan att närma sig flushens
   * DMA-tak? Ett vägrat fönster är en loggrad och ett nytt försök om en
   * stund; en fryst panel är en USB-räddning. */
  size_t largest = dma_log("före öppning");
  if (!tg_wifi_setup_dma_ok_to_open(largest, s_hooks->flush_dma_bytes)) {
    ESP_LOGW(TAG, "setupfönstret VÄGRAR öppna: DMA-blocket %u byte < "
             "%d x flushens %u — hellre stängt än fryst glas",
             (unsigned)largest, TG_WIFI_SETUP_DMA_OPEN_FACTOR,
             (unsigned)s_hooks->flush_dma_bytes);
    return;
  }

  /* Port 80 kan bara ha en ägare. Ett OTA-fönster utan nät kan ändå inte
   * ta emot en uppladdning, så nätlagret vinner den konflikten — och
   * säger det i loggen i stället för att tyst misslyckas. */
  if (torget_ota_service_maintenance_open()) {
    ESP_LOGI(TAG, "stänger OTA-fönstret: porten och minnet behövs här");
    torget_ota_service_close_maintenance();
    vTaskDelay(pdMS_TO_TICKS(1200)); /* låt OTA-vakten lämna tillbaka porten */
    dma_log("efter OTA-stopp");
  }

  if (s_hooks->sta_pause) s_hooks->sta_pause(true);
  esp_wifi_disconnect();
  vTaskDelay(pdMS_TO_TICKS(200));

  scan_networks();
  derive_ap_password();
  dma_log("efter skanning");

  if (!s_ap_netif) s_ap_netif = esp_netif_create_default_wifi_ap();

  wifi_config_t ap = {0};
  snprintf((char *)ap.ap.ssid, sizeof ap.ap.ssid, "%s", AP_SSID);
  ap.ap.ssid_len = (uint8_t)strlen(AP_SSID);
  snprintf((char *)ap.ap.password, sizeof ap.ap.password, "%s", s_ap_pass);
  ap.ap.channel = AP_CHANNEL;
  ap.ap.max_connection = AP_MAX_CONN;
  ap.ap.authmode = WIFI_AUTH_WPA2_PSK;

  esp_err_t err = esp_wifi_set_mode(WIFI_MODE_APSTA);
  if (err == ESP_OK) err = esp_wifi_set_config(WIFI_IF_AP, &ap);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "accesspunkten kom inte upp: %s", esp_err_to_name(err));
    esp_wifi_set_mode(WIFI_MODE_STA);
    if (s_hooks->sta_pause) s_hooks->sta_pause(false);
    return;
  }

  /* GRIND 2, efter APSTA-bytet — den dyra biten. Föll blocket under x2 av
   * flushen är NÄSTA flush i farozonen: riv hellre fönstret medan glaset
   * fortfarande lever än fortsätt stapla httpd + DNS ovanpå. */
  largest = dma_log("efter APSTA");
  if (!tg_wifi_setup_dma_ok_to_continue(largest, s_hooks->flush_dma_bytes)) {
    ESP_LOGE(TAG, "setupfönstret AVBRYTER: DMA-blocket %u byte < "
             "%d x flushens %u efter AP-start — river innan glaset fryser",
             (unsigned)largest, TG_WIFI_SETUP_DMA_ABORT_FACTOR,
             (unsigned)s_hooks->flush_dma_bytes);
    esp_wifi_set_mode(WIFI_MODE_STA);
    if (s_hooks->sta_pause) s_hooks->sta_pause(false);
    return;
  }

  atomic_store(&s_dns_stop, false);
  if (xTaskCreate(dns_task, "tg-wifi-dns", 3072, NULL, 4, NULL) != pdPASS)
    ESP_LOGW(TAG, "DNS-lögnaren startade inte — portalen nås via " AP_ADDRESS);
  server_start();
  dma_log("fönstret uppe");

  atomic_store(&s_open, true);
  /* Lösenordet står på glaset, inte i loggen: den som läser serieloggen
   * har redan kabeln, men loggen kan hamna i en bugrapport. */
  ESP_LOGI(TAG, "setupfönstret öppet i tio minuter (%s)", AP_SSID);
}

static void window_close(void) {
  if (s_server) {
    httpd_stop(s_server);
    s_server = NULL;
  }
  atomic_store(&s_dns_stop, true);
  /* DNS-tasken vaknar ur sin sekundtimeout, ser flaggan och tar bort sig
   * själv; sockeln stängs där, inte här. */
  vTaskDelay(pdMS_TO_TICKS(1200));

  esp_wifi_set_mode(WIFI_MODE_STA);
  atomic_store(&s_open, false);
  atomic_store(&s_joined_at_us, 0);
  s_joined_ssid[0] = '\0';
  if (s_hooks->sta_pause) s_hooks->sta_pause(false);
  ESP_LOGI(TAG, "setupfönstret stängt");
}

/* ----------------------------------------------------------------- vakten */

static void guard_task(void *arg) {
  (void)arg;
  int64_t no_ip_since = esp_timer_get_time();
  int64_t opened_us = 0;
  int64_t last_close_us = 0;
  int64_t got_ip_us = 0;
  bool applied = false;

  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(500));

    const int64_t now = esp_timer_get_time();
    const bool have_ip = s_hooks->have_ip && s_hooks->have_ip();
    const bool open = atomic_load(&s_open);

    if (have_ip) {
      /* Flanken false->true är den enda gången listan behöver skrivas om;
       * att göra det varje halvsekund vore rent flashslitage. */
      if (no_ip_since != 0 && s_hooks->ip_acquired) s_hooks->ip_acquired();
      no_ip_since = 0;
      if (open && got_ip_us == 0) got_ip_us = now;
    } else if (no_ip_since == 0) {
      no_ip_since = now;
      got_ip_us = 0;
    }

    if (!open) {
      bool asked = atomic_exchange(&s_want_open, false);
      atomic_store(&s_want_close, false);
      if (asked ||
          tg_wifi_setup_should_open(have_ip, now, no_ip_since, last_close_us)) {
        opened_us = now;
        got_ip_us = 0;
        applied = false;
        window_open();
        if (!atomic_load(&s_open)) { /* öppningen föll — försök inte i loop */
          opened_us = 0;
          last_close_us = now;
        }
      }
    } else {
      /* Uppgifter mottagna: bygg om kandidatlistan EN gång och släpp
       * STA:n fri mot det nya nätet. */
      if (!applied && atomic_load(&s_joined_at_us) != 0) {
        applied = true;
        if (s_hooks->sta_pause) s_hooks->sta_pause(false);
        if (s_hooks->creds_changed) s_hooks->creds_changed(s_joined_ssid);
      }
      if (atomic_exchange(&s_want_close, false) ||
          tg_wifi_setup_should_close(now, opened_us, got_ip_us)) {
        window_close();
        last_close_us = now;
        opened_us = 0;
      }
    }

    /* Glaset: nätlagret syns bara när det finns något att säga. En panel
     * med IP har inget ärende här — då äger apparna skärmen.
     *
     * OTA-overlayn har alltid företräde: efter en OTA-omstart utan nät är
     * BÅDE underhållsfönstret (återväpnat av PENDING_VERIFY-booten) och
     * nätsökningen aktiva, och båda lagren flyttar sig främst vid varje
     * uppdatering — utan den här spärren flimrar de om förgrunden en gång
     * i sekunden. Ringen vinner; nätsidan väntar tills fönstret stängt.
     * Setupfönstret är undantaget: window_open() stängde OTA-fönstret för
     * port 80, så konflikten kan inte uppstå där. */
    const bool now_open = atomic_load(&s_open);
    if (!now_open && torget_ota_service_maintenance_open()) {
      torget_wifi_ui_set(TG_WIFI_UI_HIDDEN, NULL, NULL, NULL, 0);
    } else if (have_ip && !now_open) {
      torget_wifi_ui_set(TG_WIFI_UI_HIDDEN, NULL, NULL, NULL, 0);
    } else if (now_open && atomic_load(&s_joined_at_us) != 0) {
      torget_wifi_ui_set(have_ip ? TG_WIFI_UI_JOINED : TG_WIFI_UI_JOINING,
                         s_joined_ssid, NULL, NULL, 0);
    } else if (now_open) {
      int left = (int)((TG_WIFI_SETUP_WINDOW_US - (now - opened_us)) / 1000000);
      torget_wifi_ui_set(TG_WIFI_UI_OPEN, AP_SSID, s_ap_pass, NULL, left);
    } else if (tg_wifi_search_ui_visible(have_ip, now, no_ip_since)) {
      /* Den ärliga nätsidan: vilket nät jagas, vad radion svarade, och hur
       * länge det är kvar tills fönstret öppnar sig självt. Först efter
       * TG_WIFI_SEARCH_UI_US — bootskärmen äger uppstarten. */
      const char *ssid = s_hooks->current_ssid ? s_hooks->current_ssid() : NULL;
      const char *reason = s_hooks->last_reason ? s_hooks->last_reason() : NULL;
      int64_t until = TG_WIFI_SETUP_AUTO_US - (now - no_ip_since);
      int left = until > 0 ? (int)(until / 1000000) : 0;
      torget_wifi_ui_set(TG_WIFI_UI_SEARCHING, ssid, NULL, reason, left);
    } else {
      /* Kort svacka eller pågående boot: apparna behåller glaset. */
      torget_wifi_ui_set(TG_WIFI_UI_HIDDEN, NULL, NULL, NULL, 0);
    }
  }
}

void torget_wifi_setup_start(const tg_wifi_setup_hooks *hooks) {
  if (!hooks) return;
  s_hooks = hooks;
  ESP_LOGI(TAG, "%d ihågkomna nät i NVS", tg_wifi_creds_count());
  /* 5 kB, inte 4: vakten är den som får röra NVS åt värdlagret, och en
   * hel slotlista är 600 byte på stacken innan NVS ens börjat. */
  if (xTaskCreate(guard_task, "tg-wifi-setup", 5120, NULL, 4, NULL) != pdPASS)
    ESP_LOGE(TAG, "setupvakten kunde inte skapas — nya nät kräver USB");
}

void torget_wifi_setup_request_open(void) { atomic_store(&s_want_open, true); }
void torget_wifi_setup_request_close(void) { atomic_store(&s_want_close, true); }
bool torget_wifi_setup_is_open(void) { return atomic_load(&s_open); }
