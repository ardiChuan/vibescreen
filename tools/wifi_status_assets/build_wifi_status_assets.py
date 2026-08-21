#!/usr/bin/env python3
"""Generate four muted 20x18 I4 Wi-Fi marks for the shared page header."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT_H = ROOT / "platform/wifi_status_assets.h"
OUT_C = ROOT / "platform/wifi_status_assets.c"
WIDTH = 20
HEIGHT = 18

DOT = {(9, 15), (10, 15), (9, 16), (10, 16)}
INNER = {
    (9, 10), (10, 10),
    (7, 11), (8, 11), (9, 11), (10, 11), (11, 11), (12, 11),
    (6, 12), (7, 12), (12, 12), (13, 12),
    (6, 13), (13, 13),
}
MIDDLE = {
    *{(x, 6) for x in range(6, 14)},
    (4, 7), (5, 7), (14, 7), (15, 7),
    (4, 8), (15, 8), (5, 9), (14, 9),
}
OUTER = {
    *{(x, 1) for x in range(7, 13)},
    (5, 2), (6, 2), (13, 2), (14, 2),
    (3, 3), (4, 3), (15, 3), (16, 3),
    (2, 4), (3, 4), (16, 4), (17, 4),
    (1, 5), (2, 5), (17, 5), (18, 5),
}
SLASH = {
    *{(4 + i, 3 + i) for i in range(12)},
    *{(5 + i, 3 + i) for i in range(11)},
}


def _encode_i4(on_pixels: set[tuple[int, int]]) -> bytes:
    palette = bytearray(16 * 4)
    palette[4:8] = bytes((0xA2, 0x98, 0x92, 0xFF))  # BGRA: #9298A2
    indices = [1 if (x, y) in on_pixels else 0
               for y in range(HEIGHT) for x in range(WIDTH)]
    packed = bytearray()
    for offset in range(0, len(indices), 2):
        packed.append((indices[offset] << 4) | indices[offset + 1])
    return bytes(palette + packed)


def build_assets() -> dict[str, bytes]:
    weak = DOT | INNER
    medium = weak | MIDDLE
    strong = medium | OUTER
    return {
        "offline": _encode_i4(strong | SLASH),
        "weak": _encode_i4(weak),
        "medium": _encode_i4(medium),
        "strong": _encode_i4(strong),
    }


def decode_i4(data: bytes) -> tuple[list[tuple[int, int, int, int]], list[int]]:
    palette = []
    for offset in range(0, 64, 4):
        b, g, r, a = data[offset:offset + 4]
        palette.append((r, g, b, a))
    pixels = []
    for value in data[64:]:
        pixels.extend((value >> 4, value & 0x0F))
    return palette, pixels[:WIDTH * HEIGHT]


def _c_array(name: str, data: bytes) -> str:
    rows = []
    for offset in range(0, len(data), 16):
        chunk = data[offset:offset + 16]
        rows.append("  " + ", ".join(f"0x{byte:02x}" for byte in chunk) + ",")
    return f"static const uint8_t {name}[] = {{\n" + "\n".join(rows) + "\n};\n"


def _descriptor(name: str, data_name: str, size: int) -> str:
    return f"""const lv_image_dsc_t {name} = {{
  .header = {{
    .magic = LV_IMAGE_HEADER_MAGIC,
    .cf = LV_COLOR_FORMAT_I4,
    .flags = 0,
    .w = {WIDTH},
    .h = {HEIGHT},
    .stride = {WIDTH // 2},
  }},
  .data_size = {size},
  .data = {data_name},
}};
"""


def render_sources() -> tuple[str, str]:
    assets = build_assets()
    header = """#ifndef TORGET_WIFI_STATUS_ASSETS_H
#define TORGET_WIFI_STATUS_ASSETS_H

#include "lvgl.h"

extern const lv_image_dsc_t tg_img_wifi_offline;
extern const lv_image_dsc_t tg_img_wifi_weak;
extern const lv_image_dsc_t tg_img_wifi_medium;
extern const lv_image_dsc_t tg_img_wifi_strong;

#endif
"""
    source = '#include "wifi_status_assets.h"\n\n'
    for state, data in assets.items():
        source += _c_array(f"tg_img_wifi_{state}_data", data)
    source += "\n"
    for state, data in assets.items():
        source += _descriptor(
            f"tg_img_wifi_{state}", f"tg_img_wifi_{state}_data", len(data)
        )
    return header, source


def main() -> None:
    header, source = render_sources()
    OUT_H.write_text(header, encoding="utf-8")
    OUT_C.write_text(source, encoding="utf-8")


if __name__ == "__main__":
    main()
