package expo.modules.systemaccess

import android.app.NotificationManager
import android.content.Context
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

/**
 * Special-access states that no installed library reports. Today only one: whether the user let this app
 * override Do Not Disturb (Android's "Do not disturb permission", i.e. notification policy access).
 */
class SystemAccessModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("SystemAccess")

    Function("isDndAccessGranted") {
      val manager = appContext.reactContext?.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager
      manager?.isNotificationPolicyAccessGranted == true
    }
  }
}
