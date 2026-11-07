package expo.modules.systemaccess

import android.Manifest
import android.app.Activity
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.telephony.SmsManager
import expo.modules.kotlin.Promise
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

/**
 * Android access that no installed library covers:
 * - whether the user let this app override Do Not Disturb (notification policy access);
 * - texting the emergency contact without opening the SMS app (SmsManager, needs SEND_SMS), so the message goes out
 *   even when the driver can't tap anything and the app is in the background.
 */
class SystemAccessModule : Module() {
  private val main = Handler(Looper.getMainLooper())
  private var nextId = 0

  private val context: Context?
    get() = appContext.reactContext?.applicationContext

  override fun definition() = ModuleDefinition {
    Name("SystemAccess")

    Function("isDndAccessGranted") {
      val manager = context?.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager
      manager?.isNotificationPolicyAccessGranted == true
    }

    // Resolves "sent" once the network took every part, "failed" (no signal, no SIM, airplane mode...),
    // "timeout" (no answer in 30 s), "no_permission" or "unavailable" (no context, or no SMS on this device).
    // Everything runs on the main thread (the "sent" broadcasts arrive there too), so the counters need no locking.
    AsyncFunction("sendSms") { phone: String, body: String, promise: Promise ->
      main.post { sendSms(phone, body, promise) }
    }
  }

  private fun sendSms(phone: String, body: String, promise: Promise) {
    val ctx = context ?: return promise.resolve("unavailable")
    if (ctx.checkSelfPermission(Manifest.permission.SEND_SMS) != PackageManager.PERMISSION_GRANTED) {
      return promise.resolve("no_permission")
    }
    val sms: SmsManager = try {
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        ctx.getSystemService(SmsManager::class.java) ?: return promise.resolve("unavailable")
      } else {
        @Suppress("DEPRECATION")
        SmsManager.getDefault()
      }
    } catch (e: Exception) {
      return promise.resolve("unavailable")
    }

    nextId += 1
    val action = "${ctx.packageName}.SMS_SENT.$nextId"
    val parts = sms.divideMessage(body)
    var pending = parts.size
    var failed = false
    var done = false
    lateinit var receiver: BroadcastReceiver

    fun finish(result: String) {
      if (done) return
      done = true
      main.removeCallbacksAndMessages(action)
      try {
        ctx.unregisterReceiver(receiver)
      } catch (e: Exception) {
        // already unregistered
      }
      promise.resolve(result)
    }

    // One "sent" broadcast per part.
    receiver = object : BroadcastReceiver() {
      override fun onReceive(c: Context, intent: Intent) {
        if (resultCode != Activity.RESULT_OK) failed = true
        pending -= 1
        if (pending <= 0) finish(if (failed) "failed" else "sent")
      }
    }
    val filter = IntentFilter(action)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
      ctx.registerReceiver(receiver, filter, Context.RECEIVER_NOT_EXPORTED)
    } else {
      @Suppress("UnspecifiedRegisterReceiverFlag")
      ctx.registerReceiver(receiver, filter)
    }
    main.postAtTime({ finish("timeout") }, action, SystemClock.uptimeMillis() + 30_000)

    // The PendingIntents are ours, so their broadcast reaches the not-exported receiver above.
    val sent = ArrayList<PendingIntent>(parts.size)
    for (i in parts.indices) {
      val intent = Intent(action).setPackage(ctx.packageName)
      sent.add(PendingIntent.getBroadcast(ctx, i, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_ONE_SHOT))
    }
    try {
      if (parts.size == 1) {
        sms.sendTextMessage(phone, null, body, sent[0], null)
      } else {
        sms.sendMultipartTextMessage(phone, null, parts, sent, null)
      }
    } catch (e: Exception) {
      finish("failed")
    }
  }
}
