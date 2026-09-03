package se.torget.vibepulse.net

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException

/**
 * The cable-free path: classic Bluetooth RFCOMM to a bridge on the computer.
 *
 * Why a fixed channel instead of a UUID lookup: the normal Android call,
 * `createRfcommSocketToServiceRecord(uuid)`, asks the *computer* to advertise
 * an SDP record naming its channel. Python's socket module on Windows can bind
 * and listen on an RFCOMM channel but exposes no way to register that SDP
 * record, so the lookup has nothing to find. The reflective
 * `createRfcommSocket(channel)` connects to a channel number directly and
 * skips discovery entirely, which is what makes a pure-stdlib bridge possible.
 *
 * That reflection is a documented-by-community hack, not public API, and some
 * vendor stacks restrict it. It is therefore isolated here, reported honestly
 * through [Transport.Response.Failure], and never the app's only way in -- USB
 * remains the primary transport precisely because this one can be refused by
 * the platform.
 *
 * One request at a time: a single RFCOMM channel is one stream, and two
 * overlapping request/response pairs would interleave their frames.
 */
class BluetoothTransport(
    private val adapter: BluetoothAdapter?,
    private val deviceAddress: String,
    private val channel: Int,
) : Transport {

    override val label: String = "Bluetooth"

    private var socket: BluetoothSocket? = null
    private val lock = Mutex()

    @SuppressLint("MissingPermission")
    private fun connectLocked(): BluetoothSocket {
        socket?.let { if (it.isConnected) return it }
        close()

        val a = adapter ?: throw IOException("no Bluetooth adapter")
        if (!a.isEnabled) throw IOException("Bluetooth is off")

        val device: BluetoothDevice = a.getRemoteDevice(deviceAddress)
        // createRfcommSocket(int) is hidden API reached by reflection. The
        // public alternative needs an SDP record the Windows bridge cannot
        // publish, so this is the only route that reaches a stdlib bridge.
        val method = device.javaClass.getMethod("createRfcommSocket", Int::class.javaPrimitiveType)
        val sock = method.invoke(device, channel) as BluetoothSocket

        // Discovery and an in-flight connect fight over the radio.
        runCatching { a.cancelDiscovery() }
        sock.connect()
        socket = sock
        return sock
    }

    override suspend fun request(method: String, path: String, body: String?): Transport.Response =
        withContext(Dispatchers.IO) {
            lock.withLock {
                try {
                    val sock = connectLocked()
                    Frames.write(sock.outputStream, Frames.requestJson(method, path, body))
                    val reply = JSONObject(Frames.read(sock.inputStream))
                    Transport.Response.Success(
                        reply.optInt("status", 0),
                        reply.optString("body", ""),
                    )
                } catch (e: Exception) {
                    // A dropped link must not poison every later attempt, so the
                    // socket is torn down and the next call reconnects.
                    close()
                    Transport.Response.Failure(e.message ?: e.javaClass.simpleName)
                }
            }
        }

    override fun close() {
        runCatching { socket?.close() }
        socket = null
    }
}
