package se.torget.vibepulse.net

import java.io.EOFException
import java.io.InputStream
import java.io.OutputStream
import org.json.JSONObject

/**
 * The Bluetooth wire format, shared with `tools/btbridge/bt_bridge.py`.
 *
 * RFCOMM is a byte stream, not a message channel: one `read()` can return half
 * a payload or two payloads stuck together. `/api/agent-status` runs to about
 * 3.5 KB, so "read until nothing more arrives" truncates it intermittently --
 * and a truncated JSON body looks exactly like a parse bug, which is an
 * expensive thing to debug. Every message is therefore length-prefixed.
 *
 *   request : [4-byte big-endian length][UTF-8 {"method","path","body"}]
 *   response: [4-byte big-endian length][UTF-8 {"status","body"}]
 *
 * The bridge turns each request into the identical HTTP call the USB transport
 * would have made, so both transports hit the same tokenserver routes with the
 * same bodies and the same signatures.
 */
object Frames {

    /** Refuse anything larger than this rather than allocating on a bad length. */
    const val MAX_FRAME = 1 shl 20

    fun encode(payload: String): ByteArray {
        val body = payload.toByteArray(Charsets.UTF_8)
        val out = ByteArray(4 + body.size)
        out[0] = (body.size ushr 24).toByte()
        out[1] = (body.size ushr 16).toByte()
        out[2] = (body.size ushr 8).toByte()
        out[3] = body.size.toByte()
        body.copyInto(out, 4)
        return out
    }

    fun write(stream: OutputStream, payload: String) {
        stream.write(encode(payload))
        stream.flush()
    }

    /** Blocking read of exactly one frame. */
    fun read(stream: InputStream): String {
        val header = readFully(stream, 4)
        val len = ((header[0].toInt() and 0xff) shl 24) or
            ((header[1].toInt() and 0xff) shl 16) or
            ((header[2].toInt() and 0xff) shl 8) or
            (header[3].toInt() and 0xff)
        require(len in 0..MAX_FRAME) { "bad frame length $len" }
        return String(readFully(stream, len), Charsets.UTF_8)
    }

    private fun readFully(stream: InputStream, n: Int): ByteArray {
        val buf = ByteArray(n)
        var read = 0
        while (read < n) {
            // The short-read case is the whole reason this helper exists.
            val got = stream.read(buf, read, n - read)
            if (got < 0) throw EOFException("stream closed after $read of $n bytes")
            read += got
        }
        return buf
    }

    fun requestJson(method: String, path: String, body: String?): String =
        JSONObject().apply {
            put("method", method)
            put("path", path)
            if (body != null) put("body", body)
        }.toString()
}
