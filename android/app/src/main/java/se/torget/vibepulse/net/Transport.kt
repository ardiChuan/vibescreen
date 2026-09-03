package se.torget.vibepulse.net

/**
 * The one interface the rest of the app talks to.
 *
 * The ESP32 panel is an HTTP client. Over USB (`adb reverse`) the phone can be
 * exactly that, so [HttpTransport] is a thin wrapper and the tokenserver needs
 * no changes at all. Over Bluetooth there is no HTTP at all -- RFCOMM is a
 * byte stream -- so [BluetoothTransport] carries the same request/response
 * pair in a framed envelope and a bridge on the computer turns it back into
 * the identical HTTP call.
 *
 * Everything above this interface (parsing, signing, UI) is therefore written
 * once and is transport-blind. That is the whole point of it existing: without
 * it, adding Bluetooth after the fact means rewriting the app rather than
 * plugging in a second implementation.
 */
interface Transport {

    /** Human-readable name for the status line: "USB", "Bluetooth". */
    val label: String

    /**
     * One request. [path] is a tokenserver path such as `/api/tokens`.
     * [body] is a JSON string for POST, or null for GET.
     *
     * Implementations must not throw for ordinary connectivity problems --
     * a dead cable or an unpaired phone is a normal state for a panel, not an
     * exception. They return [Response.Failure] instead, so the UI can keep
     * showing last-known-good values the way the firmware does.
     */
    suspend fun request(method: String, path: String, body: String? = null): Response

    /** Cheap check used to pick a transport at startup and after a drop. */
    suspend fun probe(): Boolean =
        request("GET", "/").let { it is Response.Success }

    fun close() {}

    sealed interface Response {
        data class Success(val status: Int, val body: String) : Response
        data class Failure(val reason: String) : Response
    }
}
