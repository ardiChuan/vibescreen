package se.torget.vibepulse.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import se.torget.vibepulse.data.ForecastState
import se.torget.vibepulse.data.Job
import se.torget.vibepulse.data.PanelRepository
import se.torget.vibepulse.data.TrackerProvider
import se.torget.vibepulse.R
import se.torget.vibepulse.data.ValueState

/**
 * Five views, Claude only.
 *
 * The firmware ships eight because it serves two providers. This panel drops
 * every Codex surface and the heaviest-model window, which leaves the pages
 * that actually say something on a Claude-only machine.
 */
private const val PAGE_COUNT = 5

@Composable
fun Panel(
    state: PanelRepository.State,
    onOpenSettings: () -> Unit,
) {
    val pager = rememberPagerState(pageCount = { PAGE_COUNT })
    val landscape = LocalConfiguration.current.screenWidthDp >
        LocalConfiguration.current.screenHeightDp

    Column(
        Modifier
            .fillMaxSize()
            .background(VP.Background),
    ) {
        StatusBar(state, onOpenSettings)

        HorizontalPager(
            state = pager,
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
        ) { page ->
            // Rotating to landscape roughly halves the height, so each page
            // scrolls rather than clipping its stats off the bottom.
            Box(Modifier.fillMaxSize().padding(horizontal = VP.Gutter)) {
                when (page) {
                    0 -> SessionPage(state, landscape)
                    1 -> BurnRatePage(state, landscape)
                    2 -> TrackerPage(state.tracker?.claude, state.tracker?.codingStreakDays, landscape)
                    3 -> GitHubPage(state, landscape)
                    4 -> ValuePage(state, landscape)
                }
            }
        }

        Pager(current = pager.currentPage)
        AgentStrip(state)
    }
}

/* ---------------------------------------------------------------- chrome -- */

@Composable
private fun StatusBar(state: PanelRepository.State, onOpenSettings: () -> Unit) {
    val dot = when {
        state.connected -> VP.Ok
        state.staleSeconds > 30 -> VP.Bad
        else -> VP.Warn
    }
    val text = when {
        state.connected -> "${state.transportLabel} · live"
        state.staleSeconds > 0 -> "${state.transportLabel} · stale ${state.staleSeconds}s"
        else -> state.lastError ?: "connecting…"
    }
    Row(
        Modifier
            .fillMaxWidth()
            .padding(start = VP.Gutter, end = 8.dp, top = 10.dp, bottom = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(dot))
        Spacer(Modifier.width(8.dp))
        Text(
            text,
            color = VP.Muted,
            fontSize = 11.sp,
            fontFamily = FontFamily.Monospace,
            modifier = Modifier.weight(1f),
            maxLines = 1,
        )
        Text(
            "⚙",
            color = VP.Muted,
            fontSize = 18.sp,
            modifier = Modifier.padding(8.dp).clickableNoRipple(onOpenSettings),
        )
    }
}

@Composable
private fun Pager(current: Int) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 10.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        repeat(PAGE_COUNT) { i ->
            Box(
                Modifier
                    .padding(horizontal = 4.dp)
                    .size(if (i == current) 7.dp else 5.dp)
                    .clip(CircleShape)
                    .background(if (i == current) VP.DotOn else VP.Dot),
            )
        }
    }
}

/**
 * The live agent rows, visible under every view.
 *
 * On the round panel these can only be an overlay; portrait has the room to
 * keep them permanently on screen, which is the one place this panel is better
 * than the hardware it replaces.
 */
@Composable
private fun AgentStrip(state: PanelRepository.State) {
    val jobs = state.agents?.claude.orEmpty()
    Row(
        Modifier
            .fillMaxWidth()
            .background(Color(0xFF07080A))
            .padding(horizontal = VP.Gutter, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(7.dp).clip(CircleShape).background(VP.Claude))
        Spacer(Modifier.width(8.dp))
        Text(
            "CLAUDE",
            color = VP.Label,
            fontSize = 10.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.width(56.dp),
        )
        if (jobs.isEmpty()) {
            Text("idle", color = VP.Muted, fontSize = 12.sp)
        } else {
            Column {
                jobs.take(4).forEach { job ->
                    val mark = when (job.state) {
                        "working" -> "▶"
                        "waiting" -> "❚❚"
                        "done" -> "✓"
                        "error" -> "!"
                        else -> "·"
                    }
                    val colour = when (job.state) {
                        "error" -> VP.Bad
                        "waiting" -> VP.Warn
                        "done" -> VP.Ok
                        else -> VP.Meta
                    }
                    Text(
                        "$mark  ${job.project ?: "—"}  ·  ${job.activity ?: job.state}",
                        color = colour,
                        fontSize = 12.sp,
                        maxLines = 1,
                    )
                }
                if (jobs.size > 4) {
                    Text("+${jobs.size - 4} more", color = VP.Muted, fontSize = 10.sp)
                }
            }
        }
    }
}

/* ------------------------------------------------------------ furniture -- */

/**
 * The Claude pet, the same mark the firmware puts on the glass
 * (`components/app_tokens/assets/source/claude-pet-white.png`). It is a white
 * silhouette, so it is tinted rather than recoloured per page.
 */
@Composable
private fun PetMark(size: Int = 26) {
    Image(
        painter = painterResource(R.drawable.claude_pet),
        contentDescription = null,
        colorFilter = ColorFilter.tint(VP.Claude),
        contentScale = ContentScale.Fit,
        modifier = Modifier.height(size.dp).width((size * 1.6f).dp),
    )
}

/**
 * The pet, dancing while Claude is actually working.
 *
 * Motion is the cheapest way to answer "is it doing anything right now?" from
 * across a room -- faster than reading a word. So it is bound to real state
 * rather than run always: a pet that danced while nothing was happening would
 * be decoration, and worse, it would teach you to ignore it. Idle also drops
 * the tint to the muted accent, so stillness reads as deliberate.
 *
 * Bob, tilt and squash run on different periods so the loop does not read as
 * one mechanical bounce.
 */
@Composable
private fun DancingPet(working: Boolean, size: Int) {
    val transition = rememberInfiniteTransition(label = "pet")
    val bob by transition.animateFloat(
        initialValue = 0f,
        targetValue = if (working) -10f else 0f,
        animationSpec = infiniteRepeatable(tween(420), RepeatMode.Reverse),
        label = "bob",
    )
    val tilt by transition.animateFloat(
        initialValue = if (working) -9f else 0f,
        targetValue = if (working) 9f else 0f,
        animationSpec = infiniteRepeatable(tween(560), RepeatMode.Reverse),
        label = "tilt",
    )
    val squash by transition.animateFloat(
        initialValue = 1f,
        targetValue = if (working) 0.9f else 1f,
        animationSpec = infiniteRepeatable(tween(420), RepeatMode.Reverse),
        label = "squash",
    )
    Image(
        painter = painterResource(R.drawable.claude_pet),
        contentDescription = if (working) "Claude is working" else "Claude is idle",
        colorFilter = ColorFilter.tint(if (working) VP.Claude else VP.ClaudeMuted),
        contentScale = ContentScale.Fit,
        modifier = Modifier
            .height(size.dp)
            .width((size * 1.6f).dp)
            .graphicsLayer {
                translationY = bob
                rotationZ = tilt
                scaleY = squash
                scaleX = 2f - squash
            },
    )
}

/**
 * One page, laid out for the shape of the screen.
 *
 * Portrait stacks. Landscape has roughly half the height and twice the width,
 * so stacking there pushes the stats under the fold and wastes the entire right
 * half of the panel; it becomes two columns instead. Neither orientation
 * scrolls -- a glanceable panel that hides half its numbers is not glanceable.
 */
@Composable
private fun PageFrame(
    landscape: Boolean,
    primary: @Composable () -> Unit,
    secondary: @Composable () -> Unit,
) {
    if (landscape) {
        Row(
            Modifier.fillMaxSize().padding(vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(0.56f)) { primary() }
            Spacer(Modifier.width(22.dp))
            Column(
                Modifier.weight(0.44f),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) { secondary() }
        }
    } else {
        Column(
            Modifier.fillMaxSize().padding(vertical = 18.dp),
            verticalArrangement = Arrangement.Center,
        ) {
            primary()
            Spacer(Modifier.height(30.dp))
            secondary()
        }
    }
}

/** Stats as rows rather than a cramped side-by-side, for the narrow column. */
@Composable
private fun StatList(pairs: List<Pair<String, String>>) {
    pairs.forEach { (label, value) ->
        Column {
            Text(value, color = VP.Text, fontSize = VP.StatSize, fontWeight = FontWeight.Bold)
            Text(label, color = VP.Muted, fontSize = VP.LabelSize)
        }
    }
}

@Composable
private fun PageHeader(who: String, scope: String, pet: Boolean = true) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        if (pet) {
            PetMark()
            Spacer(Modifier.width(10.dp))
        }
        Text(who, color = VP.Text, fontSize = 15.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.width(10.dp))
        Text(scope, color = VP.Muted, fontSize = VP.ScopeSize, maxLines = 1)
    }
}

@Composable
private fun Hero(
    value: String,
    suffix: String,
    accent: Color,
    landscape: Boolean,
    trailing: @Composable () -> Unit = {},
) {
    // An em dash set at the hero size is a solid bar the width of the screen,
    // which reads as a rendering fault rather than as "not known yet".
    val unknown = value == "—"
    val size = when {
        unknown -> 56.sp
        landscape -> 84.sp
        else -> VP.HeroSize
    }
    Row(verticalAlignment = Alignment.Bottom) {
        Text(
            value,
            color = if (unknown) VP.Muted else VP.Text,
            fontSize = size,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
        )
        Spacer(Modifier.width(6.dp))
        Text(
            suffix,
            color = accent,
            fontSize = if (landscape) 26.sp else 34.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = if (landscape) 14.dp else 22.dp),
        )
        Spacer(Modifier.width(18.dp))
        Box(Modifier.padding(bottom = if (landscape) 12.dp else 20.dp)) { trailing() }
    }
}

@Composable
private fun Bar(fraction: Float, accent: Color, breakEven: Boolean = false) {
    Box(
        Modifier
            .fillMaxWidth()
            .height(VP.BarHeight)
            .clip(RoundedCornerShape(percent = 50))
            .background(VP.Track),
    ) {
        Box(
            Modifier
                .fillMaxHeight()
                .fillMaxWidth(fraction.coerceIn(0f, 1f))
                .clip(RoundedCornerShape(percent = 50))
                .background(accent),
        )
        if (breakEven) {
            Box(
                Modifier
                    .align(Alignment.Center)
                    .width(3.dp)
                    .fillMaxHeight()
                    .background(VP.Text),
            )
        }
    }
}

/* ----------------------------------------------------------------- pages -- */

/**
 * Page one: the session window.
 *
 * The session is what actually stops you mid-task, so it gets the hero. The
 * week is the slower fact and rides underneath as a stat.
 */
@Composable
private fun SessionPage(state: PanelRepository.State, landscape: Boolean) {
    val session = state.tokens?.claudeSession
    val week = state.tokens?.claudeWeek
    // "Working" is the agent's own reported state, so the dance tracks what
    // Claude is really doing rather than merely that the link is up.
    val working = state.agents?.claude.orEmpty().any { it.state == "working" }
    PageFrame(
        landscape = landscape,
        primary = {
            PageHeader("CLAUDE", "SESSION", pet = false)
            Spacer(Modifier.height(if (landscape) 8.dp else 18.dp))
            Hero(pctText(session?.pct), "%", VP.Claude, landscape) {
                DancingPet(working = working, size = if (landscape) 68 else 92)
            }
            Spacer(Modifier.height(if (landscape) 10.dp else 20.dp))
            Bar(((session?.pct ?: 0.0) / 100.0).toFloat(), VP.Claude)
            Spacer(Modifier.height(12.dp))
            Text(
                "RESETS IN ${humanMinutes(session?.resetMin)}",
                color = VP.Meta,
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold,
            )
            val delta = session?.deltaPct
            Text(
                if (delta == null) "LAST HOUR —"
                else "LAST HOUR ${if (delta >= 0) "+" else ""}${String.format("%.0f", delta)}%",
                color = VP.Muted,
                fontSize = 13.sp,
            )
            if (session?.stale == true) {
                Text(
                    "LAST KNOWN GOOD",
                    color = VP.Warn,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                )
            }
        },
        secondary = {
            StatList(
                listOf(
                    "WEEK %" to pctText(week?.pct),
                    "WEEK RESETS" to humanMinutes(week?.resetMin),
                    "TOKENS TODAY" to (state.tokens?.let { compactNumber(it.dayTokens) } ?: "—"),
                )
            )
        },
    )
}

@Composable
private fun BurnRatePage(state: PanelRepository.State, landscape: Boolean) {
    val t = state.tokens
    val forecast = t?.claudeForecast
    // Each state says a different true thing. "Collecting" is not a number yet
    // and must never be rendered as one.
    val (hero, note) = when (forecast?.state) {
        ForecastState.EXHAUSTS -> "RUNS OUT" to
            "in ${humanMinutes(forecast.offsetMin)} at this pace"
        ForecastState.AT_RESET -> "${forecast.pctAtReset ?: "—"}%" to "projected at reset"
        ForecastState.COLLECTING -> "—" to "still collecting a baseline"
        else -> "—" to "no forecast available"
    }
    PageFrame(
        landscape = landscape,
        primary = {
            PageHeader("BURN RATE", "WEEKLY FORECAST")
            Spacer(Modifier.height(if (landscape) 10.dp else 22.dp))
            Text(
                hero,
                color = if (hero == "—") VP.Muted else VP.Text,
                fontSize = if (landscape) 40.sp else 52.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(note, color = VP.Muted, fontSize = 14.sp)
        },
        secondary = {
            StatList(
                listOf(
                    "PER HOUR" to (t?.let { compactNumber(it.dayTokensPerHour) } ?: "—"),
                    "TOKENS TODAY" to (t?.let { compactNumber(it.dayTokens) } ?: "—"),
                    "SESSIONS" to (t?.daySessions?.toString() ?: "—"),
                    "THIS MONTH" to (t?.let { compactNumber(it.monthTokens) } ?: "—"),
                )
            )
        },
    )
}

/**
 * Twenty weeks of daily peaks. A cell is one day: brightness is the peak
 * percentage, and a day that hit the cap gets the full accent. `-1` means no
 * data and stays visibly empty rather than reading as a quiet day, which is a
 * different fact entirely.
 */
@Composable
private fun TrackerPage(
    provider: TrackerProvider?,
    streakDays: Int?,
    landscape: Boolean,
) {
    val days = provider?.days.orEmpty()
    PageFrame(
        landscape = landscape,
        primary = {
            PageHeader("MAX TRACKER", provider?.planLabel ?: "CLAUDE")
            Spacer(Modifier.height(if (landscape) 10.dp else 22.dp))
            if (days.isEmpty()) {
                Text("No history yet.", color = VP.Muted, fontSize = 14.sp)
            } else {
                val weeks = days.size / 7
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(3.dp),
                ) {
                    repeat(weeks) { w ->
                        Column(
                            Modifier.weight(1f),
                            verticalArrangement = Arrangement.spacedBy(3.dp),
                        ) {
                            repeat(7) { d ->
                                val (pct, maxed) = days.getOrElse(w * 7 + d) { Pair(-1, -1) }
                                val colour = when {
                                    pct < 0 -> VP.Hairline
                                    maxed == 1 -> VP.Claude
                                    else -> VP.Claude.copy(alpha = 0.15f + 0.55f * (pct / 100f))
                                }
                                Box(
                                    Modifier
                                        .fillMaxWidth()
                                        .height(if (landscape) 10.dp else 14.dp)
                                        .clip(RoundedCornerShape(2.dp))
                                        .background(colour),
                                )
                            }
                        }
                    }
                }
            }
        },
        secondary = {
            StatList(
                listOf(
                    "AVG PEAK" to (provider?.avgPeakPct?.let { String.format("%.0f%%", it) } ?: "—"),
                    "MAX WEEKS" to (provider?.maxWeeks?.toString() ?: "—"),
                    "DAY STREAK" to (streakDays?.toString() ?: "—"),
                )
            )
        },
    )
}

@Composable
private fun GitHubPage(state: PanelRepository.State, landscape: Boolean) {
    val g = state.github
    PageFrame(
        landscape = landscape,
        primary = {
            PageHeader("GITHUB", g?.repo ?: "—", pet = false)
            Spacer(Modifier.height(if (landscape) 10.dp else 18.dp))
            if (g == null || !g.enabled) {
                Text("Monitoring is off.", color = VP.Muted, fontSize = 15.sp)
                Spacer(Modifier.height(6.dp))
                Text(
                    "Restart the tokenserver with --github-repo owner/name. " +
                        "Public counts need no login.",
                    color = VP.Muted,
                    fontSize = 12.sp,
                    lineHeight = 17.sp,
                )
            } else {
                Hero(g.stars?.toString() ?: "—", "★", VP.Warn, landscape)
            }
        },
        secondary = {
            if (g != null && g.enabled) {
                StatList(
                    listOf(
                        "FORKS" to (g.forks?.toString() ?: "—"),
                        "STATE" to if (g.stale) "STALE" else "FRESH",
                    )
                )
            }
        },
    )
}

/**
 * Did the month cost less on a subscription than it would have on the API?
 * Anything the service will not stand behind arrives as PARTIAL or
 * NO_PLAN_COST and is dashed here -- a made-up multiple is worse than none.
 */
@Composable
private fun ValuePage(state: PanelRepository.State, landscape: Boolean) {
    val v = state.tokens?.value
    val multiple = v?.multiple
    val verdict = when (v?.state) {
        ValueState.OK -> when {
            multiple == null -> "—"
            multiple >= 2.0 -> "PAYING FOR ITSELF"
            multiple >= 1.0 -> "AHEAD"
            else -> "BEHIND"
        }
        ValueState.NO_PLAN_COST -> "NO PLAN COST SET"
        ValueState.PARTIAL -> "TOO MANY UNPRICED TOKENS"
        else -> "—"
    }
    PageFrame(
        landscape = landscape,
        primary = {
            PageHeader("VALUE", "MONTH TO DATE", pet = false)
            Spacer(Modifier.height(10.dp))
            Text(verdict, color = VP.Label, fontSize = 14.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            Hero(multiple?.let { String.format("%.1f", it) } ?: "—", "×", VP.Ok, landscape)
            Spacer(Modifier.height(if (landscape) 10.dp else 20.dp))
            // Break-even sits at the halfway mark, so 2x fills the bar.
            Bar(((multiple ?: 0.0) / 2.0).toFloat(), VP.Ok, breakEven = true)
        },
        secondary = {
            StatList(
                listOf(
                    "LIST VALUE" to usd(v?.valueUsd),
                    "PLAN COST" to usd(v?.planUsd),
                )
            )
            if (v?.costConfigured == false && v.planUsd != null) {
                Text(
                    "Plan cost is a default. Pass --plan claude=200 to correct it.",
                    color = VP.Muted,
                    fontSize = 11.sp,
                    lineHeight = 15.sp,
                )
            }
        },
    )
}
