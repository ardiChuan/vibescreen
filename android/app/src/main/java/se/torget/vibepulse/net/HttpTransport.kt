package se.torget.vibepulse.net

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.BufferedReader
import java.net.HttpURLConnection
import java.net.URL

/**
 * The USB path, and the LAN path, which are the same code.
 *
 * `adb reverse tcp:8737 tcp:8737` makes the computer's tokenserver appear on
 * the phone's own loopback, so the base URL is `http://127.0.0.1:8737` and no
 * WiFi, pairing or bridge is involved. Point [base] at a LAN address instead
 * and the identical class talks to the identical endpoints.
 *
 * Loopback is also a browser-grade "secure origin", which is why the USB route
 * is the primary one: it is the only transport where the phone is treated as
 * local by the platform rather than as a remote network client.
 */
class HttpTransport(private val base: String) : Transport {

    override val label: String =
        if (base.contains("127.0.0.1") || base.contains("localhost")) "USB" else "LAN"

    override suspend fun request(method: String, path: String, body: String?): Transport.Response =
        withContext(Dispatchers.IO) {
            var conn: HttpURLConnection? = null
            try {
                conn = (URL(base.trimEnd('/') + path).openConnection() as HttpURLConnection).apply {
                    requestMethod = method
                    // The panel polls once a second. A socket that hangs longer
                    // than the poll interval would stack requests, so both
                    // timeouts stay under it deliberately.
                    connectTimeout = 800
                    readTimeout = 900
                    setRequestProperty("Accept", "application/json")
                    if (body != null) {
                        doOutput = true
                        setRequestProperty("Content-Type", "application/json")
                        outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                    }
                }
                val status = conn.responseCode
                // A 409 from /api/interaction carries the refusal reason in its
                // body and the UI must show it, so error bodies are read too
                // rather than collapsed into a generic failure.
                val stream = if (status in 200..299) conn.inputStream else conn.errorStream
                val text = stream?.bufferedReader()?.use(BufferedReader::readText).orEmpty()
                Transport.Response.Success(status, text)
            } catch (e: Exception) {
                Transport.Response.Failure(e.message ?: e.javaClass.simpleName)
            } finally {
                conn?.disconnect()
            }
        }
}
