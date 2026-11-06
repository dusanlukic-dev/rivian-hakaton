---
name: mobile-dev
description: Build, run and debug the Expo SDK 58 / React Native 0.88 phone app in frontend/mobile on the physical Android phone. Covers when a rebuild is needed versus hot reload, prebuild (CNG), the Gradle/JDK toolchain on this PC, release APK builds, lint and typecheck, and common build errors. Use for any task that runs, builds or packages the mobile app.
---

# Mobile dev workflow (`frontend/mobile`)

Run everything from `frontend/mobile/`. Check the phone first with the `android-device` skill (`adb devices` must show `device`).

## Decide: hot reload or rebuild?

| you changed | do |
|---|---|
| `.ts/.tsx` under `src/`, JS-only packages | nothing. Metro hot-reloads (`npm start` must be running) |
| `app.json` (plugins, permissions, name, icons), `plugins/*.js`, `assets/sounds/*` used by notification channels | `npm run prebuild` → `npm run android` |
| added/removed a package with native code (`npx expo install …`) | `npm run prebuild` → `npm run android` |
| things look stale or weird after native changes | `npm run prebuild:clean` → `npm run android` |

## Commands

```bash
npm start                 # Metro dev server for the already-installed dev build (press `a` to open it on the phone)
npm run android           # = expo run:android: Gradle debug build, install, adb reverse 8081, start Metro. First build ~10–20 min, then ~1–3 min
npm run android:release   # release variant (JS bundled inside, debug-signed). This is what the demo phone should run
npm run prebuild          # regenerate android/ from app.json + plugins (android/ is gitignored, never hand-edit it)
npm run adb:reverse       # phone localhost:8081/8000 → laptop
npm run lint && npm run typecheck   # required before calling a task done
npm run doctor            # expo-doctor: dependency/config sanity
npx expo install --fix    # align package versions with SDK 58
```

Metro over Wi-Fi instead of USB: phone and laptop on the same network, `npm start`, then in the dev client enter
`http://<laptop-ip>:8081`. The Windows firewall must allow 8081 (`.claude/knowledge/networking.md`).

## Toolchain on this PC (details: `.claude/knowledge/environment.md`)

- `ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk` (user env var). Shells opened before setup lack it, so set it in-session:
  PowerShell `$env:ANDROID_HOME="$env:LOCALAPPDATA\Android\Sdk"`, bash `export ANDROID_HOME="$LOCALAPPDATA/Android/Sdk"`.
- Gradle 9.4.1 runs on the global **JDK 25** (`JAVA_HOME`). RN's Gradle plugin needs a **JDK 17 toolchain**, which comes from
  `~/.jdks/jdk-17.0.21+9`, registered in `~/.gradle/gradle.properties` (`org.gradle.java.installations.paths`).
  If a build fails with a Java/Kotlin version error, run the Gradle daemon on JDK 17 too:
  `$env:JAVA_HOME="$HOME\.jdks\jdk-17.0.21+9"; npm run android`.
- SDK packages: platform 37.0, build-tools 37.0.0, NDK 27.1.12297006, CMake 3.30.5. Install with `android sdk install <pkg/path>`
  (`sdkmanager` is deprecated). Only `arm64-v8a` is built (D12).

## Release APK for the demo phone / other phones

```bash
npm run android:release        # builds + installs on the connected phone
# APK: android/app/build/outputs/apk/release/app-release.apk. Share it and install with `adb install -r`, or sideload
```
It's debug-signed, which is fine for sideloading. Updating an installed app needs the same signature, so `adb uninstall` first if it differs.

## Common errors

| symptom | fix |
|---|---|
| `SDK location not found` | set `ANDROID_HOME` (above) or create `android/local.properties` with `sdk.dir=C:\\Users\\…\\Android\\Sdk` |
| `No matching toolchains found … languageVersion=17` | JDK 17 isn't registered. Check `~/.gradle/gradle.properties` |
| `Unsupported class file major version 69` / Kotlin can't parse Java version | run with `JAVA_HOME` = JDK 17 (above) |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | signature mismatch: `adb uninstall dev.hakaton.driveralert` |
| App opens, red screen "Unable to load script" | Metro not running or not reachable: `npm start`, then `npm run adb:reverse` |
| Native module "null"/"not found" at runtime | the installed dev build is older than package.json. Rebuild with `npm run android` |
| Notification sound/importance won't change | channels are immutable. Use a new channel id or `adb shell pm clear dev.hakaton.driveralert` |
| Windows path-length errors in CMake/Ninja | keep the repo path short. Enable long paths (admin): `git config --system core.longpaths true` + the registry `LongPathsEnabled=1` |
