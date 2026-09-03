package se.torget.vibepulse.ui

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import se.torget.vibepulse.data.Pending

/**
 * The waiting-decision notice. Informational only.
 *
 * This panel does not answer anything: it holds no device key and never POSTs.
 * The notice exists because "an agent has been sitting there for four minutes"
 * is the single most useful thing a shelf screen can tell you -- but the answer
 * itself is given at the terminal.
 *
 * The countdown maps to the real fallback deadline (`hold_ms`), so it means
 * something specific: when it runs out, the terminal prompts instead.
 */
@Composable
fun NeedsYou(pending: Pending) {
    val remaining = pending.expiresInMs.coerceAtLeast(0)
    val fraction = if (pending.holdMs > 0) {
        (remaining.toFloat() / pending.holdMs.toFloat()).coerceIn(0f, 1f)
    } else 0f
    val animated by animateFloatAsState(fraction, label = "countdown")

    Column(
        Modifier
            .fillMaxSize()
            .background(VP.Background)
            .padding(horizontal = 22.dp, vertical = 18.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text("NEEDS YOU", color = VP.Claude, fontSize = 34.sp, fontWeight = FontWeight.Black)
        Spacer(Modifier.height(4.dp))
        Text(
            listOfNotNull(pending.project, pending.kind.uppercase()).joinToString("  ·  "),
            color = VP.Muted,
            fontSize = 12.sp,
        )

        Spacer(Modifier.height(10.dp))
        Box(
            Modifier
                .fillMaxWidth()
                .height(5.dp)
                .clip(RoundedCornerShape(percent = 50))
                .background(VP.Track),
        ) {
            Box(
                Modifier
                    .fillMaxWidth(animated)
                    .height(5.dp)
                    .clip(RoundedCornerShape(percent = 50))
                    .background(if (fraction < 0.25f) VP.Bad else VP.Claude),
            )
        }
        Spacer(Modifier.height(4.dp))
        Text(
            "${remaining / 1000}s before this falls back to the terminal",
            color = VP.Muted,
            fontSize = 11.sp,
        )

        Spacer(Modifier.height(24.dp))
        pending.tool?.let {
            Text(it.uppercase(), color = VP.Label, fontSize = 12.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
        }
        pending.title?.let {
            Text(it, color = VP.Text, fontSize = 24.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(10.dp))
        }
        pending.prompt?.let {
            Text(it, color = VP.Text, fontSize = 19.sp, lineHeight = 26.sp)
            Spacer(Modifier.height(10.dp))
        }
        pending.subtitle?.let {
            Text(it, color = VP.Muted, fontSize = 14.sp, lineHeight = 20.sp)
        }
        // The stripped case: the server deliberately sent no text. Say so rather
        // than showing an empty screen.
        if (pending.title == null && pending.prompt == null && pending.tool == null) {
            Text(
                "SOMETHING IS WAITING",
                color = VP.Text,
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold,
            )
        }

        Spacer(Modifier.height(22.dp))
        Text(
            "Answer this at the terminal.",
            color = VP.Warn,
            fontSize = 13.sp,
            fontWeight = FontWeight.Bold,
        )
    }
}
