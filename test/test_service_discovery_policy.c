#include <stdio.h>
#include <string.h>

#include "../components/torget_net/service_discovery_policy.h"

static int failures;

static void check(const char *name, int condition) {
  if (!condition) {
    printf("FAIL %s\n", name);
    ++failures;
  }
}

int main(void) {
  check("valid private IPv4 origin",
        tg_service_origin_valid("http://192.168.1.8:8737"));
  check("valid edge octets",
        tg_service_origin_valid("http://0.255.1.2:65535"));
  check("rejects path",
        !tg_service_origin_valid("http://192.168.1.8:8737/api/tokens"));
  check("rejects userinfo",
        !tg_service_origin_valid("http://user@192.168.1.8:8737"));
  check("rejects bad octet",
        !tg_service_origin_valid("http://256.1.1.1:8737"));
  check("rejects zero port",
        !tg_service_origin_valid("http://192.168.1.8:0"));
  check("rejects overflow port",
        !tg_service_origin_valid("http://192.168.1.8:65536"));
  check("rejects https",
        !tg_service_origin_valid("https://192.168.1.8:8737"));

  char url[64];
  check("builds bounded endpoint",
        tg_service_build_endpoint("http://192.168.1.8:8737", "/api/tokens",
                                  url, sizeof url) &&
        strcmp(url, "http://192.168.1.8:8737/api/tokens") == 0);
  check("rejects relative path",
        !tg_service_build_endpoint("http://192.168.1.8:8737", "api/tokens",
                                   url, sizeof url));
  check("rejects truncation",
        !tg_service_build_endpoint("http://192.168.1.8:8737", "/api/tokens",
                                   url, 8));

  if (failures == 0) {
    puts("OK: discovered origins and endpoint URLs are strict and bounded");
    return 0;
  }
  return 1;
}
