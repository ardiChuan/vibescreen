package se.torget.vibepulse.ui

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * The panel's own palette, mirrored from
 * `components/app_tokens/vibepulse_layout.generated.h`.
 *
 * The background is true black rather than a dark grey on purpose. The round
 * panel is an OLED and so is the F3, so black pixels are off pixels: it is the
 * difference between a screen that can sit lit on a shelf all day and one that
 * cooks its own battery. It is also why the provider accents are the only
 * saturated colour on screen.
 */
object VP {
    val Background = Color(0xFF000000)
    val Text = Color(0xFFFFFFFF)
    val Muted = Color(0xFF9298A2)
    val Track = Color(0xFF303238)
    val Hairline = Color(0xFF202328)
    val Claude = Color(0xFFD97757)

    val Label = Color(0xFFB2B7C0)
    val Meta = Color(0xFFD9DCE2)
    val ClaudeMuted = Color(0xFF8A4F42)
    val Dot = Color(0xFF41444A)
    val DotOn = Color(0xFFCDD2DA)

    val Ok = Color(0xFF6FBF8B)
    val Warn = Color(0xFFE0B341)
    val Bad = Color(0xFFCF5B5B)

    /** The round panel gives the percentage 164 of 480 px. Portrait can be
     *  bolder still, but not so bold that a three-digit value wraps. */
    val HeroSize = 132.sp
    val ScopeSize = 13.sp
    val LabelSize = 12.sp
    val StatSize = 22.sp

    val Gutter = 24.dp
    val BarHeight = 22.dp
}

/** 219108100 -> "219.1M". A raw token count is unreadable at a glance. */
fun compactNumber(value: Double): String {
    val v = kotlin.math.abs(value)
    return when {
        v >= 1_000_000_000 -> String.format("%.1fB", value / 1_000_000_000)
        v >= 1_000_000 -> String.format("%.1fM", value / 1_000_000)
        v >= 1_000 -> String.format("%.1fk", value / 1_000)
        else -> String.format("%.0f", value)
    }
}

/** Minutes to the shape the panel uses: "4h 16m", "2d 6h". */
fun humanMinutes(min: Int?): String {
    if (min == null || min < 0) return "—"
    val days = min / 1440
    val hours = (min % 1440) / 60
    val mins = min % 60
    return when {
        days > 0 -> "${days}d ${hours}h"
        hours > 0 -> "${hours}h ${mins}m"
        else -> "${mins}m"
    }
}

/** A percentage, or a dash. Never 0 for "unknown". */
fun pctText(pct: Double?): String = pct?.let { String.format("%.0f", it) } ?: "—"

fun usd(value: Double?): String = value?.let { String.format("$%,.0f", it) } ?: "—"
