package se.torget.vibepulse

import android.content.Context
import android.content.SharedPreferences
import se.torget.vibepulse.ui.Prefs

/**
 * Connection and display preferences.
 *
 * There is no secret here any more. The panel is read only: it holds no device
 * key, signs nothing, and cannot answer an agent, so ordinary private
 * SharedPreferences is the right store and the Keystore dependency is gone.
 */
class PrefsStore(context: Context) {

    private val prefs: SharedPreferences =
        context.getSharedPreferences("vibepulse", Context.MODE_PRIVATE)

    fun load(): Prefs = Prefs(
        transport = prefs.getString("transport", Prefs.TRANSPORT_USB) ?: Prefs.TRANSPORT_USB,
        httpBase = prefs.getString("httpBase", Prefs.DEFAULT_USB_BASE)
            ?: Prefs.DEFAULT_USB_BASE,
        btAddress = prefs.getString("btAddress", "").orEmpty(),
        btChannel = prefs.getInt("btChannel", 5),
        keepAwake = prefs.getBoolean("keepAwake", true),
    )

    fun save(p: Prefs) {
        prefs.edit()
            .putString("transport", p.transport)
            .putString("httpBase", p.httpBase)
            .putString("btAddress", p.btAddress)
            .putInt("btChannel", p.btChannel)
            .putBoolean("keepAwake", p.keepAwake)
            .apply()
    }
}
