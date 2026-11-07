# Personal Safety Reviewer (Rivian hackathon)

An in-cabin camera watches the driver. The camera model (`rivian_model/`) sees phone use, eyes off the road, closed eyes
and a collapsed driver, and the backend's coordinator turns that into an **attention score 0–100** plus the car's reaction
(dashboard light, seat vibration, sound, message), pushed live to the phone (Bluetooth LE or WebSocket). A **phone app** and a
**web dashboard** (mock car screen) warn the driver, and every trip ends with a report. Domain rules are in [`CLAUDE.md`](CLAUDE.md)
and the contract is in [`docs/API.md`](docs/API.md).

```
backend/              FastAPI: coordinator (in the car: camera, model link, score, sections) + server (accounts, history, reports)
backend/coordinator/  car_link/ = Bluetooth LE gateway between the phone and the coordinator
rivian_model/         the camera model (own venv / Docker): YOLO11n + YOLO11n-pose + MediaPipe face -> evidence per category
notebooks/            risk_config.json (the coordinator's risk thresholds), safety_client.py (drive simulator, no camera)
frontend/mobile/      Expo SDK 58 / React Native 0.88 Android app (dev build)
frontend/dashboard/   Vite + React 19 + Tailwind + shadcn mock car screen
tools/                camera_stream.py (clip / webcam -> coordinator), sim.py (exact states), gen-sounds.mjs
start.ps1             the whole system in Docker, one command (docker-compose.yml, docker/): DOCKER.md
demo.ps1              the whole car natively on this laptop (no Docker), one window per part
docs/                 API.md (contract), ARCHITECTURE.md (coordinator / server / model), BLUETOOTH.md, DATABASE.md
PROGRESS.md           live status board: start here
.claude/              agent rules, skills, knowledge books (architecture, contract notes, Android alerting, networking…)
```

## Quick start

**Everything in Docker, one command** (installs Docker Desktop if needed, builds, starts; instructions: [DOCKER.md](DOCKER.md))
```powershell
.\start.ps1
```

**Backend + simulated drive** (Python 3.13; 3.15 can't install `fastapi[standard]` yet)
```bash
cd backend
py -3.13 -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe run.py                                       # 0.0.0.0:8000, prints the IP for the phone
.venv/Scripts/python.exe ../notebooks/safety_client.py --interval 0.3  # second terminal: drives through every level
```

**Dashboard**
```bash
cd frontend/dashboard
cp .env.example .env        # VITE_API_URL=http://localhost:8000
npm ci && npm run dev       # http://localhost:5173  (starter component docs: /usage-examples)
```

**Phone app** (Android, USB debugging on, `adb devices` shows the phone)
```bash
cd frontend/mobile
npm ci
npm run android             # builds + installs the dev build and starts Metro (first build ~15 min)
npm run adb:reverse         # the phone's localhost:8000/8001 then reach the laptop's coordinator/server over USB
```
Requirements: Node 20+, Android SDK (`ANDROID_HOME`), a JDK 17 the Gradle toolchain can find, and on Windows a long-path-aware Ninja.
See [`.claude/skills/mobile-dev/SKILL.md`](.claude/skills/mobile-dev/SKILL.md) and [`.claude/knowledge/environment.md`](.claude/knowledge/environment.md).

## Demo: the car with the camera model

The model runs in its own environment (Python 3.13 here; the models are not in git). Once:
```powershell
py -3.13 -m venv rivian_model\.venv
rivian_model\.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
rivian_model\.venv\Scripts\python.exe -m pip install -r rivian_model\requirements.txt
rivian_model\.venv\Scripts\python.exe rivian_model\setup_models.py
```
The model uses the GPU when there is one (DirectML on Windows: NVIDIA, AMD or Intel; CUDA on Linux) and the CPU otherwise
(`--device cpu` / `$env:MODEL_DEVICE` to force it); `GET /api/v1/coordinator/status` shows which.
Then every part in its own window (ports 8000 and 8001 must be free). The dataset clips live outside the repo
(`..\dataset`, or set `$env:DATASET_DIR`):
```powershell
.\demo.ps1 -PoVoznji -Dashboard                                  # every trip started on the phone gets the next clip
.\demo.ps1 -Video ..\dataset\05_23_62_031246_video_inCabin.mp4   # collapse -> emergency, clip looped
.\demo.ps1 -Video ..\dataset\08_14_62_092916_video_inCabin.mp4   # phone call
```
`demo.ps1` starts Postgres + RustFS (Docker), the server (:8001), the coordinator (:8000, mocked speed `cruise`, 50–62 km/h),
the Bluetooth gateway (or keeps the one already running), the model, the camera, and a small window that keeps the phone's
USB ports (`adb reverse`) alive. Every run starts clean (it closes its own earlier windows); `.\demo.ps1 -Stop` stops it all.
If Windows ever reserves one of our ports (WinError 10013), run `tools\reserve-ports.ps1` once as administrator. One camera at a time: a second stream would mix two drivers' frames into one
model, so the coordinator refuses it. The model needs the camera's driver zone (`--camera 05_23|08_14`, taken from the clip
name), so clips of one run come from one camera series. Model details: [`rivian_model/README.md`](rivian_model/README.md).

### Release APK without Android Studio and without LongPathsEnabled (Dušan, verified 2026-11-07)

A release APK has the JS inside (no Metro). Needs JDK 17, the Android SDK in `%LOCALAPPDATA%\Android\Sdk`
(`platforms;android-37.0`, `build-tools;37.0.0`, `ndk;27.1.12297006`, `cmake;3.30.5`, `cmake;3.22.1`, installed with
`cmdline-tools\latest\bin\android.exe --no-metrics sdk install ...`, not `sdkmanager.bat`: `cmd` splits the `;` in package names)
and Ninja 1.13.2 in both `cmake\*\bin\`. Without `LongPathsEnabled` the build must run from a short folder
(`git worktree add --detach C:\r main`; `subst` doesn't work, codegen fails on "different roots") with `CMAKE_OBJECT_PATH_MAX=250`
in the generated `android/app/build.gradle`:
```powershell
cd C:\r\frontend\mobile; npm ci; $env:CI=1; npx expo prebuild --platform android --no-install
# android\app\build.gradle, in defaultConfig { ... }:  externalNativeBuild { cmake { arguments "-DCMAKE_OBJECT_PATH_MAX=250" } }
$env:ANDROID_HOME="$env:LOCALAPPDATA\Android\Sdk"; $env:JAVA_HOME="C:\Program Files\Java\jdk-17"
$env:JAVA_TOOL_OPTIONS="-Djavax.net.ssl.trustStoreType=Windows-ROOT"   # only behind an HTTPS-inspecting antivirus (AVG)
cd android; .\gradlew.bat assembleRelease -PreactNativeArchitectures=arm64-v8a   # ~10-20 min; APK: app\build\outputs\apk\release\
```
To the phone over Wi-Fi: `python -m http.server 8766 --bind 0.0.0.0` in the APK's folder, then open
`http://<laptop IP>:8766/<name>.apk` on the phone and allow installing unknown apps.

**Demo network:** the phone hosts a mobile hotspot, the laptop joins it, and the app connects to the IP that `run.py` prints. The Windows
firewall must allow Python on Public networks. See [`.claude/knowledge/networking.md`](.claude/knowledge/networking.md).
