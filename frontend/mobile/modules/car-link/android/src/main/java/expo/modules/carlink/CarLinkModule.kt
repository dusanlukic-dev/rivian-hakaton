package expo.modules.carlink

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.BluetoothStatusCodes
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import android.util.Log
import expo.modules.kotlin.Promise
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import java.io.ByteArrayOutputStream
import java.util.ArrayDeque
import java.util.UUID

private const val TAG = "CarLink"
private val CCCD: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

/** Frame header (docs/BLUETOOTH.md): msg_id, index, count, each uint16 big-endian. */
private const val HEADER = 6
private const val WANTED_MTU = 517
/** One radio packet (251-byte LE data length): bigger writes need L2CAP segmentation, which Windows drivers handle badly. */
private const val MAX_FRAME = 244
private const val WRITE_RETRIES = 60 // x 25 ms: the stack may be busy right after a burst of notifications

/** One frame waiting to be written; all frames of a message share its promise, the last one settles it. */
private class PendingFrame(val bytes: ByteArray, val message: Promise, val last: Boolean)

/**
 * Bluetooth LE link to the car computer (docs/BLUETOOTH.md), as a message pipe: JS sends and receives whole JSON
 * messages. This module finds the car by its service UUID, connects, asks for a large MTU and a fast connection,
 * subscribes to `rx`, and cuts messages into frames both ways. Every GATT step runs on the main looper, one at a time
 * (Android allows a single outstanding GATT operation). JS checks `status()` (permissions granted, Bluetooth on)
 * before scanning or connecting; a revoked permission still only fails the call, it never crashes.
 */
@SuppressLint("MissingPermission")
class CarLinkModule : Module() {
  private val main = Handler(Looper.getMainLooper())
  private val context: Context
    get() = requireNotNull(appContext.reactContext) { "React context is gone" }

  private var scanCallback: ScanCallback? = null
  private var adapterReceiver: BroadcastReceiver? = null

  private var gatt: BluetoothGatt? = null
  private var rx: BluetoothGattCharacteristic? = null
  private var tx: BluetoothGattCharacteristic? = null
  private var serviceUuid: UUID? = null
  private var rxUuid: UUID? = null
  private var txUuid: UUID? = null
  private var mtu = 23
  private var ready = false
  private var connectPromise: Promise? = null

  private val writes = ArrayDeque<PendingFrame>()
  private var writing = false
  private var writeRetries = 0
  private var sendId = 0

  private var rxId = -1
  private var rxNext = 0
  private var rxCount = 0
  private val rxBuffer = ByteArrayOutputStream()

  override fun definition() = ModuleDefinition {
    Name("CarLink")

    Events("onDevice", "onState", "onMessage")

    /** "unsupported" | "no-permission" | "off" | "ready" */
    Function("status") { status() }

    Function("startScan") { service: String ->
      val uuid = UUID.fromString(service)
      main.post { startScan(uuid) }
    }

    Function("stopScan") { main.post { stopScan() } }

    AsyncFunction("connect") { deviceId: String, service: String, rxChar: String, txChar: String, promise: Promise ->
      val ids = Triple(UUID.fromString(service), UUID.fromString(rxChar), UUID.fromString(txChar))
      main.post { connect(deviceId, ids.first, ids.second, ids.third, promise) }
    }

    Function("disconnect") { main.post { teardown("closed by the app") } }

    AsyncFunction("send") { json: String, promise: Promise -> main.post { send(json, promise) } }

    OnCreate { main.post { watchAdapter() } }

    OnDestroy {
      main.post {
        stopScan()
        teardown("app closed")
        unwatchAdapter()
      }
    }
  }

  /**
   * Android doesn't always call a GATT client back when Bluetooth is switched off (seen on the A54, Android 16), so
   * the adapter's own broadcast ends the connection; "adapter-on" lets JS retry at once instead of on its next check.
   */
  private fun watchAdapter() {
    if (adapterReceiver != null) return
    val receiver =
      object : BroadcastReceiver() {
        override fun onReceive(c: Context, intent: Intent) {
          when (intent.getIntExtra(BluetoothAdapter.EXTRA_STATE, BluetoothAdapter.ERROR)) {
            BluetoothAdapter.STATE_TURNING_OFF, BluetoothAdapter.STATE_OFF ->
              main.post {
                stopScan()
                teardown("Bluetooth was turned off")
                emitState("adapter-off")
              }
            BluetoothAdapter.STATE_ON -> main.post { emitState("adapter-on") }
          }
        }
      }
    val filter = IntentFilter(BluetoothAdapter.ACTION_STATE_CHANGED)
    try {
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        context.registerReceiver(receiver, filter, Context.RECEIVER_EXPORTED) // a protected system broadcast
      } else {
        context.registerReceiver(receiver, filter)
      }
      adapterReceiver = receiver
    } catch (e: Exception) {
      Log.w(TAG, "can't watch the Bluetooth adapter", e)
    }
  }

  private fun unwatchAdapter() {
    val receiver = adapterReceiver ?: return
    adapterReceiver = null
    try {
      context.unregisterReceiver(receiver)
    } catch (_: Exception) {}
  }

  // ---- state ----------------------------------------------------------------------------------------------------

  private fun adapter(): BluetoothAdapter? =
    (context.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager)?.adapter

  private fun hasPermissions(): Boolean {
    val needed =
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        listOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
      } else {
        listOf(Manifest.permission.ACCESS_FINE_LOCATION)
      }
    return needed.all { context.checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED }
  }

  private fun status(): String {
    val adapter = adapter() ?: return "unsupported"
    if (!context.packageManager.hasSystemFeature(PackageManager.FEATURE_BLUETOOTH_LE)) return "unsupported"
    if (!hasPermissions()) return "no-permission"
    return if (adapter.isEnabled) "ready" else "off"
  }

  private fun emitState(state: String, reason: String? = null) {
    sendEvent("onState", mapOf("state" to state, "reason" to reason, "mtu" to mtu))
  }

  // ---- scanning -------------------------------------------------------------------------------------------------

  @SuppressLint("MissingPermission")
  private fun startScan(service: UUID) {
    stopScan()
    val scanner = adapter()?.bluetoothLeScanner
    if (scanner == null) {
      emitState("scan-failed", "Bluetooth is off")
      return
    }
    val callback =
      object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
          val device = result.device
          val name =
            result.scanRecord?.deviceName
              ?: try {
                device.name
              } catch (_: SecurityException) {
                null
              }
          sendEvent("onDevice", mapOf("id" to device.address, "name" to name, "rssi" to result.rssi))
        }

        override fun onScanFailed(errorCode: Int) {
          main.post {
            scanCallback = null
            emitState("scan-failed", "scan failed with code $errorCode")
          }
        }
      }
    val filters = listOf(ScanFilter.Builder().setServiceUuid(ParcelUuid(service)).build())
    val settings = ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build()
    try {
      scanner.startScan(filters, settings, callback)
      scanCallback = callback
    } catch (e: SecurityException) {
      emitState("scan-failed", "no Bluetooth permission")
    }
  }

  @SuppressLint("MissingPermission")
  private fun stopScan() {
    val callback = scanCallback ?: return
    scanCallback = null
    try {
      adapter()?.bluetoothLeScanner?.stopScan(callback)
    } catch (e: Exception) {
      Log.w(TAG, "stopScan", e)
    }
  }

  // ---- connection -----------------------------------------------------------------------------------------------

  @SuppressLint("MissingPermission")
  private fun connect(deviceId: String, service: UUID, rxChar: UUID, txChar: UUID, promise: Promise) {
    stopScan()
    teardown("new connection")
    val adapter = adapter()
    if (adapter == null || !adapter.isEnabled) {
      promise.reject("bluetooth_off", "Bluetooth is off", null)
      return
    }
    val device =
      try {
        adapter.getRemoteDevice(deviceId)
      } catch (e: IllegalArgumentException) {
        promise.reject("bad_device", "Not a Bluetooth address: $deviceId", e)
        return
      }
    serviceUuid = service
    rxUuid = rxChar
    txUuid = txChar
    mtu = 23
    ready = false
    resetRx()
    connectPromise = promise
    emitState("connecting")
    gatt =
      try {
        device.connectGatt(context, false, callback, BluetoothDevice.TRANSPORT_LE)
      } catch (e: SecurityException) {
        failConnect("no Bluetooth permission")
        null
      }
    if (gatt == null) failConnect("could not start the connection")
  }

  /** Closes the connection (if any), fails whatever waits on it, and tells JS once. */
  @SuppressLint("MissingPermission")
  private fun teardown(reason: String) {
    val current = gatt ?: return
    gatt = null
    try {
      current.disconnect()
    } catch (_: Exception) {}
    try {
      current.close()
    } catch (_: Exception) {}
    ready = false
    rx = null
    tx = null
    resetRx()
    failConnect(reason)
    while (writes.isNotEmpty()) {
      val frame = writes.poll() ?: break
      if (frame.last) frame.message.reject("disconnected", reason, null)
    }
    writing = false
    emitState("disconnected", reason)
  }

  private fun failConnect(message: String) {
    val promise = connectPromise ?: return
    connectPromise = null
    promise.reject("connect_failed", message, null)
  }

  private fun becomeReady() {
    ready = true
    val promise = connectPromise
    connectPromise = null
    promise?.resolve(mapOf("mtu" to mtu, "maxFrame" to mtu - 3))
    emitState("ready")
  }

  /** Android caches a device's GATT table; the car's table changes during development, so always read it fresh. */
  private fun refreshCache(g: BluetoothGatt) {
    try {
      g.javaClass.getMethod("refresh").invoke(g)
    } catch (e: Exception) {
      Log.w(TAG, "gatt.refresh() unavailable", e)
    }
  }

  @SuppressLint("MissingPermission")
  private fun discover(g: BluetoothGatt) {
    g.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)
    // Some stacks drop a discovery started in the same instant as an MTU/priority change.
    main.postDelayed({
      if (g == gatt && !g.discoverServices()) {
        failConnect("service discovery refused")
        teardown("service discovery refused")
      }
    }, 200)
  }

  @SuppressLint("MissingPermission")
  private fun subscribe(g: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
    if (!g.setCharacteristicNotification(characteristic, true)) {
      teardown("notifications refused")
      return
    }
    val cccd = characteristic.getDescriptor(CCCD)
    if (cccd == null) {
      becomeReady() // no CCCD: the stack delivers notifications without one
      return
    }
    val value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
    val started =
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        g.writeDescriptor(cccd, value) == BluetoothStatusCodes.SUCCESS
      } else {
        @Suppress("DEPRECATION")
        cccd.value = value
        @Suppress("DEPRECATION")
        g.writeDescriptor(cccd)
      }
    if (!started) teardown("subscribing refused")
  }

  private val callback =
    object : BluetoothGattCallback() {
      override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
        main.post {
          if (g != gatt) {
            if (newState == BluetoothProfile.STATE_DISCONNECTED) g.close()
            return@post
          }
          if (newState == BluetoothProfile.STATE_CONNECTED && status == BluetoothGatt.GATT_SUCCESS) {
            refreshCache(g)
            if (!g.requestMtu(WANTED_MTU)) discover(g)
          } else {
            teardown(if (status == BluetoothGatt.GATT_SUCCESS) "the car disconnected" else "connection lost, status $status")
          }
        }
      }

      override fun onMtuChanged(g: BluetoothGatt, newMtu: Int, status: Int) {
        main.post {
          if (g != gatt) return@post
          if (status == BluetoothGatt.GATT_SUCCESS) mtu = newMtu
          if (!ready) discover(g)
        }
      }

      override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
        main.post {
          if (g != gatt) return@post
          val service = if (status == BluetoothGatt.GATT_SUCCESS) g.getService(serviceUuid) else null
          val r = service?.getCharacteristic(rxUuid)
          val t = service?.getCharacteristic(txUuid)
          if (r == null || t == null) {
            teardown(if (service == null) "the car's Bluetooth service is missing" else "the car's characteristics are missing")
            return@post
          }
          rx = r
          tx = t
          subscribe(g, r)
        }
      }

      override fun onDescriptorWrite(g: BluetoothGatt, descriptor: BluetoothGattDescriptor, status: Int) {
        main.post {
          if (g != gatt || ready) return@post
          if (status == BluetoothGatt.GATT_SUCCESS) becomeReady() else teardown("subscribing failed, status $status")
        }
      }

      override fun onCharacteristicWrite(g: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) {
        main.post { if (g == gatt) onWriteDone(status) }
      }

      // Android 13+: the value comes with the callback.
      override fun onCharacteristicChanged(g: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray) {
        val copy = value.copyOf()
        main.post { if (g == gatt && characteristic.uuid == rxUuid) onFrame(copy) }
      }

      // Android 12 and older. On 13+ the new overload above is the one called.
      @Deprecated("Replaced by the overload with the value on Android 13")
      override fun onCharacteristicChanged(g: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) return
        @Suppress("DEPRECATION")
        val copy = characteristic.value?.copyOf() ?: return
        main.post { if (g == gatt && characteristic.uuid == rxUuid) onFrame(copy) }
      }
    }

  // ---- sending --------------------------------------------------------------------------------------------------

  private fun send(json: String, promise: Promise) {
    if (gatt == null || tx == null || !ready) {
      promise.reject("not_connected", "Not connected to the car", null)
      return
    }
    val payload = json.toByteArray(Charsets.UTF_8)
    val chunk = maxOf(1, minOf(mtu - 3, MAX_FRAME) - HEADER)
    val count = maxOf(1, (payload.size + chunk - 1) / chunk)
    if (count > 0xFFFF) {
      promise.reject("too_big", "Message too big for the car link", null)
      return
    }
    sendId = (sendId + 1) and 0xFFFF
    for (i in 0 until count) {
      val start = i * chunk
      val end = minOf(payload.size, start + chunk)
      val frame = ByteArray(HEADER + (end - start))
      putU16(frame, 0, sendId)
      putU16(frame, 2, i)
      putU16(frame, 4, count)
      System.arraycopy(payload, start, frame, HEADER, end - start)
      writes.add(PendingFrame(frame, promise, i == count - 1))
    }
    pump()
  }

  @SuppressLint("MissingPermission")
  private fun pump() {
    if (writing) return
    val g = gatt ?: return
    val t = tx ?: return
    val frame = writes.peek() ?: return
    val started =
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        g.writeCharacteristic(t, frame.bytes, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) == BluetoothStatusCodes.SUCCESS
      } else {
        @Suppress("DEPRECATION")
        t.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
        @Suppress("DEPRECATION")
        t.value = frame.bytes
        @Suppress("DEPRECATION")
        g.writeCharacteristic(t)
      }
    if (started) {
      writing = true
      writeRetries = 0
      return
    }
    if (++writeRetries > WRITE_RETRIES) {
      writeRetries = 0
      dropMessage(writes.peek()?.message, "the car link is busy")
      pump()
      return
    }
    main.postDelayed({ pump() }, 25)
  }

  private fun onWriteDone(status: Int) {
    writing = false
    val frame = writes.poll() ?: return
    if (status != BluetoothGatt.GATT_SUCCESS) {
      if (frame.last) frame.message.reject("write_failed", "write failed, status $status", null)
      else dropMessage(frame.message, "write failed, status $status")
    } else if (frame.last) {
      frame.message.resolve(null)
    }
    pump()
  }

  /** Removes the rest of one message's frames and fails it (the car drops the partial message on its side). */
  private fun dropMessage(message: Promise?, reason: String) {
    if (message == null) return
    while (writes.peek()?.message === message) {
      val frame = writes.poll() ?: break
      if (frame.last) frame.message.reject("write_failed", reason, null)
    }
  }

  // ---- receiving ------------------------------------------------------------------------------------------------

  private fun onFrame(frame: ByteArray) {
    if (frame.size < HEADER) return
    val id = u16(frame, 0)
    val index = u16(frame, 2)
    val count = u16(frame, 4)
    if (count == 0 || index >= count) {
      resetRx()
      return
    }
    if (index == 0) {
      rxId = id
      rxNext = 0
      rxCount = count
      rxBuffer.reset()
    } else if (id != rxId || index != rxNext || count != rxCount) {
      resetRx() // a frame went missing: this message is lost, the next one starts clean
      return
    }
    rxBuffer.write(frame, HEADER, frame.size - HEADER)
    rxNext = index + 1
    if (rxNext == rxCount) {
      val json = rxBuffer.toString("UTF-8")
      resetRx()
      sendEvent("onMessage", mapOf("json" to json))
    }
  }

  private fun resetRx() {
    rxId = -1
    rxNext = 0
    rxCount = 0
    rxBuffer.reset()
  }

  private fun u16(bytes: ByteArray, at: Int) = ((bytes[at].toInt() and 0xFF) shl 8) or (bytes[at + 1].toInt() and 0xFF)

  private fun putU16(bytes: ByteArray, at: Int, value: Int) {
    bytes[at] = (value shr 8).toByte()
    bytes[at + 1] = value.toByte()
  }
}
