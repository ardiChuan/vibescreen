# VibePulse AMOLED Wi-Fi Icon Repair Design

## Problem

The existing 28 px Wi-Fi mark is built from three rounded LVGL arcs. Their
three-pixel strokes leave only about one pixel of black space between bands.
The simulator preserves that gap, but the physical AMOLED's antialiasing and
bloom merge the bands into a white cloud or umbrella. Because the object lives
on the global top layer, pages that do not visibly reserve the header lane can
also make the mark feel pasted over the page.

## Chosen design

Use the familiar Font Awesome Wi-Fi silhouette already shipped with LVGL,
converted into a dedicated single-glyph 22 px LVGL font. Font Awesome's 5:4
proportion makes that glyph exactly 28 px wide. Render one complete
muted symbol as the base and clip a white copy from the bottom upward for the
0/1/2/3 signal-strength states. Keep the existing disconnected slash for zero
bars. There is no runtime scaling and no dependency on a large general-purpose
symbol font.

The indicator remains one platform-owned object on `lv_layer_top()`. Every app
and overlay treats `(418, 38, 28, 28)` as reserved global header chrome. The
icon is therefore visually part of every page without duplicating network
state or geometry in each app. Boot continues to hide it; normal pages, OTA,
and Wi-Fi setup keep their existing visibility policy.

## Alternatives rejected

- Thinner custom arcs would be the smallest code change, but physical bloom
  could still merge their caps and require another panel-only correction.
- Four bitmap sprites would give exact pixels, but duplicate the same shape,
  complicate color changes, and add unnecessary generated assets.
- One icon per app would look integrated locally but create multiple sources
  of truth, positional drift, and overlay ordering bugs.

## Safety and verification

The regression suite must fail on the old cloud silhouette by checking the
named Wi-Fi mark for stable internal black negative space, not only total pixel
counts. It must also verify the reserved header lane on Claude, Codex, values,
GitHub, companion apps, launcher, OTA, and Wi-Fi setup.

Verification order:

1. Capture the failing raster regression before production edits.
2. Generate the one-glyph font deterministically and pin its exact descriptor.
3. Build the shared simulator and inspect 0/1/2/3 bars at 1:1.
4. Run focused layer, raster, design, and full host test suites.
5. Build the ESP32-S3 image. Do not flash until the user explicitly approves
   the prepared ota_1 image; ota_0 remains untouched.
