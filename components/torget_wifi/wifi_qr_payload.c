#include "wifi_qr_payload.h"

#include <string.h>

#include "wifi_slots.h"

static bool append_char(char *out, size_t cap, size_t *used, char value) {
  if (*used + 1 >= cap) return false;
  out[(*used)++] = value;
  out[*used] = '\0';
  return true;
}

static bool append_literal(char *out, size_t cap, size_t *used,
                           const char *value) {
  for (const char *p = value; *p; p++) {
    if (!append_char(out, cap, used, *p)) return false;
  }
  return true;
}

static bool append_escaped(char *out, size_t cap, size_t *used,
                           const char *value) {
  for (const char *p = value; *p; p++) {
    if (strchr("\\;,:\"", *p) != NULL &&
        !append_char(out, cap, used, '\\')) {
      return false;
    }
    if (!append_char(out, cap, used, *p)) return false;
  }
  return true;
}

bool tg_wifi_qr_payload(char *out, size_t cap,
                        const char *ssid, const char *password) {
  if (out != NULL && cap > 0) out[0] = '\0';
  if (out == NULL || cap == 0 || !tg_wifi_ssid_valid(ssid) ||
      !tg_wifi_pass_valid(password) || password[0] == '\0') {
    return false;
  }

  size_t used = 0;
  if (!append_literal(out, cap, &used, "WIFI:T:WPA;S:") ||
      !append_escaped(out, cap, &used, ssid) ||
      !append_literal(out, cap, &used, ";P:") ||
      !append_escaped(out, cap, &used, password) ||
      !append_literal(out, cap, &used, ";H:false;;")) {
    out[0] = '\0';
    return false;
  }
  return true;
}
