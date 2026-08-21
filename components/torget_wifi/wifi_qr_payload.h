#ifndef TORGET_WIFI_QR_PAYLOAD_H
#define TORGET_WIFI_QR_PAYLOAD_H

#include <stdbool.h>
#include <stddef.h>

/* Bounded scratch space for the temporary setup AP's Wi-Fi QR payload. */
#define TG_WIFI_QR_PAYLOAD_CAP 192

/* Build the standard ZXing Wi-Fi QR grammar for a WPA/WPA2 network.
 * Reserved characters are escaped with a backslash. On every failure the
 * output is empty when a writable output buffer was supplied. */
bool tg_wifi_qr_payload(char *out, size_t cap,
                        const char *ssid, const char *password);

#endif
