#!/usr/bin/env python3
"""Regression guard for LVGL's small private heap on the ESP32 target."""

from pathlib import Path


root = Path(__file__).resolve().parents[1]
usage_screen = (root / "components/app_tokens/usage_screen.c").read_text(
    encoding="utf-8"
)
agent_monitor = (root / "components/app_tokens/agent_monitor.c").read_text(
    encoding="utf-8"
)
target_main = (root / "main/main.c").read_text(encoding="utf-8")
sim_main = (root / "sim/main.c").read_text(encoding="utf-8")
platform_header = (root / "platform/torget.h").read_text(encoding="utf-8")

# Scaling a dynamic label makes LVGL render the complete label into an
# unsliceable ARGB transform layer.  The 436 px hero labels can then request
# more contiguous memory than Torget's 96 KiB LVGL pool has available and the
# draw dispatcher spins until the task watchdog fires.
assert "lv_obj_set_style_transform_scale_" not in usage_screen, (
    "VibePulse labels must use a native-size font, never an LVGL transform layer"
)
assert "SUMMARY_LABEL_SCALE_Y" not in usage_screen
assert "extern const lv_font_t plex_ui_21;" in usage_screen
assert "extern const lv_font_t plex_num_164;" in usage_screen
assert "lv_obj_set_style_transform" not in usage_screen
assert "lv_obj_set_style_opa" not in usage_screen
assert "lv_canvas" not in usage_screen

# Needs You remains one provider-neutral LVGL tree.  Codex must only swap
# native assets/colors/copy into that tree; a second screen would double the
# persistent object and draw-memory cost that the 256 KiB pool is sized for.
assert agent_monitor.count("} needs_you_view;") == 1
assert "codex_needs_you_view" not in agent_monitor.lower()
assert "tk_img_codex_64" in agent_monitor
assert '"CODEX RECOMMENDS"' in agent_monitor
assert '"APPROVE"' in agent_monitor
assert '"ALLOW ONCE"' in agent_monitor
assert "COL_CODEX" in agent_monitor

# The approved header leaves a hard lane for the radio indicator: the
# provider/project eyebrow is ellipsized at x=148,w=260 and the Wi-Fi group is
# the single 28px object rooted at (418,38).  The icon reports Wi-Fi only,
# never relay health.
assert "148, 46, 260" in agent_monitor
assert "lv_label_set_long_mode(v->h_eyebrow, LV_LABEL_LONG_DOT)" in agent_monitor
assert "lv_obj_set_pos(v->wifi_group, 418, 38)" in agent_monitor
assert "lv_obj_set_size(v->wifi_group, 28, 28)" in agent_monitor
assert agent_monitor.count("lv_arc_create(v->wifi_group)") == 1
assert agent_monitor.count("ny_wifi_arc(v,") == 3
assert "uint8_t torget_wifi_signal_bars(void);" in platform_header
assert "Never implies relay health" in platform_header

# Target sampling is lock-free and stays out of LVGL; the simulator supplies a
# deterministic fixture through the same platform API.
assert "atomic_uchar" in target_main
assert "esp_wifi_sta_get_ap_info" in target_main
assert "pdMS_TO_TICKS(5000)" in target_main
assert "torget_wifi_signal_bars" in sim_main
assert "sim_wifi_signal_bars" in sim_main

print("OK: VibePulse labels and shared Needs You tree stay allocation-safe")
