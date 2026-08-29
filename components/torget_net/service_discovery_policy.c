#include "service_discovery_policy.h"

#include <stdio.h>

bool tg_service_origin_valid(const char *origin) {
  if (!origin) return false;
  unsigned a, b, c, d, port;
  int consumed = 0;
  if (sscanf(origin, "http://%u.%u.%u.%u:%u%n",
             &a, &b, &c, &d, &port, &consumed) != 5) {
    return false;
  }
  return origin[consumed] == '\0' && a <= 255 && b <= 255 && c <= 255 &&
         d <= 255 && port >= 1 && port <= 65535;
}

bool tg_service_build_endpoint(const char *origin, const char *path,
                               char *url, size_t cap) {
  if (!tg_service_origin_valid(origin) || !path || path[0] != '/' ||
      !url || cap == 0) {
    return false;
  }
  int written = snprintf(url, cap, "%s%s", origin, path);
  return written >= 0 && (size_t)written < cap;
}
