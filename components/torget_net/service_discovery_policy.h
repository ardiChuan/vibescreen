#ifndef TORGET_SERVICE_DISCOVERY_POLICY_H
#define TORGET_SERVICE_DISCOVERY_POLICY_H

#include <stdbool.h>
#include <stddef.h>

/* Discovered/LKG origins are deliberately narrower than general URLs:
 * mDNS supplies one IPv4 address and one TCP port, never a path or userinfo. */
bool tg_service_origin_valid(const char *origin);
bool tg_service_build_endpoint(const char *origin, const char *path,
                               char *url, size_t cap);

#endif
