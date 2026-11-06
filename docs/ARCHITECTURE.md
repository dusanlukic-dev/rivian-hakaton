# Arhitektura: koordinator, server i model

Backend ima **dva dela sa jasnom granicom** (koordinator i server), a model radi kao **zaseban proces**.
U demo-u koordinator i server rade u jednom procesu na portu 8000 (`python run.py`), ali jedan drugom se
obraćaju samo preko HTTP API-ja, pa se razdvajaju podešavanjem, bez izmene koda.

| Deo | Gde radi | Šta radi | Šta NE radi |
|---|---|---|---|
| **Model** (`model/worker.py`) | svoj proces i svoje okruženje (kasnije svoj Docker kontejner) | prima frejm, detektuje (kod CV tima: MediaPipe, YOLO, `FeatureExtractor`) i vraća **dokaz** `p` po kategoriji | ne računa rizik, score ni reakciju kola |
| **Koordinator** (`backend/app/coordinator/`) | u kolima (laptop) | prima video, šalje frejmove modelu, računa rizik (izdvojen `RiskEngine` CV tima), score 0–100 i reakciju kola, šalje stanje telefonu (WS), drži keš (5 min videa + sekcije), na svake 2 s pravi **rezime sekcije** i šalje ga serveru i telefonu | nikad ne dira Postgres ni S3 |
| **Server** (`backend/app/server/`) | u demo-u isti proces; kasnije poseban server | nalozi, prima rezimee od koordinatora, čuva ih (Postgres) zajedno sa slikama (S3), služi istoriju, izveštaj sa grafikom i slikama, analitiku | ne zna ništa o kameri, modelu ni WebSocket-u |

## Tok podataka

```
 kamera (tools/camera_stream.py: snimak u petlji, test slika ili web kamera)
    │ jedan JPEG po poruci, ~10 fps ── WS /api/v1/camera/ws   (ili POST /api/v1/video/frames)
    ▼
┌─ KOORDINATOR ──────────────────────────────────────────────────────────────────────────────┐
│  VideoCache (diskcache, 5 min) ◄── frejm                                                   │
│        │                         ModelLink ── binarni frejm ──────────► model worker       │
│        │                             ▲      ◄── JSON: dokaz po kategoriji ─┘ (WS /model/ws)│
│        │                             ▼                                                     │
│        │        RiskEngine (matematika CV tima): glađenje, trajanje, grupe, pravila, alarm │
│        │                             │                                                     │
│        │   brzina (mock, "spolja") ─►│◄── POST /telemetry (simulator: labele ili zapis)    │
│        │                             ▼                                                     │
│        │        scoring.py + alerts.py: score 0–100, nivo, reakcija kola                   │
│        │               │                                  │                                │
│        │               ▼                                  ▼                                │
│        │   WS `state` ~2/s, `emergency`        SectionRecorder: sekcija od 2 s (memorija)  │
│        └── slika najrizičnijeg frejma ───────────────► opasna sekcija                      │
│                                                           ├──► WS `section` (telefon)      │
│                                                           ▼                                │
│                              ServerOutbox: redom, ponavlja dok server ne odgovori         │
└──────────────────────────────────────────────────────── │ ────────────────────────────────┘
                                                          │ POST /api/v1/internal/trips/{id}/sync
                                                          ▼   (X-Internal-Token)
┌─ SERVER ───────────────────────────────────────────────────────────────────────────────────┐
│  TripStore: trips + trip_sections (Postgres :5433), slike sections/<vožnja>/<sekcija>.jpg (S3) │
│  REST za aplikacije: /auth, GET /trips, /trips/{id}/summary | report | sections, /media, /analytics │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

Telefon i dashboard i dalje imaju **jednu adresu** (`http://<IP>:8000/api/v1`): uživo (WS, start i kraj
vožnje) odgovara koordinator, a istoriju, izveštaj i naloge server. Koji deo služi koju rutu piše u
[API.md](API.md) §5.

## Ko šta računa

1. **Model** (`model/worker.py`): perception + `FeatureExtractor` iz `notebooks/risk_pipeline.py`,
   uvezeni bez izmena. Izlaz je dokaz `p_i` ∈ [0, 1] po kategoriji (`phone_use`, `eyes_off_road`,
   `hands_off_wheel`, `eating_drinking`, `drowsiness`, `eyes_closed`).
2. **Koordinator, rizik** (`coordinator/services/risk_engine.py`): `RiskEngine` CV tima, **izdvojen** iz
   `risk_pipeline.py` (fajl CV tima se ne menja). Matematika je ista do bita:
   `tests/test_risk_engine.py` pušta nasumičan dokaz kroz kopiju i original i traži iste zapise i rezime.
   Pragove i dalje podešava CV tim u `notebooks/risk_config.json` (čitaju ga oba).
3. **Koordinator, score** (`scoring.py`, `alerts.py`): naš koeficijent 0–100 (težina × sekunde ×
   brzina × noć × krhkost, oporavak), nivoi i reakcija kola. Crveni alarm modela odmah pali vibraciju i
   glasan zvuk. Ovo je ostalo isto kao pre podele.
4. **Server**: ništa ne računa, samo čuva i spaja uzastopne opasne sekcije u momente pri čitanju.

Kad CV tim počisti svoj kod, `RiskEngine` iz `risk_pipeline.py` može da se izbaci: worker ga ne koristi,
a koordinator ima svoju kopiju.

## Sekcije (rezime na 2 s)

Koordinator skuplja sve tickove (detekcije modela ~5–10/s ili telemetriju) u memoriji i na svake
**2 s vožnje** (`SECTION_S`) zatvara **sekciju**: score na početku, kraju i minimum, brzina, koja
ponašanja su viđena i koliko sekundi, brojevi modela (`p`, `p_max`, `r`, `run_s` po kategoriji, rizik,
alarm, pravila), reakcija kola (svetlo, vibracija, zvuk), uzbuna i **opasnost**:

| `danger` | Kada (samo dok se kola kreću, ≥ 5 km/h) |
|---|---|
| `critical` ("ultra opasno") | crveni alarm modela, glasan alarm kola (`sound: high`) ili uzbuna |
| `dangerous` | vidi se bodovano ponašanje, žuti alarm modela ili je sedište vibriralo |
| `none` | sve ostalo, i uvek dok kola stoje |

Zašto 2 s: model u sekciji i dalje da 10–20 detekcija (stabilno "šta je viđeno"), pola sata vožnje je
900 tačaka na grafiku, a opasan momenat stiže do servera i telefona za ~2 s.

Za **opasnu sekciju** koordinator uzima iz video keša frejm njenog najrizičnijeg trenutka (najveća
opasnost, pa rizik modela, pa koliko je score pao). Kad radi model, to je baš frejm koji je model
analizirao. Slika se smanji na 960 px (`SECTION_IMAGE_WIDTH`) i ide uz sekciju serveru.

Sekcija ide na dva mesta:
- **telefonu**, odmah, kao WS `section` (bez slike, `image_url: null`), za uživo prikaz "šta je viđeno";
- **serveru**, preko outbox-a, sa slikom i trenutnim rezimeom vožnje.

Server pri čitanju izveštaja spaja uzastopne opasne sekcije u **momente** (jedna mirna sekcija u sredini
se premošćuje). Momenat ima čvor na grafiku (`peak_t`, `peak_score`) i sliku najrizičnijeg frejma.

## Keš u koordinatoru

| Šta | Gde | Koliko |
|---|---|---|
| otvorena sekcija vožnje | memorija (`SectionRecorder`) | jedna po vožnji |
| sekcije, slike i rezime koje server još nije potvrdio | memorija (`ServerOutbox`) | do 10 000 sekcija po vožnji i 300 MB slika; preko toga prvo ispadaju najstarije sekcije, pa nove slike |
| video | **diskcache** u temp folderu (`VideoCache`), briše se na svakom startu | 5 min (`VIDEO_CACHE_S`), najviše 1 GB, najviše 10 frejmova u sekundi |

- Frejm koji je model analizirao uvek ostaje u kešu, jer može postati slika sekcije.
- Upis na disk ide kroz jednu pozadinsku nit, pa event loop (živi score) nikad ne čeka disk.
- `VIDEO_CACHE=memory` drži video u memoriji (testovi, mašine bez diska).
- **Zašto ne Redis:** jedan koordinator po kolima ne treba deljeni keš, a disk i memorija ne traže još
  jedan servis. Ako koordinatora bude više ili keš treba da preživi restart, Redis Streams su prirodan
  sledeći korak (XADD po vremenu, XRANGE za "frejmove između t0 i t1").
- `VideoCache.frames_between()` + `video.encode_mp4()` su spremni za planirano: **video celog momenta**
  umesto jedne slike.

## Ugovori između delova

### 1. Telefon / dashboard ↔ backend
Javni ugovor: [API.md](API.md). Novo: WS događaj `section` i izveštaj sa sekcijama i momentima.

### 2. Kamera → koordinator
`WS /api/v1/camera/ws`: **jedna binarna poruka = jedan JPEG** (do 2 MB). Bez aktivne vožnje frejmovi se
odbacuju, a socket ostaje otvoren. Isto radi i `POST /api/v1/video/frames` (telo je JPEG), koji koristi
`notebooks/safety_client.py --video`.

### 3. Koordinator ↔ model (`WS /api/v1/model/ws`)
Model se **sam javlja** koordinatoru (nema novog porta ni firewall pravila, bilo ko može da se restartuje).

| Smer | Poruka |
|---|---|
| model → koordinator | `{"type": "hello", "worker": "cv-pipeline", "version": "1.0", "categories": [...]}` |
| koordinator → model | binarno: `uint32 LE dužina zaglavlja` + JSON zaglavlje `{"type": "frame", "id": 41, "t": 12.375, "trip_id": "..."}` + JPEG |
| model → koordinator | `{"type": "detection", "id": 41, "t": 12.375, "trip_id": "...", "evidence": {"phone_use": 0.82, ...}, "perception": {...}, "ms": 84.2}` |
| model → koordinator | `{"type": "error", "id": 41, "message": "..."}` (frejm se preskače) |
| koordinator → model | `{"type": "reset", "trip_id": "..."}` (nova vožnja: detektori ispočetka) · `{"type": "idle"}` (vožnja gotova) |

- `t` = sekundi od početka vožnje; detektori ga koriste kao svoj sat.
- **Jedan frejm u letu.** Novi frejmovi menjaju onaj koji čeka (najnoviji pobeđuje), pa spor model ne
  pravi red i detekcija nikad nije starija od jednog frejma. Frejm bez odgovora 5 s se računa kao izgubljen.
- Aktivan je jedan worker; nova konekcija zamenjuje staru.
- Koordinator šalje telefonu `state` ~2/s (i odmah na promenu nivoa, reakcije ili ponašanja), iako
  detekcije stižu 5–10/s.

### 4. Koordinator → server (`/api/v1/internal/*`, zaglavlje `X-Internal-Token`)
- `POST /internal/trips/{trip_id}/sync`, telo `TripSync` (`backend/app/schemas/sync.py`): podaci o vožnji
  (svaki put; server ignoriše ono što već ima), nove sekcije sa slikom (base64 JPEG) i trenutni rezime
  (`ended_at` kad je gotova). Idempotentno: koordinator ponavlja paket posle greške. Odgovor
  `{"sections": n, "images": m}`, `503` dok je Postgres dole, `403` bez tokena.
- `POST /internal/trips/close-interrupted`, telo `{"keep": [...]}`: koordinator ga zove posle svakog
  starta, pa vožnje koje je pad ostavio otvorene dobiju kraj na poslednjem rezimeu.
- Token je `INTERNAL_TOKEN` (podrazumevano `dev-internal-token`). Promeni ga čim je server dostupan drugima.

## Pouzdanost

| Šta otkaže | Šta se dešava |
|---|---|
| server ili Postgres | živi score, reakcije i WS rade; sekcije čekaju u outbox-u i odlaze kad se server vrati (jedno upozorenje u logu, jedna poruka kad se vrati). Istorija i izveštaj daju `503` |
| S3 (RustFS) | sekcije se čuvaju bez slike |
| model | nema detekcija; simulator i dalje radi preko `POST /telemetry`. `GET /coordinator/status` pokazuje stanje |
| kamera | otvorena sekcija se zatvara 3 s posle poslednjeg ticka |
| koordinator (pad, restart) | vožnja ostaje na serveru sa rezimeom do poslednje sekcije; novi koordinator traži da se zatvori |
| kraj vožnje ("End") | koordinator čeka do 3 s da server primi sve, pa izveštaj odmah posle kraja ima celu vožnju |

## Pokretanje

```powershell
cd backend; docker compose up -d                              # Postgres :5433 + RustFS :9000 (ili .\scripts\services.ps1 start)
cd backend; .venv\Scripts\python.exe run.py                   # koordinator + server, :8000
backend\.venv\Scripts\python.exe tools\camera_stream.py       # kamera: test slika (--video snimak.mp4, --webcam "ime")
backend\.venv\Scripts\python.exe model\worker.py --fake       # model bez CV paketa (skriptovane detekcije)
model\.venv\Scripts\python.exe model\worker.py                # pravi model CV tima (model/README.md)
curl http://127.0.0.1:8000/api/v1/coordinator/status          # kamera fps, model, keš, isporuka serveru
```

Simulator bez kamere i modela i dalje radi: `python notebooks/safety_client.py`.

Odvojeno (kasnije i u Docker-u):
```powershell
.venv\Scripts\python.exe run.py --role server --port 8001
$env:SERVER_URL="http://127.0.0.1:8001/api/v1"; .venv\Scripts\python.exe run.py --role coordinator
```
Tada telefon treba da istoriju i izveštaj traži od servera (reverse proxy ispred oba dela još nije
napravljen). `model/Dockerfile` je spreman za kontejner modela (još nije testiran).

## Gde šta

| Hoćeš da... | Fajl |
|---|---|
| promeniš dužinu sekcije ili pravila opasnosti | `SECTION_S`, `tick_danger` u `coordinator/services/sections.py` |
| promeniš koji frejm postaje slika | `_Section.add` (peak), `_section_image` u `coordinator/services/coordinator.py` |
| promeniš keš videa | `VIDEO_CACHE*` u `core/config.py`, `coordinator/services/video_cache.py` |
| promeniš protokol sa modelom | `coordinator/services/model_link.py` i `model/worker.py` (oba!) |
| promeniš isporuku serveru | `coordinator/services/outbox.py`, `server_client.py`, `schemas/sync.py`, `server/routes/internal.py` |
| promeniš kako se sekcije čuvaju | `server/repositories/recordings.py`, `server/services/storage.py`, [DATABASE.md](DATABASE.md) |
| promeniš momente | `build_moments` u `server/services/history.py` |
| podesiš rizik modela | `notebooks/risk_config.json` (CV tim); kod je u `coordinator/services/risk_engine.py` |

## Planirano

- Video celog momenta umesto slike (`VideoCache.frames_between` + `encode_mp4`, klip u S3 uz sekciju).
- Model u Docker kontejneru (`model/Dockerfile`), koordinator i server u svojim.
- Više kola: `car_id` u `TripMeta` i `close-interrupted` po kolima; deljeni keš (Redis) ako zatreba.
- Reverse proxy da telefon i u odvojenom režimu ima jednu adresu; potpisani URL-ovi za slike.
