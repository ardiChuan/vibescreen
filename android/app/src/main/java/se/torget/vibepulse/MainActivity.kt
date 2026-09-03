package se.torget.vibepulse

import android.Manifest
import android.bluetooth.BluetoothManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.lifecycleScope
import se.torget.vibepulse.data.PanelRepository
import se.torget.vibepulse.net.BluetoothTransport
import se.torget.vibepulse.net.HttpTransport
import se.torget.vibepulse.ui.NeedsYou
import se.torget.vibepulse.ui.Panel
import se.torget.vibepulse.ui.Prefs
import se.torget.vibepulse.ui.SettingsScreen

/**
 * The shelf screen, on a phone.
 *
 * The whole app is one activity because the panel is one thing: a view that is
 * always showing, with an alert that takes it over when an agent needs you.
 * Navigation would only add a way to be on the wrong screen when that happens.
 */
class MainActivity : ComponentActivity() {

    private lateinit var repo: PanelRepository
    private lateinit var store: PrefsStore

    private val requestBluetooth =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { /* re-checked on use */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = PrefsStore(this)
        repo = PanelRepository(lifecycleScope)
        goFullScreen()

        setContent {
            var prefs by remember { mutableStateOf(store.load()) }
            var showSettings by remember { mutableStateOf(false) }
            var btStatus by remember { mutableStateOf("") }
            val state by repo.state.collectAsState()

            // Rebuild the transport whenever the connection settings change,
            // and never on every recomposition.
            LaunchedEffect(prefs.transport, prefs.httpBase, prefs.btAddress, prefs.btChannel) {
                repo.setTransport(buildTransport(prefs) { btStatus = it })
            }
            LaunchedEffect(prefs.keepAwake) {
                if (prefs.keepAwake) {
                    window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                } else {
                    window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                }
            }
            LaunchedEffect(Unit) { repo.start() }

            val pending = state.agents?.pending

            when {
                showSettings -> SettingsScreen(
                    prefs = prefs,
                    btStatus = btStatus,
                    onChange = { prefs = it; store.save(it) },
                    onClose = { showSettings = false },
                )
                // The notice outranks everything: a decision you did not see is
                // one the terminal ends up making for you. It is informational
                // only -- the answer is given at the terminal.
                pending != null -> NeedsYou(pending = pending)
                else -> Panel(state = state, onOpenSettings = { showSettings = true })
            }
        }
    }

    /**
     * Edge to edge, with the status and navigation bars hidden.
     *
     * A shelf panel showing a phone's clock, battery and notification icons is
     * a phone on a shelf; hiding them is what makes it read as an appliance.
     * The bars stay reachable by swiping from an edge, so nothing is trapped.
     */
    private fun goFullScreen() {
        WindowCompat.setDecorFitsSystemWindows(window, false)
        WindowInsetsControllerCompat(window, window.decorView).apply {
            hide(WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior =
                WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
    }

    /** Re-hide after a rotation or after the user swipes the bars back in. */
    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) goFullScreen()
    }

    private fun buildTransport(prefs: Prefs, status: (String) -> Unit) =
        if (prefs.transport == Prefs.TRANSPORT_BT) {
            if (!hasBluetoothPermission()) {
                askForBluetooth()
                status("Waiting for Bluetooth permission.")
                null
            } else if (prefs.btAddress.isBlank()) {
                status("Enter the computer's Bluetooth address.")
                null
            } else {
                status("Connecting on channel ${prefs.btChannel}…")
                val manager = getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
                BluetoothTransport(manager?.adapter, prefs.btAddress, prefs.btChannel)
            }
        } else {
            HttpTransport(prefs.httpBase.ifBlank { Prefs.DEFAULT_USB_BASE })
        }

    /**
     * Android 12 replaced the old blanket Bluetooth permissions with a runtime
     * one. The F3 may be on 11, 12 or 13, so both eras are handled rather than
     * assuming the version it happens to be running today.
     */
    private fun hasBluetoothPermission(): Boolean =
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) true
        else ContextCompat.checkSelfPermission(
            this, Manifest.permission.BLUETOOTH_CONNECT,
        ) == PackageManager.PERMISSION_GRANTED

    private fun askForBluetooth() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            requestBluetooth.launch(Manifest.permission.BLUETOOTH_CONNECT)
        }
    }

    override fun onDestroy() {
        repo.stop()
        super.onDestroy()
    }
}
