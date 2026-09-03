package se.torget.vibepulse.data

import org.json.JSONArray
import org.json.JSONObject

/**
 * The four endpoint payloads, parsed the way the firmware parses them.
 *
 * Two rules carry over from `components/app_tokens/tokens_parse.c` and they
 * are the difference between a panel you can trust and one you cannot:
 *
 *  1. A field that is absent or null is *unknown*, not zero. It renders as a
 *     dash. Showing 0% for "we could not read your quota" is the one failure
 *     mode that actively misleads.
 *  2. The service's error shape, `{"error": "..."}`, parses as valid JSON.
 *     It must be rejected explicitly so a 500 keeps the last good values on
 *     screen instead of blanking them.
 */

private fun JSONObject.optDoubleOrNull(key: String): Double? =
    if (isNull(key)) null else optDouble(key).takeUnless { it.isNaN() }

private fun JSONObject.optIntOrNull(key: String): Int? =
    if (isNull(key) || !has(key)) null else optInt(key, Int.MIN_VALUE).takeUnless { it == Int.MIN_VALUE }

private fun JSONObject.optStringOrNull(key: String): String? =
    if (isNull(key) || !has(key)) null else optString(key).takeUnless { it.isEmpty() }

/** One quota window: a percentage, a countdown, and the change inside it. */
data class Limit(
    val pct: Double? = null,
    val resetMin: Int? = null,
    val deltaPct: Double? = null,
    val stale: Boolean = false,
)

enum class ForecastState { UNAVAILABLE, COLLECTING, AT_RESET, EXHAUSTS }

data class Forecast(
    val state: ForecastState = ForecastState.UNAVAILABLE,
    val pctAtReset: Int? = null,
    val paceFactor: Double? = null,
    val offsetMin: Int? = null,
)

enum class ValueState { UNAVAILABLE, PARTIAL, NO_PLAN_COST, OK }

data class ValueBlock(
    val state: ValueState = ValueState.UNAVAILABLE,
    val valueUsd: Double? = null,
    val planUsd: Double? = null,
    val multiple: Double? = null,
    val costConfigured: Boolean = false,
)

data class Tokens(
    val dayTokens: Double = 0.0,
    val dayTokensPerHour: Double = 0.0,
    val daySessions: Int = 0,
    val monthTokens: Double = 0.0,
    val claudeSession: Limit = Limit(),
    val claudeWeek: Limit = Limit(),
    val claudeForecast: Forecast = Forecast(),
    val value: ValueBlock = ValueBlock(),
) {
    companion object {
        fun parse(raw: String): Tokens? {
            val o = runCatching { JSONObject(raw) }.getOrNull() ?: return null
            // The error shape is valid JSON; the panel must not treat it as data.
            if (o.has("error")) return null
            if (o.optInt("v", -1) != 2) return null

            fun limit(pct: String, reset: String, delta: String, stale: String) = Limit(
                pct = o.optDoubleOrNull(pct),
                resetMin = o.optIntOrNull(reset),
                deltaPct = o.optDoubleOrNull(delta),
                stale = o.optBoolean(stale, false),
            )

            fun forecast(prefix: String): Forecast {
                val state = when (o.optStringOrNull("${prefix}ForecastState")) {
                    "collecting" -> ForecastState.COLLECTING
                    "at_reset" -> ForecastState.AT_RESET
                    "exhausts" -> ForecastState.EXHAUSTS
                    else -> ForecastState.UNAVAILABLE
                }
                return Forecast(
                    state = state,
                    pctAtReset = o.optIntOrNull("${prefix}ForecastPctAtReset"),
                    paceFactor = o.optDoubleOrNull("${prefix}ForecastPaceFactor"),
                    offsetMin = o.optIntOrNull("${prefix}ForecastOffsetMin"),
                )
            }

            val value = o.optJSONObject("value")?.let { v ->
                ValueBlock(
                    state = when (v.optStringOrNull("state")) {
                        "ok" -> ValueState.OK
                        "no_plan_cost" -> ValueState.NO_PLAN_COST
                        "partial" -> ValueState.PARTIAL
                        else -> ValueState.UNAVAILABLE
                    },
                    valueUsd = v.optDoubleOrNull("value_usd"),
                    planUsd = v.optDoubleOrNull("plan_usd"),
                    multiple = v.optDoubleOrNull("multiple"),
                    costConfigured = v.optStringOrNull("cost_source") == "configured",
                )
            } ?: ValueBlock()

            return Tokens(
                dayTokens = o.optDouble("dayTokens", 0.0),
                dayTokensPerHour = o.optDouble("dayTokensPerHour", 0.0),
                daySessions = o.optInt("daySessions", 0),
                monthTokens = o.optDouble("monthTokens", 0.0),
                claudeSession = limit(
                    "claudeSessionPct", "claudeSessionResetMin",
                    "claudeSessionHourDeltaPct", "claudeSessionStale",
                ),
                claudeWeek = limit(
                    "claudeWeekPct", "claudeWeekResetMin",
                    "claudeWeekTodayDeltaPct", "claudeWeekStale",
                ),
                claudeForecast = forecast("claude"),
                value = value,
            )
        }
    }
}

data class Job(
    val taskId: String,
    val state: String,      // working | waiting | done | error
    val project: String?,
    val activity: String?,
    val model: String?,
    val effort: String?,
)

/** The decision the panel is being asked to make. One at a time, by design. */
data class Pending(
    val requestId: String,
    val kind: String,           // question | approval
    val project: String?,
    val expiresInMs: Int,
    val holdMs: Int,
    val canApprove: Boolean,
    val provider: String?,      // absent on v1 interactions
    val viewSha256: String?,    // absent on v1 interactions
    val prompt: String?,
    val title: String?,
    val subtitle: String?,
    val tool: String?,
    val optionsTotal: Int?,
)

data class AgentStatus(
    val seq: Long = 0,
    val claude: List<Job> = emptyList(),
    val pending: Pending? = null,
) {
    companion object {
        fun parse(raw: String): AgentStatus? {
            val o = runCatching { JSONObject(raw) }.getOrNull() ?: return null
            if (o.has("error")) return null
            if (o.optInt("v", -1) != 2) return null
            val agents = o.optJSONObject("agents") ?: return null

            fun jobs(name: String): List<Job> {
                val arr: JSONArray = agents.optJSONObject(name)?.optJSONArray("jobs")
                    ?: return emptyList()
                return (0 until arr.length()).mapNotNull { i ->
                    val j = arr.optJSONObject(i) ?: return@mapNotNull null
                    Job(
                        taskId = j.optString("task_id"),
                        state = j.optString("state"),
                        project = j.optStringOrNull("project"),
                        activity = j.optStringOrNull("activity"),
                        model = j.optStringOrNull("model"),
                        effort = j.optStringOrNull("effort"),
                    )
                }
            }

            val pending = o.optJSONObject("pending")?.let { p ->
                val id = p.optStringOrNull("request_id") ?: return@let null
                Pending(
                    requestId = id,
                    kind = p.optString("kind", "approval"),
                    project = p.optStringOrNull("project"),
                    expiresInMs = p.optInt("expires_in_ms", 0),
                    holdMs = p.optInt("hold_ms", 0),
                    // Absent means false: the server omits it only when the
                    // whole view was stripped, and a stripped view is never
                    // approvable from the panel.
                    canApprove = p.optBoolean("can_approve", false),
                    provider = p.optStringOrNull("provider"),
                    viewSha256 = p.optStringOrNull("view_sha256"),
                    prompt = p.optStringOrNull("prompt"),
                    title = p.optStringOrNull("title"),
                    subtitle = p.optStringOrNull("subtitle"),
                    tool = p.optStringOrNull("tool"),
                    optionsTotal = p.optIntOrNull("options_total"),
                )
            }

            return AgentStatus(
                seq = o.optLong("seq", 0),
                claude = jobs("claude"),
                pending = pending,
            )
        }
    }
}

data class TrackerProvider(
    val planLabel: String? = null,
    val avgPeakPct: Double? = null,
    val maxWeeksStreak: Int = 0,
    val maxWeeks: Int = 0,
    val maxDays: Int = 0,
    val weekMaxed: List<Int> = emptyList(),
    /** 140 pairs of [peakPct, maxedFlag]; -1 in either slot means "no data". */
    val days: List<Pair<Int, Int>> = emptyList(),
)

data class MaxTracker(
    val weeks: Int = 0,
    val stale: Boolean = true,
    val codingStreakDays: Int = 0,
    val claude: TrackerProvider = TrackerProvider(),
) {
    companion object {
        fun parse(raw: String): MaxTracker? {
            val o = runCatching { JSONObject(raw) }.getOrNull() ?: return null
            if (o.has("error")) return null
            if (o.optInt("v", -1) != 1) return null

            fun provider(name: String): TrackerProvider {
                val p = o.optJSONObject(name) ?: return TrackerProvider()
                val weekMaxed = p.optJSONArray("weekMaxed")?.let { a ->
                    (0 until a.length()).map { a.optInt(it, 0) }
                } ?: emptyList()
                val days = p.optJSONArray("days")?.let { a ->
                    (0 until a.length()).map { i ->
                        val pair = a.optJSONArray(i)
                        Pair(pair?.optInt(0, -1) ?: -1, pair?.optInt(1, -1) ?: -1)
                    }
                } ?: emptyList()
                return TrackerProvider(
                    planLabel = p.optStringOrNull("planLabel"),
                    avgPeakPct = p.optDoubleOrNull("avgPeakPct"),
                    maxWeeksStreak = p.optInt("maxWeeksStreak", 0),
                    maxWeeks = p.optInt("maxWeeks", 0),
                    maxDays = p.optInt("maxDays", 0),
                    weekMaxed = weekMaxed,
                    days = days,
                )
            }

            return MaxTracker(
                weeks = o.optInt("weeks", 0),
                stale = o.optBoolean("stale", true),
                codingStreakDays = o.optInt("codingStreakDays", 0),
                claude = provider("claude"),
            )
        }
    }
}

data class GitHub(
    val enabled: Boolean = false,
    val repo: String? = null,
    val stars: Int? = null,
    val forks: Int? = null,
    val stale: Boolean = true,
) {
    companion object {
        fun parse(raw: String): GitHub? {
            val o = runCatching { JSONObject(raw) }.getOrNull() ?: return null
            if (o.has("error")) return null
            if (o.optInt("v", -1) != 1) return null
            return GitHub(
                enabled = o.optBoolean("enabled", false),
                repo = o.optStringOrNull("repo"),
                stars = o.optIntOrNull("stars"),
                forks = o.optIntOrNull("forks"),
                stale = o.optBoolean("stale", true),
            )
        }
    }
}
