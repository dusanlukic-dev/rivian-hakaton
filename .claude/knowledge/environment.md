# Dev environment (Matija's laptop = the "car computer")

Recorded 2026-11-06. Update it when something changes. Other teammates' machines will differ; the repo itself is machine-independent.

## Toolchain

| tool | version | where / notes |
|---|---|---|
| Windows | 11 Pro (26300) | PowerShell 5.1 + Git Bash. PS 5.1 has no `&&`, and `>` corrupts binary output |
| Node / npm | 26.13.0 / 12.2.1 | nvm4w (`C:\nvm4w\nodejs`). **npm 12 blocks dependency install scripts** unless allowed (`npm install-scripts ls/approve`). Only `@parcel/watcher` was blocked (prebuilt binary, harmless). **Matija Vujić's backend laptop:** Node 26.13.0 / npm 11.20.0 (winget `OpenJS.NodeJS.LTS`, `C:\Program Files\nodejs`, upgraded from 22.11 on 2026-11-06). Node < 22.12 breaks the frontends: vite 8 / rolldown silently lose the native binding ("Cannot find native binding"), the Expo CLI wants ≥ 22.13, and npm 10 can't `npm ci` the mobile lock. Verified there with 26.13: clean `npm ci` in both apps, dashboard build, mobile typecheck + lint |
| git | 2.56 | identity "Matija Radović" <radovic1918@gmail.com>. SSH to GitHub works |
| Python | 3.15.2 (default `py`) + **3.13.17** | 3.13 was installed with `py install 3.13` (the Python install manager, per user, no admin). **The backend venv `backend/.venv` uses 3.13**: on 3.15, `fastapi[standard]` fails because PyYAML has no cp315 wheel (D16). Run the backend with `backend\.venv\Scripts\python.exe run.py` |
| Java (global) | Temurin **25** | `JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-25.0.5.8-hotspot\`, untouched |
| Java (Android toolchain) | Temurin **17.0.21+9**, portable | `C:\Users\matija\.jdks\jdk-17.0.21+9`, registered only as a Gradle toolchain candidate in `~/.gradle/gradle.properties` (`org.gradle.java.installations.paths`). Not on PATH |
| Android SDK | — | `C:\Users\matija\AppData\Local\Android\Sdk` (Android Studio's default location, so a later Studio install reuses it) |
| ├ cmdline-tools | 23.0.0 (`latest`) | ships the new **`android` CLI** (`android sdk install …`, `android screen capture`, `android layout`, `android input`, `android device hub`). `sdkmanager` is deprecated and delegates to it |
| ├ platform-tools | 37.0.1 | adb |
| ├ platforms | android-37.0 | compileSdk 37 |
| ├ build-tools | 37.0.0 | |
| ├ NDK | 27.1.12297006 | RN 0.88's version catalog |
| └ CMake | 3.30.5 (RN core) + 3.22.1 (auto-installed by AGP for libraries without a pinned version, e.g. react-native-screens, worklets) | **Both `bin/ninja.exe` were replaced with Ninja 1.13.2** (long-path aware; the bundled 1.10.2 broke the C++ build on our 70-char repo path). Originals kept as `ninja-1.10.2-original.exe`. Swap loop (Git Bash): `for B in "$LOCALAPPDATA"/Android/Sdk/cmake/*/bin; do cp /path/to/ninja-1.13.2.exe "$B/ninja.exe"; done` (ninja-win.zip from github.com/ninja-build/ninja/releases) |
| Windows long paths | `LongPathsEnabled=1` (was already set) | needed together with Ninja ≥ 1.12 |
| Expo / RN / React | SDK 58.0.23 / 0.88.1 / 19.3.0 | TypeScript 6.0, React Compiler on, New Architecture only, Hermes |
| Gradle / AGP / Kotlin | 9.4.1 / 9.2.1 / 2.2.0 | from the generated `android/`; minSdk 24, targetSdk 36, compileSdk 37 |
| Chrome | `C:\Program Files\Google\Chrome\Application\chrome.exe` | headless screenshots (dashboard-dev skill) |
| Postgres + RustFS | **18.6** (EDB binaries zip, no pgAdmin) + **1.0.4** | portable in `%LOCALAPPDATA%\safety-reviewer` (data, logs, downloads), installed and started by `backend/scripts/services.ps1` (no admin, no Docker). Postgres `127.0.0.1:5433` user/db `safety` (trust auth), RustFS `127.0.0.1:9000` key `safety` / `safety-secret`. Docker is **not** installed |
| PostgreSQL 18 (system service) | `postgresql-x64-18`, Automatic | someone's earlier EDB install, `C:\Program Files\PostgreSQL\18`, listening on `0.0.0.0:5432`, credentials unknown. Left alone; our database is on 5433 |
| OpenCV (system Python) | `cv2` 5.0.0 in `py -3.13` and `py` | lets `notebooks/safety_client.py --video` stream a webcam or file. Not in `backend/.venv` |
| Model venv | `rivian_model/.venv`, **Python 3.13** | Dušan's model (D44): CPU torch 2.15.0 from the PyTorch index first, then `rivian_model/requirements.txt` (ultralytics 8.4.203, **onnxruntime-directml 1.24.4** on Windows (D48), mediapipe 1.2.2, onnx 1.23.2). Weights: `setup_models.py`. PyPI gave only ~220 KB/s here (GitHub and Google downloads were fast), so the first install took ~30 min |
| GPUs | NVIDIA GeForce GTX 1650 (4 GB, driver 621.01) + AMD Radeon iGPU | the model uses the GTX 1650 through DirectML ("high performance" adapter). No CUDA toolkit installed (not needed for DirectML). For **training**: `rivian_model/.venv-train` (Python 3.13, `torch 2.15.0+cu132` from the PyTorch `cu132` index, ultralytics 8.4.204), `torch.cuda.is_available()` = True. The driver supports up to CUDA 13.5. Kept separate from `.venv` so the live model is never touched. GTX 16xx can produce NaN with AMP: if the loss goes NaN, train with `amp=False` |
| Dataset | `C:\Users\matija\Desktop\faks\hakaton\rivian\dataset` (116 clips: 82 `05_23_*`, 34 `08_14_*`, 30 s each) | outside the repo. The model scripts find it as `../dataset` next to the repo, or via `$env:DATASET_DIR` |

User env vars set by setup: `ANDROID_HOME`, plus PATH entries `%ANDROID_HOME%\platform-tools` and `%ANDROID_HOME%\cmdline-tools\latest\bin`.
**Shells or VS Code windows opened before setup don't see them**: restart VS Code, or set them in-session (mobile-dev skill).

**Matija Vujić's backend laptop (2026-11-07):** the Android SDK was there (`platform-tools` with adb 36.0.2) but nothing was on
PATH. Set `ANDROID_HOME` and added the PATH entries as **absolute** paths (`C:\Users\Matija\AppData\Local\Android\Sdk\platform-tools`,
`...\cmdline-tools\latest\bin`). Don't use `%ANDROID_HOME%\...` there: a shell that lacks `ANDROID_HOME` (a terminal opened
earlier that refreshes PATH from the registry) leaves `%ANDROID_HOME%` unexpanded and still can't find adb.

## Test phone

| fact | value |
|---|---|
| model | Samsung Galaxy A54 5G, **SM-A546B** |
| OS | **Android 16 (API 36), One UI 8.0**, build A546BXXSFEYJ9, patch 2025-10-01 |
| ABI / screen | arm64-v8a · 1080×2340, density 450 (override 420) |
| adb serial | `RZCW60AY39Y`. USB debugging authorized for this PC (2026-11-06). Windows shows "ADB Interface" (Samsung driver OK) |
| hotspot | interface `swlan0`, **randomized subnet**: on 2026-11-06 the phone was `10.190.62.95/24` |

Android 16 means full-screen intents need the special-access toggle for non-alarm/call apps, and foreground-service types are mandatory.

## Network (when the laptop is on the phone's hotspot)

- Laptop adapter `WiFi`: `10.190.62.27`, gateway (= the phone) `10.190.62.95`. Both change between hotspot sessions.
- Windows classed the hotspot as **Public**. Python 3.13 is allowed inbound (backend reachable ✅). `node.exe` has Block rules on
  Public (Metro over Wi-Fi and the LAN dashboard are blocked; USB is fine). The fix is in `networking.md` § Windows firewall. The adapter alias is `WiFi`.
- Extra adapters exist: VirtualBox host-only `192.168.56.1` ("Ethernet 2"), Hyper-V `192.168.16.1`, Npcap loopback. Code that guesses the
  "LAN IP" must pick the adapter with the default route (the UDP-connect trick in `backend/run.py` does). Never take the first adapter.

## Session 4 additions (2026-11-06 evening)

- **Docker Desktop is installed** (client/server 29.9.2). Postgres 18.6 + RustFS 1.0.4 run from `backend/docker-compose.yml`
  (`docker compose up -d` in `backend/`): containers `backend-postgres-1` (:5433) and `backend-rustfs-1` (:9000/:9001). The WSL
  Ubuntu distro has a sudo password; nothing here needs WSL directly.
- Backend venv now also has `diskcache`, `Pillow` (coordinator) and `numpy` (risk-engine test). It was missing even the storage
  requirements (`sqlalchemy`, `asyncpg`, `boto3`, `imageio-ffmpeg`): the backend that was running was the very first version.
- **uvicorn `--reload` on Windows leaves an orphan:** killing the reloader doesn't kill its `multiprocessing.spawn` worker, which keeps
  listening on :8000 next to the new one (Windows allows it), so stale code answers at random. Kill the whole tree (`taskkill /T /F`)
  and check `Get-NetTCPConnection -LocalPort 8000`. The backend now runs in its own minimized console window (`Start-Process`).
- The A54's USB link dropped twice in this session (`adb reverse` list emptied, then `offline`, then gone; Windows still showed
  "ADB Interface"). `adb kill-server` didn't bring it back: replug the cable / re-allow USB debugging. Re-apply `adb reverse` after.
- Do NOT swipe in the recents screen blindly: One UI centres the *previous* app there. Remove one task with
  `adb shell am stack remove <taskId>` (task id from `dumpsys activity recents`), which is what "swipe away" does.

## Bluetooth (the car link, 2026-11-07; protocol in docs/BLUETOOTH.md)

- **Laptop adapter:** MediaTek Bluetooth Adapter. WinRT reports LE, **peripheral role**, central role, LE Secure Connections and
  extended advertising as supported (max advertisement data 312 B). Check again with the PowerShell snippet in the
  `backend-local` skill (BluetoothAdapter.GetDefaultAsync).
- **The laptop's Bluetooth radio was OFF.** `GattServiceProvider.CreateAsync` then fails with `RadioNotAvailable`. The gateway
  turns it on by itself (Windows.Devices.Radios, allowed without a prompt for a desktop app); the taskbar toggle works too.
- The laptop advertises from `XX:..:A3:5D`; the A54 connects from a random private address that changes per connection
  (the gateway log shows a different "phone ..." address each time). Neither side may rely on a fixed address: the app finds
  the car by the service UUID and only *prefers* the last address.
- Windows never lets a GATT server set the advertised name (it's the computer name); the car's name in the app comes from `hello`.
- Python: pywinrt 3.2.1 (`winrt-*` packages) works on Python 3.13. Overloads have their own names
  (`start_advertising_with_parameters`), WinRT callbacks run on its thread pool (hand off with `loop.call_soon_threadsafe`).
- **A54 (Android 16):** `adb shell cmd bluetooth_manager enable|disable` switches Bluetooth; Android does **not** call a GATT
  client back when Bluetooth goes off (the module listens to `ACTION_STATE_CHANGED` instead). `adb logcat -s BluetoothGatt`
  shows connect, MTU, priority, discovery and CCCD steps per app pid; notifications are not logged.
