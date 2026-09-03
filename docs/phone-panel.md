# The phone panel

An Android app that puts the ESP32 panel's numbers on a phone you already own.
Built against a Poco F3, but nothing in it is specific to that model.

It is a **read-only dashboard**. It watches and never answers: no device key, no
signing, no POST of any kind. A waiting decision still appears on screen so you
know one exists, but you answer it at the terminal.

| | ESP32 panel | Phone panel |
|---|---|---|
| Transport | WiFi, LAN | USB (`adb reverse`), or Bluetooth RFCOMM |
| Endpoints | `/api/tokens`, `/api/agent-status`, `/api/max-tracker`, `/api/github` | identical |
| Answering | signed `POST /api/interaction/<id>` | **none — read only** |
| Screen | 480 × 480 round | 1080 × 2400, either orientation |

**The tokenserver is unmodified.** No new routes, no new port, no unsigned
answer path. The Windows release gate's firewall and discovery evidence is
untouched, because nothing about it changed.

## What it shows

Five views, swiped horizontally:

1. **Session** — the Claude session window as the hero number, with the weekly
   window, its reset, and today's tokens alongside. The session is what stops
   you mid-task, so it gets the big number.
2. **Burn rate** — the weekly forecast, plus volume counters.
3. **Max Tracker** — twenty weeks of daily peaks as a heatmap.
4. **GitHub** — star and fork counts, when enabled.
5. **Value** — what the month would have cost at list API prices.

Codex is absent throughout: this build is Claude-only.

Under every page sits the **live agent strip**, which portrait has room for and
the round panel does not. Each row is one Claude Code session:

| Colour | State | Meaning |
|---|---|---|
| Yellow `❚❚` | `waiting` | The agent has stopped and needs you (`waiting_input` or `waiting_approval`) |
| White `▶` | `working` | Thinking, editing, reading, searching, running, testing, building |
| Green `✓` | `done` | Finished |
| Red `!` | `error` | Failed |

The **Claude pet** sits beside the session percentage and dances while any agent
is actually `working`, dimming and going still when none is. Motion answers "is
anything happening?" from across a room faster than reading a word — which is
why it is bound to real state rather than always running. A pet that danced
while nothing happened would just teach you to ignore it.

When a decision is parked, a full-screen **NEEDS YOU** notice takes over with
the project, the command, and a countdown to the terminal fallback. It has no
buttons.

## Setup: USB (recommended)

`adb reverse` maps a port from the phone back to this computer, so the phone's
own `localhost:8737` becomes the tokenserver. Nothing is exposed to any network,
no pairing is involved, and it works on a phone with no SIM and WiFi off.

### One time, on the phone

1. Settings → About phone → tap **MIUI version** seven times.
2. Settings → Additional settings → **Developer options**.
3. Enable **USB debugging** and, on MIUI, **Install via USB** — a separate
   toggle, and installs fail silently without it.

### One time, on the computer

Building needs a JDK 17 and the Android SDK; see [Toolchain](#toolchain).

```powershell
.\tools\phone-panel.ps1
```

Builds the APK, installs it, establishes the reverse mapping, and launches it.

### Every time you replug the cable

The mapping lives in the adb daemon, not on the phone, so unplugging drops it:

```powershell
.\tools\phone-panel.ps1 -ReverseOnly
```

## Setup: Bluetooth

For a shelf with no cable. Classic RFCOMM, not BLE: BLE's ~247-byte MTU would
mean chunking a 3.5 KB agent-status payload for no benefit.

```powershell
# Pair the phone with this computer first, in Windows Bluetooth settings.
python tools/btbridge/bt_bridge.py
```

The bridge prints the adapter address and the channel it bound:

```
[bridge] listening on RFCOMM channel 5 (adapter A0:80:69:87:29:03)
[bridge] enter address A0:80:69:87:29:03 and channel 5 in the app
```

Enter both in the app's settings and switch the transport to Bluetooth. Android
will ask for the nearby-devices permission; nothing works until it is granted.

### Why you type a channel number

Android's normal call, `createRfcommSocketToServiceRecord(uuid)`, asks the
computer to advertise an SDP record naming its channel. Python's socket module
on Windows can bind and listen on an RFCOMM channel but cannot register that
record, so the lookup finds nothing. The app therefore connects to a channel
number directly, through the reflective `createRfcommSocket(int)`.

That reflection is community knowledge rather than public API and some vendor
stacks restrict it. **It was verified working on a Poco F3 running Android 13
(MIUI).** If another device refuses to connect, this is the most likely reason
and USB is the answer.

Channel 1 is usually reserved and 2–3 are often taken by system profiles, which
is why the bridge tries several and reports which it got.

### What the bridge carries

GETs, and nothing else. It forwards only the four panel endpoints; every POST is
refused before the HTTP call, so neither the answer routes nor the loopback-only
hook routes (`/api/hook/…`, `/api/codex/…`) are reachable through it.

## Keeping the screen on

The app holds `FLAG_KEEP_SCREEN_ON` while open. For a permanently-on shelf
display, also plug it in and enable Developer options → **Stay awake while
charging**. On an AMOLED the true-black background leaves most of the panel
genuinely unlit.

Both orientations are supported and neither scrolls: landscape lays the page out
in two columns rather than stacking, because a glanceable panel that hides half
its numbers is not glanceable.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `stale`, numbers frozen | `adb reverse` was lost — re-run with `-ReverseOnly`. Or the tokenserver is not running. |
| `Cleartext HTTP traffic not permitted` | Should not occur; the app ships a network security config. If it returns, that file was lost. |
| Install fails on MIUI | **Install via USB** is a separate toggle from USB debugging. |
| Bluetooth never connects | Most likely the reflective socket is blocked on that ROM. Use USB. |
| Quota shows `—` | The server genuinely sent `null`. Unknown is not zero, so the panel dashes it rather than inventing a number. |
| Everything reads idle but agents are running | The tokenserver is not seeing them; check it is running against the right projects directory. |

## Testing without a phone

```powershell
# Parsing, against the project's real sim-fixtures.
cd android; ..\..\.toolchain\gradle-8.7\bin\gradle.bat testDebugUnitTest

# The Bluetooth bridge: framing and the path allowlist, over a socketpair,
# with no radio involved.
python tools/btbridge/test_bt_bridge.py
```

The framing tests matter more than they look. RFCOMM is a byte stream, so a
"read until it goes quiet" loop truncates a 3.5 KB body intermittently — and a
truncated JSON body is indistinguishable from a parser bug.

## An inherited limit worth knowing

`/api/agent-status` is capped at 3584 bytes server-side (`response_fits` in
`tools/tokenserver/interactions.py`). When the agent list plus the pending
decision would exceed it, the server keeps the agent list and **drops the
pending item**, logging that it did.

That cap exists because the firmware discards the whole body past its 4 KB
buffer. A phone has no such constraint, but the truncation happens on the
computer, so the app inherits it: with enough simultaneously active jobs, a
waiting decision can be omitted and the phone will never show it.

This is deliberately not changed. The cap is part of the contract the board
depends on, and widening it for the phone would mean the two panels no longer
see the same `/api/agent-status`.

## Toolchain

The app needs a JDK 17 and the Android SDK. Keeping them in one directory makes
removal a single command.

```powershell
$tc = "<repo parent>\.toolchain"     # jdk-17.x, android-sdk, gradle-8.7, gradle-home
$env:JAVA_HOME        = "$tc\jdk-17.0.13+11"
$env:ANDROID_HOME     = "$tc\android-sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:GRADLE_USER_HOME = "$tc\gradle-home"   # keeps Gradle's cache out of ~/.gradle
```

Contents: Temurin JDK 17, Android cmdline-tools (under `cmdline-tools/latest`,
which `sdkmanager` requires), platform-tools, `platforms;android-34`,
`build-tools;34.0.0`, and Gradle 8.7. Roughly 2.2 GB.

### Removing it

The installed APK keeps working without the toolchain; only rebuilding needs it.

```powershell
# Release the file locks first, or the delete fails.
& "$tc\android-sdk\platform-tools\adb.exe" kill-server
& "$tc\gradle-8.7\bin\gradle.bat" --stop

Remove-Item -Recurse -Force $tc
```

Nothing was installed system-wide and no user-scope environment variables were
set, so that directory is the entire footprint.
