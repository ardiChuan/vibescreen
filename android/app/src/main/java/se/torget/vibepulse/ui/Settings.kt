package se.torget.vibepulse.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** What the user can change, and what the app remembers between launches. */
data class Prefs(
    val transport: String = TRANSPORT_USB,
    val httpBase: String = DEFAULT_USB_BASE,
    val btAddress: String = "",
    val btChannel: Int = 5,
    val keepAwake: Boolean = true,
) {
    companion object {
        const val TRANSPORT_USB = "usb"
        const val TRANSPORT_BT = "bluetooth"
        /** `adb reverse` puts the computer's tokenserver on this phone's loopback. */
        const val DEFAULT_USB_BASE = "http://127.0.0.1:8737"
    }
}

@Composable
fun SettingsScreen(
    prefs: Prefs,
    btStatus: String,
    onChange: (Prefs) -> Unit,
    onClose: () -> Unit,
) {
    Column(
        Modifier
            .fillMaxSize()
            .background(VP.Background)
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Settings", color = VP.Text, fontSize = 24.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.weight(1f))
            Text(
                "Done",
                color = VP.Claude,
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(8.dp).clickableNoRipple(onClose),
            )
        }

        Section("Connection")
        CheckRow(
            "USB (adb reverse) — recommended",
            prefs.transport == Prefs.TRANSPORT_USB,
        ) { if (it) onChange(prefs.copy(transport = Prefs.TRANSPORT_USB)) }
        CheckRow(
            "Bluetooth (needs the bridge running)",
            prefs.transport == Prefs.TRANSPORT_BT,
        ) { if (it) onChange(prefs.copy(transport = Prefs.TRANSPORT_BT)) }

        if (prefs.transport == Prefs.TRANSPORT_USB) {
            Hint(
                "Run this on the computer with the phone plugged in:\n" +
                    "adb reverse tcp:8737 tcp:8737\n\n" +
                    "That makes the tokenserver reachable on this phone's own " +
                    "loopback, so no WiFi and no pairing are involved. Change the " +
                    "address below only if you are reaching a LAN host instead."
            )
            Field(
                value = prefs.httpBase,
                onValueChange = { onChange(prefs.copy(httpBase = it.trim())) },
                placeholder = Prefs.DEFAULT_USB_BASE,
            )
        } else {
            Hint(
                "Pair this phone with the computer first, then start the bridge:\n" +
                    "python tools/btbridge/bt_bridge.py\n\n" +
                    "The bridge prints the RFCOMM channel it managed to bind. Enter " +
                    "that number and the computer's Bluetooth address here."
            )
            Field(
                value = prefs.btAddress,
                onValueChange = { onChange(prefs.copy(btAddress = it.trim().uppercase())) },
                placeholder = "AA:BB:CC:DD:EE:FF",
            )
            Field(
                value = prefs.btChannel.toString(),
                onValueChange = {
                    val n = it.filter(Char::isDigit).take(2).toIntOrNull()
                    if (n != null) onChange(prefs.copy(btChannel = n))
                },
                placeholder = "channel",
                numeric = true,
            )
            Text(btStatus, color = VP.Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 6.dp))
        }

        Section("Display")
        CheckRow("Keep the screen on while the app is open", prefs.keepAwake) {
            onChange(prefs.copy(keepAwake = it))
        }
        Hint(
            "For a permanently-on shelf display, also plug the phone in and turn on " +
                "Developer options → Stay awake while charging."
        )

        Spacer(Modifier.height(40.dp))
    }
}

@Composable
private fun Section(title: String) {
    Spacer(Modifier.height(26.dp))
    Text(title.uppercase(), color = VP.Label, fontSize = 12.sp, fontWeight = FontWeight.Bold)
    Spacer(Modifier.height(6.dp))
}

@Composable
private fun Hint(text: String) {
    Text(text, color = VP.Muted, fontSize = 12.sp, lineHeight = 17.sp)
    Spacer(Modifier.height(8.dp))
}

@Composable
private fun Field(
    value: String,
    onValueChange: (String) -> Unit,
    placeholder: String,
    numeric: Boolean = false,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        placeholder = { Text(placeholder, color = VP.Muted, fontSize = 14.sp) },
        singleLine = true,
        keyboardOptions = KeyboardOptions(
            keyboardType = if (numeric) KeyboardType.Number else KeyboardType.Text,
        ),
        colors = TextFieldDefaults.colors(
            focusedContainerColor = Color(0xFF0C0E11),
            unfocusedContainerColor = Color(0xFF0C0E11),
            focusedTextColor = VP.Text,
            unfocusedTextColor = VP.Text,
            focusedIndicatorColor = VP.Claude,
            unfocusedIndicatorColor = VP.Hairline,
            cursorColor = VP.Claude,
        ),
        modifier = Modifier.fillMaxWidth(),
    )
    Spacer(Modifier.height(6.dp))
}

@Composable
private fun CheckRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Start,
    ) {
        Checkbox(
            checked = checked,
            onCheckedChange = onChange,
            colors = CheckboxDefaults.colors(
                checkedColor = VP.Claude,
                uncheckedColor = VP.Track,
                checkmarkColor = VP.Background,
            ),
        )
        Text(label, color = VP.Text, fontSize = 14.sp)
    }
}
