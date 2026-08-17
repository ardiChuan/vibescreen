#include "wifi_form.h"

#include <string.h>

#include "wifi_slots.h"

static int hex_nibble(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

bool tg_wifi_url_decode(char *s) {
  if (!s) return false;
  char *out = s;
  for (char *p = s; *p; p++) {
    if (*p == '+') {
      *out++ = ' ';
    } else if (*p == '%') {
      if (!p[1] || !p[2]) return false;
      int hi = hex_nibble(p[1]);
      int lo = hex_nibble(p[2]);
      if (hi < 0 || lo < 0) return false;
      /* %00 skulle klippa strängen mitt itu och göra resten osynlig för
       * varje längdkontroll efteråt — samma trunkeringsfälla som NUL:en i
       * agentnamnen 2026-08-13. Avvisa i stället för att smyga igenom. */
      if (hi == 0 && lo == 0) return false;
      *out++ = (char)((hi << 4) | lo);
      p += 2;
    } else {
      *out++ = *p;
    }
  }
  *out = '\0';
  return true;
}

bool tg_wifi_form_field(const char *body, const char *name, char *out,
                        size_t cap) {
  if (!body || !name || !out || cap == 0) return false;
  size_t namelen = strlen(name);

  for (const char *p = body; *p;) {
    const char *eq = strchr(p, '=');
    const char *amp = strchr(p, '&');
    if (!eq || (amp && eq > amp)) {
      /* Ett par utan '=' är inget fält; hoppa till nästa om det finns. */
      if (!amp) break;
      p = amp + 1;
      continue;
    }
    size_t keylen = (size_t)(eq - p);
    const char *val = eq + 1;
    size_t vallen = amp ? (size_t)(amp - val) : strlen(val);

    if (keylen == namelen && strncmp(p, name, namelen) == 0) {
      char raw[TG_WIFI_PASS_CAP * 3];
      if (vallen >= sizeof raw) return false;
      memcpy(raw, val, vallen);
      raw[vallen] = '\0';
      if (!tg_wifi_url_decode(raw)) return false;
      size_t decoded = strlen(raw);
      if (decoded >= cap) return false;
      memcpy(out, raw, decoded + 1);
      return true;
    }
    if (!amp) break;
    p = amp + 1;
  }
  return false;
}

void tg_wifi_html_escape(const char *in, char *out, size_t cap) {
  if (!out || cap == 0) return;
  size_t o = 0;
  if (!in) { out[0] = '\0'; return; }

  for (const char *p = in; *p; p++) {
    const char *rep = NULL;
    size_t replen = 0;
    switch (*p) {
      case '&': rep = "&amp;";  replen = 5; break;
      case '<': rep = "&lt;";   replen = 4; break;
      case '>': rep = "&gt;";   replen = 4; break;
      case '"': rep = "&quot;"; replen = 6; break;
      default: break;
    }
    if (rep) {
      if (o + replen >= cap) break;
      memcpy(out + o, rep, replen);
      o += replen;
    } else {
      if (o + 1 >= cap) break;
      out[o++] = *p;
    }
  }
  out[o] = '\0';
}
