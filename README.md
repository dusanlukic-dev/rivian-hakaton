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
```
Brzina auta je fiksna (`cruise`, 50–62 km/h), da demo svaki put izgleda isto. Opcije su na vrhu `demo.ps1`.
Poređenje modela na 4 klipa: `rivian_model/POREDJENJE_MODELA.md` i `rivian_model/run_compare.py`.

**Demo network:** the phone hosts a mobile hotspot, the laptop joins it, and the app connects to the IP that `run.py` prints. The Windows
firewall must allow Python on Public networks. See [`.claude/knowledge/networking.md`](.claude/knowledge/networking.md).
