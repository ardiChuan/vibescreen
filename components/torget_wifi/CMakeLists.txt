# Nätverkslistan och setupfönstret. Samma skiktning som torget_ota: den rena
# policyfilen (wifi_slots) värdtestas i test/run.sh utan ESP-IDF; adaptrarna
# får röra NVS och radion men aldrig bära ett beslut som inte redan är låst
# i policyn.
idf_component_register(
  SRCS "wifi_slots.c" "wifi_form.c" "wifi_qr_payload.c"
       "wifi_creds.c" "wifi_setup.c" "wifi_setup_ui.c"
  INCLUDE_DIRS "."
  # torget_app: designsystemets fonter (extern lv_font_t) + torget.h-låset.
  # torget_ota: setupfönstret måste kunna stänga ett OTA-fönster som håller
  # port 80 — utan nät kan det ändå aldrig ta emot en uppladdning.
  REQUIRES torget_app torget_ota
  # secrets.h (TG_OTA_TOKEN) bor i repytroten, gitignorad — därav "../..".
  PRIV_INCLUDE_DIRS "../.."
  PRIV_REQUIRES nvs_flash esp_wifi esp_netif esp_http_server esp_timer
                esp_hw_support mbedtls lwip)
