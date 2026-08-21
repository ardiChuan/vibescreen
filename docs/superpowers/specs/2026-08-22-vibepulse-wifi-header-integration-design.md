# VibePulse Wi-Fi Header Integration Design

## Outcome

Replace the physically rejected Wi-Fi overlay with a quiet status mark that is
part of Torget's shared header coordinate system. The mark must remain aligned
with the header during pixel drift, read clearly on the real AMOLED, and never
compete with the page title or live-status copy.

This design supersedes the global-top-layer and clipped-font decisions in
`2026-08-21-vibepulse-amoled-wifi-icon-repair-design.md`.

## Physical evidence and root cause

The 2026-08-22 physical photo of `torget-home-01` shows the full-signal glyph
rendering correctly but in the wrong visual relationship to the page:

- the glyph ink occupies `y=42..63`, while the header divider is at `y=63`;
  the symbol therefore lands directly on the divider;
- the provider-context object occupies `y=27..46`, so the Wi-Fi mark is
  visibly lower than the text it belongs with;
- the app roots live under the translating `tg.shift` container, while the
  Wi-Fi object lives on `lv_layer_top()` and does not translate; the relative
  alignment changes during the four-step burn-in drift cycle;
- the 28-pixel, full-white glyph is visually heavier than the 14-pixel status
  copy beside it;
- clipping a white copy over a complete muted glyph does not produce honest,
  discrete weak/medium/strong silhouettes.

The simulator tests encoded `(418, 38, 28, 28)` as the expected answer and
therefore proved consistency with the flawed implementation rather than
physical correctness.

## Approaches considered

### 1. Shared header chrome inside the drift container — chosen

Create one platform-owned header-status host as a child of `tg.shift`, not
`lv_layer_top()`. Every normal surface reserves the same top-right header slot.
The host moves with the page during burn-in drift while the network state stays
centralized. Takeovers can explicitly show or hide the host using the existing
mode API.

This is the smallest architecture that fixes both ownership and drift without
duplicating Wi-Fi state throughout every app.

### 2. One indicator object in every page header

This would make ownership visually literal, but it duplicates LVGL objects and
registration across every VibePulse page, launcher, takeover, and optional
companion. It also creates multiple render targets for one network state and
would require a broader app API migration.

### 3. Move the existing overlay upward

Changing only the coordinates would improve one photograph but retain the
independent top-layer drift, oversized glyph, clipped signal states, and tests
that validate the same implementation. It is rejected as another symptom fix.

## Visual design

The shared slot is `20 x 18` pixels, right-aligned to `x=446` and vertically
centred against the live-context row. Its nominal box is therefore
`(426, 28, 20, 18)`. The nearest page copy ends at `x=408`, leaving 18 black
pixels before the status mark. The divider remains at `y=63`, leaving at least
17 black pixels below the mark.

Use four native-size, transparent I4 image assets generated at their final
size—never a font glyph, runtime scaling, clipping, arcs, or transforms:

- **offline:** a familiar Wi-Fi outline with a diagonal cut;
- **weak:** dot and lowest arc;
- **medium:** dot and two arcs;
- **strong:** dot and three arcs.

Connected states use the existing muted status colour `#9298A2`, not full
white. Offline uses the same muted colour so connectivity remains secondary
chrome rather than an alert. Wi-Fi setup may use the strong asset but does not
change its size or colour.

Each asset must preserve at least two fully transparent pixels between bright
bands at native size. Transparent corners, exact decoded pixels, palette, and
byte-for-byte regeneration are test contracts.

## State and ownership

`torget_wifi_signal_bars()` remains the single data source. The platform maps
0/1/2/3 directly to the four assets and changes only the image source when the
state changes. No page owns or calculates signal strength.

The status host belongs to the shared translated shell and is created after
the app roots so it remains visible in its reserved slot. It must not use
`lv_layer_top()`. The visibility contract remains explicit:

- boot and full-screen private/maintenance states may hide it;
- ordinary apps, launcher, OTA-ready, and Wi-Fi setup use the shared slot;
- page switching and provider switching do not recreate the object;
- pixel drift moves the page and status host together.

## Verification and acceptance

Before production code changes, regressions must fail on the current tree and
independently prove:

1. the Wi-Fi host is not parented to `lv_layer_top()` and shares `tg.shift`;
2. every drift step preserves the exact relative offset between the header
   divider/context and the status mark;
3. the four named assets are distinct native `20 x 18` rasters with transparent
   corners and AMOLED-safe internal gaps;
4. no icon pixels touch the divider or enter the header text lane;
5. all ordinary 480 x 480 surfaces use the same slot and visibility policy.

Then generate and inspect exact LVGL captures at 1:1 for strong, medium, weak,
offline, launcher, GitHub, values, Codex, Claude, OTA-ready, and Wi-Fi setup.
The corrected rasters are shown to the user before any ESP32 build or flash.

After visual approval: run the complete repository suite, build the ESP32-S3
image once, ask for explicit flash authorization, write only `ota_1`, and leave
the `ota_0` rollback image untouched. Final acceptance requires another
straight-on physical photograph; simulator green is not physical approval.
