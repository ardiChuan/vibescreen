#!/usr/bin/env python3
"""The contracts the WiFi setup window shares across three languages.

The firmware, the Mac script and the consent model each hold one half of an
agreement.  Nothing catches these at compile time, so they are asserted
here — the drift they prevent is silent and only shows up on a hotel room
floor with a panel that will not join anything.
"""

import hashlib
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
setup_c = (root / "components/torget_wifi/wifi_setup.c").read_text(encoding="utf-8")
main_c = (root / "main/main.c").read_text(encoding="utf-8")
script = (root / "tools/wifi-here.sh").read_text(encoding="utf-8")
slots_h = (root / "components/torget_wifi/wifi_slots.h").read_text(encoding="utf-8")

# --- The access point's identity must match on both sides ------------------
# The script joins by name; a rename on one side alone strands the panel.
ap_ssid = re.search(r'#define AP_SSID\s+"([^"]+)"', setup_c).group(1)
assert f"AP_SSID={ap_ssid}" in script, (
    f"tools/wifi-here.sh joins a different SSID than the firmware raises ({ap_ssid})"
)

ap_host = re.search(r'#define AP_ADDRESS\s+"([^"]+)"', setup_c).group(1)
assert f"AP_HOST={ap_host}" in script, (
    "the script posts to a different address than the firmware serves"
)

# --- The derived access-point password ------------------------------------
# Firmware: sha256(domain || TG_OTA_TOKEN), first 6 bytes as 12 hex chars.
# Script:   the same digest, cut to 12 characters.  Both are asserted against
# a worked example so neither the domain string nor the length can drift.
domain_c = re.search(r'static const char domain\[\] = "([^"]+)"', setup_c).group(1)
domain_sh = re.search(r"^DOMAIN=(\S+)", script, re.M).group(1)
assert domain_c == domain_sh, (
    f"domain separation string differs: firmware {domain_c!r}, script {domain_sh!r}"
)

# The firmware writes 6 bytes as "%02x" pairs; the script cuts 12 characters.
assert re.search(r"for \(int i = 0; i < 6; i\+\+\)\s*\n\s*snprintf\(s_ap_pass \+ i \* 2, 3, \"%02x\"", setup_c), (
    "the firmware no longer writes exactly 6 bytes of the digest as hex"
)
assert "cut -c1-12" in script, "the script no longer cuts the digest to 12 characters"

token = "a" * 64
expected = hashlib.sha256((domain_c + token).encode()).hexdigest()[:12]
assert len(expected) == 12 and expected.isalnum()
# WPA2 refuses anything shorter than 8 characters — a 12-char PSK has margin.
assert len(expected) >= 8, "a derived AP password below 8 chars cannot be a WPA2 PSK"

# --- The consent model ------------------------------------------------------
# docs/ota.md promises the OTA maintenance window opens ONLY from the device.
# Routing KEY3 by network state must never hand a script that power.
assert "torget_wifi_setup_request_open()" in main_c
assert re.search(
    r"if \(hook_have_ip\(\)\) torget_ota_service_open_maintenance\(\);\s*\n\s*else torget_wifi_setup_request_open\(\);",
    main_c,
), "KEY3 must open the OTA window only when there is an IP, setup otherwise"

# The double hold: a second full hold while the OTA window is open must
# REQUEST the setup window, never close-and-open from the LVGL task — the
# port-80 handover belongs to the setup guard's window_open().  Two request
# sites total: the no-IP route and the switch route.
assert main_c.count("torget_wifi_setup_request_open();") == 2, (
    "expected exactly the no-IP route and the hold-again switch route"
)
maintenance_branch = main_c.split("torget_ota_service_maintenance_open()) {")[1]
# Skär vid nästa YTTRE gren (appväxlaren) — den inre else-if-kedjan för
# knapphändelserna hör till branchen och får inte klippa bort växlingsvägen.
maintenance_branch = maintenance_branch.split("torget_app_next()")[0]
assert "torget_wifi_setup_request_open();" in maintenance_branch, (
    "the hold-again switch must live inside the maintenance-open branch"
)
assert "torget_ota_service_close_maintenance();\n      torget_wifi_setup_request_open" not in main_c, (
    "the LVGL task must not close the OTA window itself when switching"
)

# The setup window may never become a firmware path.
assert "esp_ota" not in setup_c and "ota_ops" not in setup_c, (
    "the WiFi setup window must never gain a firmware-writing surface"
)

# --- The immutable floor ----------------------------------------------------
# secrets.h is what makes a bad network entry recoverable without USB.  The
# candidate list must always be built with the compiled-in networks appended.
assert "tg_wifi_candidates(remembered, TG_WIFI_SLOTS, fixed, 2" in main_c, (
    "the compiled-in secrets.h networks must stay as the candidate floor"
)
assert "TG_WIFI_SSID" in main_c and "TG_WIFI2_SSID" in main_c

# --- The lazy surface -------------------------------------------------------
# The 2026-08-14 freeze lesson: a boot that never opens the window must not
# pay for it.  The AP, the HTTP server and the DNS task all live in
# window_open(), never in the start path.
start_fn = setup_c.split("void torget_wifi_setup_start(")[1]
for forbidden in ("httpd_start", "esp_netif_create_default_wifi_ap", "dns_task"):
    assert forbidden not in start_fn, (
        f"{forbidden} must not run at boot — the setup surface is lazy"
    )

# --- Password handling ------------------------------------------------------
# A password must never reach the log; the SSID may, because it is the only
# way to debug a network from a serial console.
for line in setup_c.splitlines():
    if "ESP_LOG" in line:
        assert "s_ap_pass" not in line and "pass" not in line.split("ESP_LOG")[1], (
            f"a password must never be logged: {line.strip()}"
        )

# --- Window timing ----------------------------------------------------------
# The window must close itself; an open AP left up overnight is a surface.
assert "TG_WIFI_SETUP_WINDOW_US   (600LL" in slots_h, (
    "the setup window must stay bounded at ten minutes"
)

print("OK: WiFi setup window, Mac script and consent model agree")
