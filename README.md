# vibescreen

**Turn an old Android phone into an always-on dashboard for Claude Code.**

Quota, burn rate, and what your agents are doing right now — on a screen you
already own, sitting on your desk, that you never have to switch windows to
read.

No hardware to buy. No account. Nothing leaves your machine.

---

## The problem

Run Claude Code all day and two things stay invisible:

- **How much quota is left.** You find out you're at the wall when a long task
  dies halfway through — not before you start it.
- **When an agent stopped.** It asks one question, then just sits there. You're
  in another window. Sometimes for twenty minutes.

Both answers already exist in a terminal you aren't looking at. This puts them
on a second screen you can't miss.

## What you see

Five views, swiped horizontally:

| View | Shows |
|---|---|
| **Session** | The session window as the hero number — it's what actually stops you mid-task. Week, week reset, and today's tokens alongside. |
| **Burn rate** | The weekly forecast: on pace, or running out early and when. |
| **Max Tracker** | Twenty weeks of daily quota peaks as a heatmap. |
| **GitHub** | Star and fork counts, when enabled. |
| **Value** | What the month would have cost at list API prices, against what you pay. |

Under every page sits the **live agent strip** — one row per Claude Code
session:

| Colour | State | Meaning |
|---|---|---|
| 🟡 `❚❚` | `waiting` | **Stopped, needs you.** Waiting on input or approval. |
| ⚪ `▶` | `working` | Thinking, editing, reading, searching, running, testing, building. |
| 🟢 `✓` | `done` | Finished. |
| 🔴 `!` | `error` | Failed. |

That yellow is the point of the whole thing: an agent that asked something
twenty minutes ago and is still sitting there.

The **Claude pet** sits beside the session percentage and dances while an agent
is actually working — motion answers "is anything happening?" from across a
room faster than reading a word. It goes still and dim when nothing is running,
because a pet that danced constantly would just teach you to ignore it.

When a decision is parked, a full-screen **NEEDS YOU** notice takes over with
the project, the command, and a countdown to the terminal fallback.

## It watches, it does not act

This is a **read-only dashboard**, deliberately.

It issues only four HTTP GETs. It holds no key, signs nothing, and sends no
POST of any kind. A waiting decision appears on screen so you know it exists —
you answer it at the terminal.

## How it connects

A small Python service on your computer reads your local Claude usage and
serves it as JSON. The phone polls it. Two ways to reach it:

**USB (recommended).** `adb reverse` maps a port from the phone back to your
computer, so the phone's own `localhost:8737` *is* the service. Nothing is
exposed to any network, no pairing, and it works with WiFi switched off.

**Bluetooth.** Classic RFCOMM through a bridge on the computer, for a shelf
with no cable. The bridge forwards GETs only.

```
Claude Code ──> tokenserver ──USB adb reverse──> phone app
              (your computer) ──Bluetooth RFCOMM──> phone app
```

## Quick start

Requires Python 3.11+, a JDK 17 and the Android SDK to build. On the phone:
Developer options → **USB debugging** *and* **Install via USB**.

```powershell
# 1. Build, install, and connect over USB
.\tools\phone-panel.ps1

# 2. Keep it running after you close the terminal (and across reboots)
.\tools\btbridge\install-phone-panel-tasks.ps1
```

After replugging the cable, `.\tools\phone-panel.ps1 -ReverseOnly` restores the
mapping.

Full setup, Bluetooth pairing, troubleshooting, and toolchain notes:
**[docs/phone-panel.md](docs/phone-panel.md)**

## Tested on

A Poco F3 (`alioth`) running Android 13 — both transports live, all five views,
the waiting notice, and both orientations. Neither orientation scrolls:
landscape lays out in two columns rather than stacking, because a panel that
hides half its numbers is not glanceable.

Built with `minSdk 26`, so anything from Android 8 up should work.

## Layout

```
android/          the phone app (Kotlin, Jetpack Compose)
tools/tokenserver/  the service that reads Claude usage and serves JSON
tools/btbridge/     Bluetooth RFCOMM bridge + the service installer
tools/phone-panel.ps1  build, install, connect
docs/phone-panel.md    full documentation
```

## Credits

**Inspired by — and built on — [VibePulse](https://github.com/niclasvestlund-YT/vibepulse)
by [Niclas Vestlund](https://github.com/niclasvestlund-YT).**

VibePulse is a genuinely lovely project: an always-on ESP32-S3 shelf panel that
shows the same information on real hardware, and can answer agent prompts with a
tap on the glass. Its tokenserver — the part that reads Claude usage and serves
it as JSON — is used here largely unchanged, and this dashboard is a
reimplementation of its panel for a phone.

What's different here:

- **A phone instead of a $30 ESP32-S3 panel.** No hardware, no soldering, no
  flashing. The firmware, simulator, OTA and WiFi-provisioning tooling are all
  removed.
- **Claude Code only.** Every Codex surface is gone.
- **Read-only.** VibePulse can answer a prompt from the glass with a signed
  verdict; this deliberately cannot.

If you want the real shelf appliance, with the tap-to-answer loop and a screen
that isn't a phone you had in a drawer — go get VibePulse. It's the better toy.

## Licence

MIT, inherited from VibePulse. See [LICENSE](LICENSE) — copyright © 2026 Niclas
Vestlund, whose work this is built on.
