# VibePulse Claude Stale Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover fresh Claude quota data promptly after the official Claude client renews its credential, then publish the correction immediately without hidden Claude activity.

**Architecture:** Keep Anthropic rate-limit backoff unchanged, but give purely local authentication-wait states a short retry interval because those checks make no upstream request until a usable credential appears. Extend the numbers publisher's per-endpoint successful-send state with the set of stale flags so one stale-to-fresh `/api/tokens` correction can bypass the normal five-minute write ceiling.

**Tech Stack:** Python 3.11+, `unittest`, existing tokenserver background probe, existing Cloudflare numbers publisher.

---

## File map

- `tools/tokenserver/tokenserver.py`: select the short local-auth recovery interval while preserving upstream and 429 backoff.
- `tools/tokenserver/test_tokenserver.py`: pin local-only retries, zero upstream traffic for unchanged expired/dead credentials, and renewed-credential recovery.
- `tools/tokenserver/publisher.py`: remember successful stale fields and allow one immediate recovery publication.
- `tools/tokenserver/test_publisher.py`: pin recovery bypass, failed-send retry, normal ceiling, non-token isolation, and daily budget.

### Task 1: Fast local credential recovery

**Files:**
- Modify: `tools/tokenserver/test_tokenserver.py`
- Modify: `tools/tokenserver/tokenserver.py`

- [ ] **Step 1: Write failing interval and credential-safety tests**

Add tests beside `test_probe_backoff_interval_grows_with_failures` that set
`_probe_status` to each local authentication-wait status and require a new
`AUTH_RECOVERY_EVERY_S` interval. Retain the existing 240/480/960-second
expectations for ordinary failures and 429 state. Add an expired-candidate test
whose patched `urlopen` raises if called, and a two-cycle test whose first
candidate is expired and second candidate is renewed and returns a valid usage
response.

```python
def test_local_auth_wait_states_retry_quickly(self):
    for status in ("no_claude_oauth_token",
                   "token_expired_18:15",
                   "token_dead_awaiting_refresh"):
        with self.subTest(status=status), \
                mock.patch.object(tokenserver, "_probe_status", status):
            self.assertEqual(tokenserver._probe_interval_s(),
                             tokenserver.AUTH_RECOVERY_EVERY_S)

def test_expired_token_recheck_makes_no_upstream_request(self):
    expired_ms = (time.time() - 60) * 1000
    with mock.patch.object(tokenserver, "_read_oauth_candidates",
                           return_value=[("expired", expired_ms)]), \
            mock.patch.object(tokenserver.urllib.request, "urlopen",
                              side_effect=AssertionError("network called")):
        self.assertIsNone(tokenserver._probe_limits_locked())

def test_renewed_token_is_used_on_next_local_recheck(self):
    expired_ms = (time.time() - 60) * 1000
    candidates = [[("old", expired_ms)], [("renewed", None)]]
    with mock.patch.object(tokenserver, "_read_oauth_candidates",
                           side_effect=candidates), \
            mock.patch.object(tokenserver.urllib.request, "urlopen",
                              return_value=_FakeUsageResponse({"limits": [
                                  {"kind": "weekly_all", "percent": 7,
                                   "resets_at": "2100-01-02T00:00:00+00:00"},
                              ]})):
        self.assertIsNone(tokenserver._probe_limits_locked())
        self.assertEqual(tokenserver._probe_limits_locked()["weekPct"], 7.0)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
./.venv/bin/python -m unittest \
  tools.tokenserver.test_tokenserver.ClaudeLimitHeaderTests -v
```

Expected: the new interval assertion fails because local auth waits still use
the exponential interval; `AUTH_RECOVERY_EVERY_S` does not yet exist.

- [ ] **Step 3: Implement the minimal interval policy**

Add a small constant and status predicate near `_probe_interval_s`:

```python
AUTH_RECOVERY_EVERY_S = 15.0
_LOCAL_AUTH_WAIT_PREFIXES = (
    "no_claude_oauth_token",
    "token_expired_",
    "token_dead_awaiting_refresh",
)

def _probe_interval_s():
    if _probe_status.startswith(_LOCAL_AUTH_WAIT_PREFIXES):
        return AUTH_RECOVERY_EVERY_S
    return LIMITS_EVERY_S * (2 ** min(_probe_failure_streak, 2))
```

Do not change `_probe_limits_locked`: its existing candidate checks are the
security boundary that prevents expired and known-dead credentials from making
network requests.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Task 1 command again. Expected: all `ClaudeLimitHeaderTests` pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add tools/tokenserver/tokenserver.py tools/tokenserver/test_tokenserver.py
git commit -m "fix: detect renewed Claude credentials promptly"
```

### Task 2: Immediate stale-to-fresh relay correction

**Files:**
- Modify: `tools/tokenserver/test_publisher.py`
- Modify: `tools/tokenserver/publisher.py`

- [ ] **Step 1: Write failing publisher recovery tests**

Add tests that first successfully publish stale `/api/tokens`, advance only one
30-second tick, switch the same stale fields to `False`, and require a second
send. Add a failed-recovery case that retries on the following tick. Add a
non-token test proving identical-looking flags on `/api/github` remain capped.

```python
def test_tokens_stale_to_fresh_bypasses_the_ceiling_once(self):
    value = {"claudeWeekStale": True, "claudeWeekPct": 6}
    p, sent, clock = self._publisher({
        "/api/tokens": lambda: dict(value),
    })
    self.assertEqual(p.publish_once(), 1)
    value.update(claudeWeekStale=False, claudeWeekPct=7)
    clock["now"] += 30
    self.assertEqual(p.publish_once(), 1)
    clock["now"] += 30
    self.assertEqual(p.publish_once(), 0)
    self.assertEqual(len(sent), 2)

def test_failed_tokens_recovery_retries_next_tick(self):
    value = {"claudeWeekStale": True}
    p, sent, clock = self._publisher({
        "/api/tokens": lambda: dict(value),
    }, results=[True, False, True])
    self.assertEqual(p.publish_once(), 1)
    value["claudeWeekStale"] = False
    clock["now"] += 30
    self.assertEqual(p.publish_once(), 0)
    clock["now"] += 30
    self.assertEqual(p.publish_once(), 1)
    self.assertEqual(len(sent), 3)
```

- [ ] **Step 2: Run publisher tests and verify RED**

Run:

```bash
./.venv/bin/python -m unittest tools.tokenserver.test_publisher -v
```

Expected: the new recovery assertions fail because the five-minute ceiling
currently blocks every early change.

- [ ] **Step 3: Implement successful stale-field state**

Add a bounded helper:

```python
def stale_fields(payload) -> frozenset[str]:
    if not isinstance(payload, dict):
        return frozenset()
    return frozenset(
        key for key, value in payload.items()
        if key.endswith("Stale") and value is True
    )
```

Change publisher state to `(fingerprint, sent_at, stale_fields)`. For
`/api/tokens`, define recovery as any previously stale field now explicitly
present with value `False`. Allow that recovery to skip `should_send`; after a
successful POST store the new fingerprint, timestamp, and stale-field set.
Leave state untouched after failure so the next tick retries.

- [ ] **Step 4: Run publisher and budget tests and verify GREEN**

Run:

```bash
./.venv/bin/python -m unittest tools.tokenserver.test_publisher -v
```

Expected: all publisher tests pass, including the existing two-publisher daily
budget ceiling.

- [ ] **Step 5: Commit Task 2**

```bash
git add tools/tokenserver/publisher.py tools/tokenserver/test_publisher.py
git commit -m "fix: publish fresh Claude recovery immediately"
```

### Task 3: Integration and live verification

**Files:**
- No new production files expected

- [ ] **Step 1: Run the complete tokenserver regression set**

```bash
./.venv/bin/python -m unittest \
  tools.tokenserver.test_tokenserver \
  tools.tokenserver.test_publisher -v
```

Expected: all tests pass with no traceback or leaked credential data.

- [ ] **Step 2: Run repository gates**

```bash
PYTHON_BIN="$PWD/.venv/bin/python" ./test/run.sh --skip-js
```

Expected: exit 0. This change is Python-only; the already independently green
Cloudflare Workers runtime need not be reinstalled to validate it.

- [ ] **Step 3: Restart the user tokenserver and verify local health**

Restart the existing launchd service, then verify `/` reports
`usage_http_200 + ok` and `/api/tokens` has false Claude stale flags. Print only
safe percentages/statuses, never the relay URL or credential values.

- [ ] **Step 4: Verify Cloudflare recovery behavior**

Read the relay base URL from the existing private launchd arguments without
printing it. Confirm `/api/tokens` matches the local fresh Claude percentages
and false stale flags. This proves the actual publisher/Worker/panel data path.

- [ ] **Step 5: Final scope review and commit if verification required edits**

```bash
git diff --check
git status --short
git log --oneline -5
```

Expected: only the design/plan and four scoped Python files are changed across
the feature commits; no secrets, relay URLs, SDK config, firmware partitions,
or generated files are present.
