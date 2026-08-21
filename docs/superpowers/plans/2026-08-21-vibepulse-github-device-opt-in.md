# VibePulse GitHub Device Opt-In Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the already-working GitHub page on this physical panel without changing the open-source default or enabling notifications/sound.

**Architecture:** Retain compile-time opt-in. Change only the gitignored local `secrets.h`, verify tracked examples/tests still default off, then build and inspect the existing GitHub simulator/page path.

**Tech Stack:** ESP-IDF C configuration, Python wiring tests, SDL simulator.

---

### Task 1: Protect the open-source default

**Files:**
- Verify: `secrets.h.example`
- Verify: `test/test_github_wiring.py`
- Local-only modify: `secrets.h` (gitignored; never stage)

- [ ] **Step 1: Run the default-off guard before changing local config**

Run:

```sh
./.venv/bin/python test/test_github_wiring.py -v
git check-ignore -v secrets.h
```

Expected: the test passes, the example contains `TK_GITHUB_SCREEN_ENABLED 0`, and Git ignores `secrets.h`.

- [ ] **Step 2: Enable only the screen on this device**

Change exactly this ignored line:

```c
#define TK_GITHUB_SCREEN_ENABLED 1
```

Leave these lines at zero:

```c
#define TK_GITHUB_NOTIFICATIONS_ENABLED 0
#define TK_GITHUB_SOUND_ENABLED 0
```

- [ ] **Step 3: Prove the local setting is not staged or tracked**

Run:

```sh
git status --short
git diff -- secrets.h secrets.h.example
```

Expected: no `secrets.h` entry and no tracked default change.

### Task 2: Verify the existing GitHub page path

**Files:**
- Test: `test/test_github_wiring.py`
- Test: `test/test_vibepulse_visual_landmarks.py`

- [ ] **Step 1: Run focused wiring and simulator tests**

Run:

```sh
./.venv/bin/python test/test_github_wiring.py -v
cmake --build sim/build -j4
PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python \
  test/test_vibepulse_visual_landmarks.py -v
```

Expected: GitHub screen-on and screen-off compile contracts pass; the GitHub capture shows stars/forks and respects the top-right Wi-Fi lane.

- [ ] **Step 2: Build the target with the ignored setting**

Run the repository's normal ESP-IDF 5.5 build in a disposable build directory. Confirm the compile command contains `TK_GITHUB_SCREEN_ENABLED=1` through the included `secrets.h` and that no private file enters Git.

- [ ] **Step 3: Do not create a Git commit for the local switch**

The screen opt-in is intentionally a per-device ignored configuration change. Any tracked documentation/test changes discovered during verification must be a separate tightly scoped commit.
