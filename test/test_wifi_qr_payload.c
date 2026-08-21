#include <stdio.h>
#include <string.h>

#include "../components/torget_wifi/wifi_qr_payload.h"

static int failures;

static void check(const char *what, int condition) {
  if (!condition) {
    printf("FAIL %s\n", what);
    failures++;
  }
}

int main(void) {
  char payload[TG_WIFI_QR_PAYLOAD_CAP];

  check("standard WPA payload",
        tg_wifi_qr_payload(payload, sizeof payload,
                           "VibePulse-setup", "A1B2C3D4E5F6") &&
        strcmp(payload,
               "WIFI:T:WPA;S:VibePulse-setup;P:A1B2C3D4E5F6;H:false;;") == 0);

  check("reserved characters escaped",
        tg_wifi_qr_payload(payload, sizeof payload,
                           "Cafe;West,\"", "ab\\cd:12") &&
        strcmp(payload,
               "WIFI:T:WPA;S:Cafe\\;West\\,\\\";P:ab\\\\cd\\:12;H:false;;") == 0);

  strcpy(payload, "sentinel");
  check("small output fails closed",
        !tg_wifi_qr_payload(payload, 16,
                            "VibePulse-setup", "A1B2C3D4E5F6"));
  check("failed output is cleared", payload[0] == '\0');

  check("empty SSID rejected",
        !tg_wifi_qr_payload(payload, sizeof payload, "", "A1B2C3D4E5F6"));
  check("empty WPA password rejected",
        !tg_wifi_qr_payload(payload, sizeof payload,
                            "VibePulse-setup", ""));
  check("short WPA password rejected",
        !tg_wifi_qr_payload(payload, sizeof payload,
                            "VibePulse-setup", "1234567"));
  check("control characters rejected",
        !tg_wifi_qr_payload(payload, sizeof payload,
                            "VibePulse-setup", "1234\t678"));
  check("NULL inputs rejected",
        !tg_wifi_qr_payload(payload, sizeof payload, NULL, "12345678") &&
        !tg_wifi_qr_payload(payload, sizeof payload, "VibePulse-setup", NULL));

  if (failures) return 1;
  puts("wifi qr payload tests: OK");
  return 0;
}
