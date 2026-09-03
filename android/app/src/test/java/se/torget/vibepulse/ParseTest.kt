package se.torget.vibepulse

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.fail
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import se.torget.vibepulse.data.AgentStatus
import se.torget.vibepulse.data.GitHub
import se.torget.vibepulse.data.MaxTracker
import se.torget.vibepulse.data.Tokens
import se.torget.vibepulse.data.ValueState

/**
 * Parsed against the project's real `sim-fixtures/`, copied verbatim into test
 * resources. These are the same payloads the firmware's own QA runs on, so a
 * disagreement here is a disagreement with the panel, not with my reading of
 * the docs.
 */
class ParseTest {


    /**
     * JUnit's assertNotNull returns Unit, so it cannot double as a smart cast.
     * This fails the test with a useful message and hands back a non-null value.
     */
    private fun <T> required(value: T?): T {
        if (value == null) fail("expected a value, got null")
        return value!!
    }

    private fun fixture(name: String): String =
        checkNotNull(javaClass.classLoader?.getResourceAsStream("fixtures/$name")) {
            "missing fixture $name"
        }.bufferedReader().readText()

    @Test
    fun tokensFixtureParses() {
        val t = required(Tokens.parse(fixture("tokens.json")))
        assertEquals(219108100.0, t.dayTokens, 0.5)
        assertEquals(6, t.daySessions)
        assertEquals(21.0, t.claudeSession.pct!!, 0.01)
        assertEquals(256, t.claudeSession.resetMin)
        assertEquals(47.0, t.claudeWeek.pct!!, 0.01)
        assertEquals(9120, t.claudeWeek.resetMin)
    }

    /**
     * Null quota means unknown. It must stay null so the view can dash it --
     * this is the live shape on a real host, where the session window can be
     * present while another is not.
     */
    @Test
    fun nullQuotaStaysUnknownRatherThanZero() {
        val t = required(Tokens.parse("""{"v":2,"claudeSessionPct":null,
            "claudeSessionResetMin":null,"claudeWeekPct":9.0}"""))
        assertNull(t.claudeSession.pct)
        assertNull(t.claudeSession.resetMin)
        assertEquals(9.0, t.claudeWeek.pct!!, 0.01)
    }

    /** `{"error": ...}` is valid JSON and must never be shown as data. */
    @Test
    fun serviceErrorShapeIsRejected() {
        assertNull(Tokens.parse("""{"error":"internal server error"}"""))
        assertNull(AgentStatus.parse("""{"error":"internal server error"}"""))
        assertNull(MaxTracker.parse("""{"error":"internal server error"}"""))
    }

    @Test
    fun garbageAndWrongVersionAreRejected() {
        assertNull(Tokens.parse("not json"))
        assertNull(Tokens.parse("""{"v":1,"dayTokens":5}"""))
        assertNull(AgentStatus.parse("""{"v":1,"agents":{}}"""))
        // GitHub is the one v1 payload, so a v2 body there is equally wrong.
        assertNull(GitHub.parse("""{"v":2,"enabled":true}"""))
        assertNull(GitHub.parse("not json"))
    }

    @Test
    fun agentJobsParse() {
        val s = required(AgentStatus.parse(fixture("agent-status-multi-working.json")))
        assertEquals(2, s.claude.size)
        assertEquals("working", s.claude[0].state)
        assertEquals("Buddy", s.claude[0].project)
        assertEquals("OPUS 5", s.claude[0].model)
        assertNull(s.pending)
    }

    @Test
    fun idleFixtureHasNoJobs() {
        val s = required(AgentStatus.parse(fixture("agent-status-idle.json")))
        assertTrue(s.claude.isEmpty())
        assertNull(s.pending)
    }

    /** A v1 pending carries neither provider nor digest; the answer must stay v1. */
    @Test
    fun v1PendingHasNoBindingFields() {
        val s = required(AgentStatus.parse(fixture("agent-status-needs-you-question.json")))
        val p = required(s.pending)
        assertEquals("6750af25a1f5ab4161fc7698c3f84d60", p.requestId)
        assertEquals("question", p.kind)
        assertTrue(p.canApprove)
        assertEquals("Which authentication approach?", p.prompt)
        assertNull(p.provider)
        assertNull(p.viewSha256)
    }

    /**
     * Provider and digest are protocol fields that v2 signing binds, so they are
     * still parsed even though this panel only displays Claude. The fixture is
     * simply the one the repository ships for a v2 pending.
     */
    @Test
    fun v2PendingCarriesProviderAndDigest() {
        val s = required(
            AgentStatus.parse(fixture("agent-status-needs-you-codex-approval.json"))
        )
        val p = required(s.pending)
        assertEquals("codex", p.provider)
        assertEquals(
            "a357f0e125e5c3d47fe46c0c24f881e091a6d464574e066584fe5e81937901ec",
            p.viewSha256,
        )
        assertEquals("Shell", p.tool)
        assertTrue(p.canApprove)
    }

    /**
     * The stripped view. The server refuses an approve on it, so the button
     * must be disabled rather than letting the tap earn an opaque 409.
     */
    @Test
    fun privatePendingCannotBeApproved() {
        val s = required(AgentStatus.parse(fixture("agent-status-needs-you-private.json")))
        val p = required(s.pending)
        assertFalse(p.canApprove)
        assertNull(p.prompt)
        assertNull(p.title)
    }

    @Test
    fun trackerFixtureParses() {
        val t = required(MaxTracker.parse(fixture("max-tracker-live-shape.json")))
        assertEquals(20, t.weeks)
        assertFalse(t.stale)
        assertEquals(2, t.codingStreakDays)
        assertEquals("MAX 20X", t.claude.planLabel)
        assertEquals(140, t.claude.days.size)
        assertEquals(20, t.claude.weekMaxed.size)
        assertEquals(59.1, t.claude.avgPeakPct!!, 0.01)
        // -1 is "no data", not a zero-height cell.
        assertEquals(Pair(-1, -1), t.claude.days[0])
        assertEquals(Pair(99, 1), t.claude.days[126])
        assertEquals(Pair(100, 1), t.claude.days[130])
    }

    @Test
    fun emptyAndColdstartTrackersDoNotCrash() {
        required(MaxTracker.parse(fixture("max-tracker-empty.json")))
        assertNotNull(MaxTracker.parse(fixture("max-tracker-coldstart.json")))
    }

    @Test
    fun githubFixturesParse() {
        val g = required(GitHub.parse(fixture("github.json")))
        assertTrue(g.enabled)
        assertEquals(42, g.stars)
        assertEquals("niclasvestlund-YT/vibepulse", g.repo)

        // "missing" here means the counts are absent, not that monitoring is
        // off: the fixture is still enabled. Absent counts must stay null so the
        // view dashes them instead of claiming zero stars.
        val missing = required(GitHub.parse(fixture("github-missing.json")))
        assertTrue(missing.enabled)
        assertNull(missing.stars)
        assertNull(missing.forks)
        assertTrue(missing.stale)
    }

    @Test
    fun missingTokensFixtureDoesNotInventNumbers() {
        val t = Tokens.parse(fixture("tokens-missing.json"))
        if (t != null) {
            assertNull(t.claudeWeek.pct)
            assertEquals(ValueState.UNAVAILABLE, t.value.state)
        }
    }

    /** Every shipped fixture must parse or be explicitly rejected, never crash. */
    @Test
    fun allAgentFixturesSurviveParsing() {
        val names = listOf(
            "agent-status-claude-done.json", "agent-status-claude-error.json",
            "agent-status-claude-waiting.json", "agent-status-claude-working.json",
            "agent-status-codex-done.json", "agent-status-codex-error.json",
            "agent-status-codex-waiting.json", "agent-status-codex-working.json",
            "agent-status-multi-done.json", "agent-status-unknown.json",
            "agent-status-needs-you-approval.json",
            "agent-status-needs-you-codex-question.json",
            "agent-status-needs-you-question-long.json",
        )
        for (n in names) {
            AgentStatus.parse(fixture(n))  // must not throw
        }
    }
}
