# Personal Safety Reviewer (Rivian hackathon)

An in-cabin camera watches the driver. Camera models label risky behaviours (phone, looking behind, turning around, hands off the wheel,
drowsy), and the backend turns them into an **attention coefficient 0–100** plus the car's reaction (dashboard light, seat vibration,
sound, message), pushed live over a WebSocket. A **phone app** and a **web dashboard** (mock car screen) warn the driver, and every trip
ends with statistics and tips. Domain rules are in [`CLAUDE.md`](CLAUDE.md) and the contract is in [`docs/API.md`](docs/API.md).

```
backend/              FastAPI: scoring, levels, REST /trips, WS /api/v1/ws      (backend)
notebooks/            CV models; safety_client.py = models→backend bridge + drive simulator
frontend/mobile/      Expo SDK 58 / React Native 0.88 Android app (dev build)   (frontend)
frontend/dashboard/   Vite + React 19 + Tailwind + shadcn mock car screen       (frontend)
tools/                gen-sounds.mjs (alert sounds for both apps)
docs/API.md           backend ↔ app contract (source of truth)
PROGRESS.md           live status board: start here
.claude/              agent rules, skills, knowledge books (architecture, contract notes, Android alerting, networking…)
```

## Quick start

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
npm run adb:reverse         # the phone's localhost:8000 then reaches the laptop's backend over USB
```
Requirements: Node 20+, Android SDK (`ANDROID_HOME`), a JDK 17 the Gradle toolchain can find, and on Windows a long-path-aware Ninja.
See [`.claude/skills/mobile-dev/SKILL.md`](.claude/skills/mobile-dev/SKILL.md) and [`.claude/knowledge/environment.md`](.claude/knowledge/environment.md).

## Demo sa našim modelom (grana `nas-demo`)

Ova kopija (`rivian-demo`) koristi **naš model** (`rivian_model/`) i ima **kolaps** od modela do telefona
(skor 0 + uzbuna odmah, i dok auto stoji). Ostalo je isto kao na `main`. Jednom:
```powershell
cd backend;      py -3.13 -m venv .venv; .venv\Scripts\python.exe -m pip install -r requirements.txt; cd ..
cd rivian_model; python setup_models.py; cd ..      # modeli (nisu u gitu); treba ultralytics, onnxruntime, mediapipe
```
Demo (svaki deo u svom prozoru; port 8000 mora biti slobodan):
```powershell
.\demo.ps1 -Video "<dataset>\05_23_62_031246_video_inCabin.mp4" -Dashboard   # kolaps -> uzbuna
.\demo.ps1 -Video "<dataset>\08_14_62_092916_video_inCabin.mp4"              # telefon
.\demo.ps1 -Model cv -Video ...                                               # model CV kolege, isti backend
.\demo.ps1 -PoVoznji -Dashboard                                               # svaka voznja iz aplikacije = sledeci klip
```
Samo jedna kamera u isto vreme (`-Video`, `-Webcam` ili `-PoVoznji`): koordinator prima više kamera odjednom i meša
njihove frejmove, pa model vidi „dva vozača“. `demo.ps1` i `rivian_model/klip_po_voznji.py` to sada odbijaju.
Brzina auta je fiksna (`cruise`, 50–62 km/h), da demo svaki put izgleda isto. Opcije su na vrhu `demo.ps1`.
Poređenje modela na 4 klipa: `rivian_model/POREDJENJE_MODELA.md` i `rivian_model/run_compare.py`.

### APK za telefon bez kabla i bez Android Studija (provereno 7. 11. 2026)

Release APK sa ugrađenim JS-om (ne treba Metro). Treba: JDK 17, Android SDK u `%LOCALAPPDATA%\Android\Sdk`
(`platforms;android-37.0`, `build-tools;37.0.0`, `ndk;27.1.12297006`, `cmake;3.30.5`, `cmake;3.22.1`, instalirano sa
`cmdline-tools\latest\bin\android.exe --no-metrics sdk install ...`, ne sa `sdkmanager.bat`: `cmd` deli `;` u imenu paketa)
i Ninja 1.13.2 u oba `cmake\*\bin\`. Bez `LongPathsEnabled` build mora iz kratkog foldera (`git worktree add --detach C:\r nas-demo`;
`subst` ne radi, codegen puca na „different roots“) i uz `CMAKE_OBJECT_PATH_MAX=250` u generisanom `android/app/build.gradle`:
```powershell
cd C:\r\frontend\mobile; npm ci; $env:CI=1; npx expo prebuild --platform android --no-install
# android\app\build.gradle, u defaultConfig { ... }:  externalNativeBuild { cmake { arguments "-DCMAKE_OBJECT_PATH_MAX=250" } }
$env:ANDROID_HOME="$env:LOCALAPPDATA\Android\Sdk"; $env:JAVA_HOME="C:\Program Files\Java\jdk-17"
$env:JAVA_TOOL_OPTIONS="-Djavax.net.ssl.trustStoreType=Windows-ROOT"   # AVG presrece HTTPS: Java koristi Windows sertifikate
cd android; .\gradlew.bat assembleRelease -PreactNativeArchitectures=arm64-v8a   # ~10-20 min; APK: app\build\outputs\apk\release\
```
Na telefon preko Wi-Fi-ja: `python -m http.server 8766 --bind 0.0.0.0` u folderu sa APK-om, pa na telefonu
`http://<IP laptopa>:8766/<ime>.apk` i „instaliraj nepoznate aplikacije“. U aplikaciji adresa backenda: `<IP laptopa>:8000`.
Proba (031246 u petlji, `demo.ps1 -Port 8000 -Storage docker`): 3 vožnje sa telefona, sve sa kolapsom → skor 0 + uzbuna,
sačuvane na serveru (Postgres) sa sekcijama.

**Demo network:** the phone hosts a mobile hotspot, the laptop joins it, and the app connects to the IP that `run.py` prints. The Windows
firewall must allow Python on Public networks. See [`.claude/knowledge/networking.md`](.claude/knowledge/networking.md).
