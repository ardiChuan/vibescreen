#include <stdio.h>
#include <string.h>

#include "../components/torget_wifi/wifi_form.h"
#include "../components/torget_wifi/wifi_slots.h"

static int failures;

static void check(const char *what, int condition) {
  if (!condition) {
    printf("FAIL %s\n", what);
    failures++;
  }
}

static void test_url_decode(void) {
  char plus[] = "Hotell+Gast";
  check("plus decodes to space",
        tg_wifi_url_decode(plus) && strcmp(plus, "Hotell Gast") == 0);

  char pct[] = "caf%C3%A9%20wifi";
  check("percent pairs decode",
        tg_wifi_url_decode(pct) && strcmp(pct, "caf\xC3\xA9 wifi") == 0);

  char upper[] = "a%2Fb";
  check("uppercase hex decodes",
        tg_wifi_url_decode(upper) && strcmp(upper, "a/b") == 0);

  /* Trasig indata ger nej, inte en gissning. */
  char truncated[] = "abc%4";
  check("a truncated escape is rejected", !tg_wifi_url_decode(truncated));
  char dangling[] = "abc%";
  check("a dangling percent is rejected", !tg_wifi_url_decode(dangling));
  char nonhex[] = "abc%zz";
  check("a non-hex escape is rejected", !tg_wifi_url_decode(nonhex));

  /* %00 skulle klippa strängen mitt itu och göra resten osynlig för varje
   * längdkontroll efteråt — samma trunkeringsfälla som 2026-08-13. */
  char embedded_nul[] = "hem%00extra";
  check("an embedded NUL is rejected, not silently truncated",
        !tg_wifi_url_decode(embedded_nul));
}

static void test_form_field(void) {
  char out[TG_WIFI_PASS_CAP];

  check("first field is found",
        tg_wifi_form_field("ssid=hem&pass=hemligt1", "ssid", out, sizeof out) &&
            strcmp(out, "hem") == 0);
  check("last field is found",
        tg_wifi_form_field("ssid=hem&pass=hemligt1", "pass", out, sizeof out) &&
            strcmp(out, "hemligt1") == 0);
  check("a missing field says so",
        !tg_wifi_form_field("ssid=hem", "pass", out, sizeof out));

  /* Prefixet får inte räcka: "ssid" ska inte matcha "ssid2". */
  check("a key prefix does not match a longer key",
        !tg_wifi_form_field("ssid2=x", "ssid", out, sizeof out));

  /* Ett tomt värde är ett giltigt svar — det är ett öppet nät. */
  check("an empty value is a valid answer",
        tg_wifi_form_field("ssid=hem&pass=", "pass", out, sizeof out) &&
            out[0] == '\0');

  check("an encoded value decodes",
        tg_wifi_form_field("ssid=Hotell+G%C3%A5rd&pass=x", "ssid", out,
                           sizeof out) &&
            strcmp(out, "Hotell G\xC3\xA5rd") == 0);

  /* Längden mäts EFTER avkodningen: ett 32-tecken SSID fullt av mellanslag
   * blir 96 tecken kodat och skulle annars nekas fast det får plats. */
  char ssid_out[TG_WIFI_SSID_CAP];
  char body[256] = "ssid=";
  for (int i = 0; i < 32; i++) strcat(body, "%20");
  check("a full-length ssid survives its own encoding",
        tg_wifi_form_field(body, "ssid", ssid_out, sizeof ssid_out) &&
            strlen(ssid_out) == 32);

  /* Ett tecken för långt ska nekas, inte tyst klippas. */
  char one_too_long[256] = "ssid=";
  for (int i = 0; i < 33; i++) strcat(one_too_long, "a");
  check("one byte past the cap is rejected, not truncated",
        !tg_wifi_form_field(one_too_long, "ssid", ssid_out, sizeof ssid_out));

  /* Skräp mitt i kroppen får inte dölja fältet som kommer efter. */
  check("a malformed pair does not hide later fields",
        tg_wifi_form_field("junk&ssid=hem", "ssid", out, sizeof out) &&
            strcmp(out, "hem") == 0);
}

static void test_html_escape(void) {
  char out[128];

  tg_wifi_html_escape("hem", out, sizeof out);
  check("plain text passes through", strcmp(out, "hem") == 0);

  /* Ett SSID i luften är någon annans sträng och hamnar i portalens HTML. */
  tg_wifi_html_escape("</option><script>x</script>", out, sizeof out);
  check("markup cannot break out of the option list",
        strstr(out, "<script>") == NULL && strstr(out, "&lt;") != NULL);

  tg_wifi_html_escape("a&b\"c", out, sizeof out);
  check("ampersand and quote are escaped", strcmp(out, "a&amp;b&quot;c") == 0);

  /* Trunkering hellre än spill, och alltid NUL-terminerat. */
  char tiny[6];
  tg_wifi_html_escape("aaaaaaaaaa", tiny, sizeof tiny);
  check("truncation stays inside the buffer", strlen(tiny) < sizeof tiny);
  char no_room[4];
  tg_wifi_html_escape("&&&&", no_room, sizeof no_room);
  check("an entity that does not fit is dropped whole",
        no_room[0] == '\0');
}

int main(void) {
  test_url_decode();
  test_form_field();
  test_html_escape();

  if (failures == 0) {
    printf("OK: all WiFi setup-form parsing tests pass\n");
    return 0;
  }
  printf("%d tests failed\n", failures);
  return 1;
}
