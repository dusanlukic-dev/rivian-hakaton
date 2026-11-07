---
name: android-device
description: Drive the physical Android test phone (Galaxy A54) from this PC with adb and the new Android CLI. Covers connection and authorization, adb reverse port forwarding, launching the app and deep links, granting demo permissions, logcat, screenshots, UI layout trees and taps for visual verification, sleep and wake tests, screen mirroring, and wireless adb over the hotspot. Use whenever a task touches the phone or needs on-device verification.
---

# Android device workflow

- **adb** comes from SDK platform-tools. It's on PATH in new shells; the absolute path is `$LOCALAPPDATA/Android/Sdk/platform-tools/adb.exe`.
- **android** is Google's agent-oriented CLI: `$LOCALAPPDATA/Android/Sdk/cmdline-tools/latest/bin/android.exe`, on PATH in new shells.
- App package: `dev.hakaton.driveralert`. Test phone: Galaxy A54, serial `RZCW60AY39Y`. With more than one device attached, add `-s <serial>` / `--device=<serial>`.
- Binary output: **PowerShell 5.1 corrupts `>` redirection of binary data**. Use Git Bash, or let the tool write the file (`--output`, `adb pull`).

## 1. Connection check (always first)

```bash
adb devices -l
```
| state | fix |
|---|---|
| `device` | ready |
| `unauthorized` | Ask the user to **unlock the phone and tap Allow** on "Allow USB debugging?" (tick *Always allow from this computer*). No prompt? Replug the cable, or run `adb kill-server && adb start-server` |
| nothing listed | Cable/port problem, or Developer options → USB debugging is off. Check that Windows Device Manager shows "ADB Interface" (Samsung driver is installed on this PC) |
| `offline` | `adb reconnect`, or replug |

Device facts: `adb shell getprop ro.product.model`, `ro.build.version.release`, `ro.build.version.sdk`, `ro.product.cpu.abi`.

## 2. Port forwarding (phone `localhost` → laptop)

```bash
adb reverse tcp:8081 tcp:8081   # Metro (expo run:android does this itself)
adb reverse tcp:8000 tcp:8000   # backend → app can use ws://localhost:8000/api/v1/ws
adb reverse --list
```
These reset on replug or an adb restart. `npm run adb:reverse` in `frontend/mobile` sets both.

## 3. App lifecycle

```bash
adb shell monkey -p dev.hakaton.driveralert -c android.intent.category.LAUNCHER 1   # launch
adb shell am start -a android.intent.action.VIEW -d "driveralert://settings" dev.hakaton.driveralert  # deep link (expo-router path)
adb shell am force-stop dev.hakaton.driveralert
adb uninstall dev.hakaton.driveralert          # needed after a package rename or a signature change
adb install -r path/to/app.apk                 # or: android install path/to/app.apk (delta install)
adb shell pm clear dev.hakaton.driveralert     # wipe data, including notification channels (channels are immutable otherwise)
```

## 4. Look at the screen (visual verification)

```bash
android screen capture --output=<scratchpad>/shot.png              # then Read the PNG
android screen capture --annotate --output=<scratchpad>/shot.png   # numbered boxes, usable with `android screen resolve`
android layout --pretty --output=<scratchpad>/layout.json          # accessibility tree JSON (text, class, bounds, clickable)
android input tap "text=Connect"                                   # tap by selector (key=value pairs, comma separated)
android input text "10.190.62.27:8000" "clz=EditText" --submit    # <string> <selector>: replaces the field's text, then Enter
android input key back|home|power|enter
android device hub                                                 # live mirror window, handy on the projector during the pitch
```
Fallbacks: `adb shell screencap -p /sdcard/s.png && adb pull /sdcard/s.png <local>`, and `adb shell input tap X Y`.

Gotchas (2026-11-07):
- `android input tap "text=Log in"` "clicks" the Text node, which doesn't fire a React Native Pressable. Take the `center` of the
  node from `android layout` and use `adb shell input tap X Y` (real pixels, 1080×2340 on the A54).
- `adb shell input keyevent KEYCODE_ENTER` is a hardware Enter, not the keyboard's action key: focus moves but the soft keyboard
  closes. To test Next/Go/Done, tap the key on the on-screen keyboard (bottom-right, about `986 2126` on the A54).
- The dev client's floating gear button sits over the right edge mid-screen (about `970 1190`) and swallows taps there.
- To catch flashes on cold start: `MSYS_NO_PATHCONV=1 adb shell screenrecord --time-limit 10 --size 540x1170 /sdcard/c.mp4` while
  launching, `adb pull`, then `ffmpeg -i c.mp4 -vf "fps=5,scale=150:-1,tile=10x6" -frames:v 1 montage.png` (ffmpeg is on PATH).
  In Git Bash, `/sdcard/...` needs `MSYS_NO_PATHCONV=1` or it turns into `C:/Program Files/Git/sdcard/...`.

## 5. Logs

```bash
adb logcat -c                                                    # clear
adb logcat -v time ReactNativeJS:V ReactNative:V AndroidRuntime:E *:S   # JS console + crashes
adb logcat -b crash -d                                           # last native crash
adb logcat --pid=$(adb shell pidof dev.hakaton.driveralert)      # everything from the app (Git Bash)
adb shell dumpsys notification --noredact | grep -A3 driveralert # posted notifications and channels
```

## 6. Sleep / wake / lock testing (the "wake from sleep" feature)

```bash
adb shell input keyevent KEYCODE_SLEEP     # screen off (and locks if a lock is set)
adb shell input keyevent KEYCODE_WAKEUP
adb shell dumpsys power | grep -E "mWakefulness=|mHoldingDisplaySuspendBlocker"
```
Test: start Drive mode → screen off → trigger a critical alert from the mock/sim → screenshot. The alert UI should be over the lock screen.

## 7. Demo-phone prep (permissions + special access)

The command block is in `.claude/knowledge/android-alerting.md` § Permissions: `pm grant` for notifications, location and camera,
`appops` for overlay and full-screen intent, DND access, and the battery whitelist. Then on the phone: Settings → Apps → Safety Reviewer → Battery → **Unrestricted**.

## 8. Wireless adb (no cable), when the phone hosts the hotspot

Android's "Wireless debugging" needs the phone to be a Wi-Fi *client*, so it usually doesn't work while hosting a hotspot. Use TCP mode instead:
```bash
adb tcpip 5555                      # while still on USB
# phone's IP on its own hotspot = laptop's "Default Gateway" in `ipconfig` (Wi-Fi adapter)
adb connect <gateway-ip>:5555
adb devices                         # shows <ip>:5555 device
```
This resets on reboot. Go back to USB mode with `adb usb`.
