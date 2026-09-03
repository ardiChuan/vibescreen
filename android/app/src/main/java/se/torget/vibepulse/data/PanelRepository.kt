package se.torget.vibepulse.data

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import se.torget.vibepulse.net.Transport

/**
 * The panel loop. Read only.
 *
 * This panel watches and never answers. It holds no device key, signs nothing,
 * and issues no POST at all -- the only requests it makes are the four GETs
 * below. A decision still shows up on the glass so you know one is waiting,
 * but it is answered at the terminal.
 *
 * Cadence follows the firmware: `/api/agent-status` every second because it is
 * the one that can carry a waiting decision, and the slower endpoints on longer
 * intervals. An alert that arrives thirty seconds late has already fallen back
 * to the terminal.
 *
 * Failures never clear the screen. An unreachable server means "stale", with
 * the last good numbers kept and labelled -- a blank panel and a panel reading
 * 0% look identical from across the room, and only one of them is honest.
 */
class PanelRepository(private val scope: CoroutineScope) {

    data class State(
        val tokens: Tokens? = null,
        val agents: AgentStatus? = null,
        val tracker: MaxTracker? = null,
        val github: GitHub? = null,
        val connected: Boolean = false,
        val transportLabel: String = "—",
        /** Seconds since the last successful poll, for the stale marker. */
        val staleSeconds: Long = 0,
        val lastError: String? = null,
    )

    private val _state = MutableStateFlow(State())
    val state: StateFlow<State> = _state.asStateFlow()

    @Volatile private var transport: Transport? = null
    private var loop: Job? = null
    private var lastOkMs: Long = 0

    fun setTransport(t: Transport?) {
        transport?.close()
        transport = t
        _state.value = _state.value.copy(
            transportLabel = t?.label ?: "—",
            connected = false,
        )
    }

    fun start() {
        if (loop?.isActive == true) return
        loop = scope.launch {
            var tick = 0L
            while (isActive) {
                val startedAt = System.currentTimeMillis()
                val t = transport
                if (t == null) {
                    delay(500)
                    continue
                }

                pollAgents(t)
                // The quota windows move in minutes and the tracker in days, so
                // polling them every second would be pure noise on a link that
                // may be a Bluetooth serial channel.
                if (tick % 5L == 0L) pollTokens(t)
                if (tick % 60L == 0L) pollTracker(t)
                if (tick % 60L == 30L) pollGithub(t)

                tick++
                val since = (System.currentTimeMillis() - lastOkMs) / 1000
                _state.value = _state.value.copy(
                    staleSeconds = if (lastOkMs == 0L) 0 else since,
                )

                // Sleep for what is LEFT of the second, not a full second on top
                // of the requests. Sleeping afterwards makes every tick
                // 1000 ms + round-trip, which over a Bluetooth serial link
                // stretches the whole schedule.
                val elapsed = System.currentTimeMillis() - startedAt
                delay((1000L - elapsed).coerceIn(50L, 1000L))
            }
        }
    }

    fun stop() {
        loop?.cancel()
        loop = null
    }

    private suspend fun pollAgents(t: Transport) {
        when (val r = t.request("GET", "/api/agent-status")) {
            is Transport.Response.Success -> {
                val parsed = AgentStatus.parse(r.body)
                if (parsed != null) {
                    markOk()
                    _state.value = _state.value.copy(agents = parsed)
                } else {
                    markBad("agent-status: unusable payload")
                }
            }
            is Transport.Response.Failure -> markBad(r.reason)
        }
    }

    private suspend fun pollTokens(t: Transport) {
        val r = t.request("GET", "/api/tokens")
        if (r is Transport.Response.Success) {
            Tokens.parse(r.body)?.let {
                markOk()
                _state.value = _state.value.copy(tokens = it)
            }
        }
    }

    private suspend fun pollTracker(t: Transport) {
        val r = t.request("GET", "/api/max-tracker")
        if (r is Transport.Response.Success) {
            MaxTracker.parse(r.body)?.let { _state.value = _state.value.copy(tracker = it) }
        }
    }

    private suspend fun pollGithub(t: Transport) {
        val r = t.request("GET", "/api/github")
        if (r is Transport.Response.Success) {
            GitHub.parse(r.body)?.let { _state.value = _state.value.copy(github = it) }
        }
    }

    private fun markOk() {
        lastOkMs = System.currentTimeMillis()
        _state.value = _state.value.copy(connected = true, lastError = null, staleSeconds = 0)
    }

    private fun markBad(reason: String) {
        _state.value = _state.value.copy(connected = false, lastError = reason)
    }
}
