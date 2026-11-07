# Personal Safety Reviewer – backend (FastAPI)

Računa koeficijent bezbednosti vozača (0–100) iz onoga što model vidi na kameri i uživo javlja mobilnoj
aplikaciji kako kola treba da reaguju (svetlo na dashboardu, vibracija sedišta, zvuk, poruka kontaktu).
Usput pravi izveštaj vožnje: na svake 2 s rezime (score, šta je viđeno, opasnost) i sliku opasnih momenata.

## Arhitektura: koordinator, server i model

Detalji (tok podataka, ugovori između delova, keš, pouzdanost): **[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)**.

```
 laptop = računar u kolima                                                    telefon (hotspot)
┌───────────────────────────────────────────────────────────────────────┐    ┌──────────────────┐
│ kamera ── JPEG ──► KOORDINATOR (app/coordinator) ── WS /api/v1/ws ─────┼───►│ uživo: score,    │
│ (tools/camera_stream.py)  │  ▲                         state, section  │    │ alarmi, sekcije  │
│                frejm      ▼  │ dokaz po kategoriji                     │    │                  │
│            model (rivian_model/rivian_detector.py, svoj proces)        │    │                  │
│                           │ sekcije od 2 s + slike (POST /internal/...)│    │                  │
│                           ▼                                            │    │                  │
│            SERVER (app/server) ── /auth, /trips, /report, /media ──────┼───►│ istorija,        │
│            Postgres :5433 (trips, trip_sections) · RustFS S3 :9000     │    │ grafik vožnje    │
└───────────────────────────────────────────────────────────────────────┘    └──────────────────┘
```

- **Koordinator** prima video (jedna kamera), šalje frejmove modelu i od njegovog dokaza računa rizik
  (`RiskEngine`), score i reakciju kola, šalje stanje telefonu, drži 5 min videa u kešu i na svake
  2 s šalje rezime sekcije serveru (sa slikom najrizičnijeg frejma kad je sekcija opasna) i telefonu.
  Nikad ne dira bazu.
- **Server** čuva naloge, vožnje, sekcije i slike i služi istoriju i izveštaj. Ne zna ništa o kameri.
- **Model** (`rivian_model/rivian_detector.py`, Dušan) radi u svom okruženju (`rivian_model/.venv`, kasnije
  Docker) i samo detektuje: telefon, pogled van puta, zatvorene oči, kolaps.
- U demo-u koordinator i server rade u **jednom procesu** na portu 8000 (`python run.py`), pa telefon ima
  jednu adresu. Jedan drugom se i tada obraćaju samo preko HTTP-a.
- U jednom trenutku je aktivna **jedna vožnja** (jedan auto). Aplikacija je pokreće i završava.
- **Brzinu daje koordinator**, jer je kamera ne zna: mock vožnja (scenario po vožnji), ili GPS telefona
  ako je uključen (`PHONE_SPEED_ENABLED=true`).
- Simulator bez kamere i modela i dalje radi: `POST /telemetry` (`notebooks/safety_client.py`, `tools/sim.py`).

## Čuvanje vožnje i nalozi (server: Postgres + RustFS)

Cela struktura baze, šta se šalje frontu i review su u **[docs/DATABASE.md](../docs/DATABASE.md)**.

| Tabela / bucket | Šta | Za izveštaj |
|---|---|---|
| `users`, `user_sessions` | nalog (korisničko ime, scrypt heš lozinke, ime, kontakt) i prijave (samo SHA-256 tokena) | ko je vozio |
| `trips` | početak, rezime sa svakom sekcijom i konačan na kraju (final/prosek/min score, ponašanja) | istorija, statistika |
| `trip_sections` | **jedan red na 2 s vožnje**: score, opasnost, ponašanja u sekundama, svi brojevi modela, brzina, reakcija kola, ključ slike | grafik vožnje, momenti |
| S3 `safety-media/sections/<trip>/<sekcija>.jpg` | najrizičniji frejm opasne sekcije (960 px) | slika na grafiku |

- Opasnost sekcije (samo u vožnji): `critical` = crveni alarm modela, glasan alarm ili uzbuna; `dangerous` =
  vidi se bodovano ponašanje, žuti alarm ili vibracija. Uzastopne opasne sekcije su jedan **momenat**.
- Čitanje: **`GET /trips/{id}/report`** vraća sve o jednoj vožnji (rezime, korisnik, sekcije, momenti sa
  slikama). Postoje i `/sections`, istorija `GET /trips` i slika preko `GET /media/...` (sve u
  [docs/API.md](../docs/API.md)). Radi i posle restarta.
- Nalozi: `POST /auth/register`, `POST /auth/login` → token (`Authorization: Bearer ...`). Vožnja
  pokrenuta sa tokenom pripada nalogu i vidi je samo on. Bez prijave sve radi kao ranije (`driver_id`).
- Ako Postgres ili S3 nisu podignuti, **score i reakcije kola rade normalno**. Sekcije čekaju u
  koordinatoru i stignu kad se server vrati; bez S3 se čuvaju bez slike.
- Bucket je za demo **javan**. Kompanija (`/analytics`) slike nikad ne dobija.

Pokretanje servisa:
```powershell
docker compose up -d             # Postgres 127.0.0.1:5433, RustFS 127.0.0.1:9000 (konzola :9001, safety / safety-secret)
.\scripts\services.ps1 install   # ...ili bez Docker-a: portabl Postgres 18.6 + RustFS 1.0.4 (jednom)
.\scripts\services.ps1 start     # ...pa posle samo start
.\scripts\services.ps1 psql      # SQL nad bazom, npr. select seq, score_end, danger from trip_sections order by started_at desc limit 20;
.\scripts\services.ps1 reset     # prazna baza (posle promene tabela, jer migracija još nema); Docker: docker compose down -v
```
Adrese i ključevi se menjaju u `.env` (primer: [.env.example](.env.example)). `RECORDING_ENABLED=false` gasi čuvanje.

## Brzina

| Izvor | Kada |
|---|---|
| GPS telefona (`POST /speed`) | samo uz `PHONE_SPEED_ENABLED=true` i očitavanje mlađe od 5 s |
| `speed_kmh` u ticku | simulator i testovi, da vožnja kroz nivoe bude ista svaki put |
| mock vožnja | sve ostalo: scenario iz [app/coordinator/services/speed.py](app/coordinator/services/speed.py), `SPEED_SCENARIO=random` bira po vožnji |

Scenariji: `city` (30–50 km/h, tri semafora), `highway` (do 130), `stop_and_go` (gužva, dugo stajanje),
`country_road` (60–90), `cruise` (nikad ne staje, dobar za demo na bini), `parked` (stalno 0). Između
tačaka je kubna Bezier kriva sa ravnim ručkama: auto glatko ubrzava i koči, a stoji na tačno 0 km/h
(tada nema opasnosti ni upozorenja).

## Pokretanje

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python run.py        # za demo preko hotspota, ispisuje adresu za aplikaciju (koordinator + server)
fastapi dev app/main.py   # samo lokalno, http://127.0.0.1:8000/docs

# kamera (isti venv) i model (svoj venv: ../rivian_model/README.md); sve odjednom: ..\demo.ps1
python ..\tools\camera_stream.py --video ..\..\dataset\<klip>.mp4      # ili --webcam "ime"
..\rivian_model\.venv\Scripts\python.exe ..\rivian_model\rivian_detector.py --camera 05_23
```

Testovi: `pytest`

### Povezivanje telefona preko hotspota (nema DNS-a)
1. Uključi hotspot na telefonu i poveži laptop na njega.
2. Na laptopu pokreni `python run.py`. Ispisaće nešto ovako:
   ```
   REST       http://192.168.43.57:8000/api/v1
   WebSocket  ws://192.168.43.57:8000/api/v1/ws
   ```
3. Tu IP adresu unesi u aplikaciju. **IP se menja svaki put kad se laptop ponovo poveže na hotspot**,
   pa je ne hardkodujte, nego napravite polje u podešavanjima aplikacije.
4. **Windows Firewall:** pri prvom pokretanju Windows pita da li da pusti Python. Čekiraj i
   **Public** mreže, jer Windows hotspot često vodi kao javnu mrežu. Ako je prozor propušten,
   pokreni PowerShell kao admin:
   ```powershell
   New-NetFirewallRule -DisplayName "Safety API 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
   ```
5. Provera sa telefona: otvori `http://<IP>:8000/api/v1/health` u browseru.
6. U Expo Go / dev buildu `http://` i `ws://` rade odmah. Za samostalni Android build treba uključiti
   cleartext saobraćaj (`usesCleartextTraffic` preko `expo-build-properties`).

## Za tim sa modelima

**Put (kamera → koordinator → model):** model ne čita kameru i ne računa rizik. `rivian_model/rivian_detector.py`
prima frejmove od koordinatora i vraća dokaz po kategoriji (`phone_use`, `eyes_off_road`, `eyes_closed`,
`collapse`). Rizik računa `RiskEngine` u koordinatoru (`app/coordinator/services/risk_engine.py`), pragovi su u
`notebooks/risk_config.json`. Uputstvo: [rivian_model/README.md](../rivian_model/README.md). Model CV tima
(`model/worker.py` + `notebooks/risk_pipeline.py`) je uklonjen 2026-11-07 (u istoriji: commit `8d05c97`).

**Stari put ([notebooks/safety_client.py](../notebooks/safety_client.py)) i dalje radi**, npr. za replay:

```python
from safety_client import SafetyClient

client = SafetyClient()  # http://127.0.0.1:8000/api/v1
while True:
    ok, frame = cap.read()          # BGR frejm iz OpenCV-a
    record = ...                    # isti dict koji upisujete u frames.jsonl
    client.send_frame(record)       # sme svaki frejm, sam se ograniči na ~2/s
    client.send_video_frame(frame)  # sme svaki frejm, sam se ograniči na ~8/s (JPEG)
```

- `send_frame` šalje zapis neizmenjen, samo izbaci `perception`. numpy brojevi i nizovi su u redu.
  **Brzinu ne šaljite**, jer je backend zna (mock ili telefon). `speed_kmh=...` samo ako hoćete da je zakucate.
- `send_video_frame` prima BGR numpy frejm (kodira ga u JPEG kvaliteta 70) ili gotove JPEG bajtove.
  Frejm ide u video keš koordinatora, iz kog se uzima slika opasne sekcije.
- Ni jedno ni drugo ne ruši petlju za kameru ako backend nije podignut ili vožnja još nije počela
  (vraća `None` / `False`).
- Ako imate samo labele: `client.send({"looking_at_phone"})`. Za nepoznatu labelu odmah baca `ValueError`.
- Simulacija cele vožnje bez modela, korisno za front: `python notebooks/safety_client.py`
  (sa `--interval 0.3` ide brže od realnog vremena). `--video 0` usput strimuje web kameru (ili
  `--video snimak.mp4`), pa opasne sekcije dobijaju slike. `--backend-speed` prepušta brzinu mock vožnji.
- Replay snimljenog izlaza modela, kao da kamera radi uživo:
  `python notebooks/safety_client.py --replay frames.jsonl` (`--speedup 2`, `--speed-kmh 90`, `--video run.mp4`).

Kategorije modela → labele (`CATEGORY_TO_BEHAVIOR` u [app/coordinator/services/camera.py](app/coordinator/services/camera.py)).
Kategorije modela su u [notebooks/risk_config.json](../notebooks/risk_config.json) (`categories`).
Kategorija koja nije u tabeli ide aplikaciji, ali se ne boduje, a server jednom ispiše warning.
Test `tests/test_camera_mapping.py` pada ako model doda kategoriju koju backend ne zna.

| Kategorija modela | Labela |
|---|---|
| `phone_use` | `looking_at_phone` |
| `eyes_off_road` | `eyes_off_road` |
| `hands_off_wheel` | `hands_off_wheel` (aktivna kad su obe ruke van volana) |
| `drowsiness`, `eyes_closed` | `drowsy` |
| `eating_drinking` | ne boduje se (`IGNORED_CATEGORIES`, odluka u root `CLAUDE.md`) |
| ime same labele (npr. `looking_behind`) | ta labela |

`microsleep`, `long_distraction`, `phone_sustained` i `vats` su tvrda pravila modela, a ne
kategorije. Stižu u `rules_triggered` i dižu crveni alarm modela. Model nema izlaz za
`looking_behind` ni `turning_around`, pa njih za sada šalje samo simulator.

Labele (moraju se poklapati sa `Behavior` u [app/domain/enums.py](app/domain/enums.py)):

| Labela | Značenje | Težina (poena/s) |
|---|---|---|
| `drowsy` | pospan | 2.5 |
| `looking_at_phone` | gleda u telefon | 2.0 |
| `looking_behind` | gleda iza sebe | 2.0 |
| `turning_around` | okreće se telom (obično ide zajedno sa `looking_behind`, pa se sabiraju) | 1.0 |
| `hands_off_wheel` | ruke van volana | 1.0 |
| `eyes_off_road` | pogled van puta (obično ide zajedno sa `looking_at_phone`, pa se sabiraju) | 1.0 |

Više labela u istom ticku je u redu i penali se sabiraju. Novo ponašanje se dodaje na tri mesta:
`Behavior` u `domain/enums.py`, težina u `coordinator/services/scoring.py` i savet u `TIPS` u `domain/tips.py`.
Test će pasti ako nešto od toga fali. Ako se kategorija modela zove drugačije, dodaj je i u `CATEGORY_TO_BEHAVIOR`.

## Za mobilnu aplikaciju

Ceo ugovor (rute, WebSocket poruke, TypeScript tipovi, primeri, pravila prikaza) je u
**[docs/API.md](../docs/API.md)**. To je jedini izvor istine, pa ga ažuriraj kad menjaš rute ili šeme.

## Kako radi koeficijent

Sve se podešava na jednom mestu:
- [app/coordinator/services/scoring.py](app/coordinator/services/scoring.py) (`ScoringConfig`): opasnost ponašanja, kriva brzine, noć, model, brzina pada i oporavka
- [app/domain/levels.py](app/domain/levels.py) (`LEVEL_BANDS`) i [app/coordinator/services/alerts.py](app/coordinator/services/alerts.py) (`POLICIES`): opsezi i reakcija kola po nivou

Score je **trenutno stanje** (koliko je bezbedno SADA), ne bodovni saldo. Po ticku:
- opasnost = najgore ponašanje koje se sada vidi (raste što duže traje) + 30 % ostalih, ili rizik modela (bez mirne
  osnove 0.1, ×0.8) ako je veći
- × **brzina** (< 5 km/h = 0: stoji, nema opasnosti ni upozorenja; 0.4 pri hodu, 1.0 na 50, 1.6 na 130 km/h) × **noć** (22–06h) ×1.25
- cilj = 100 × (1 − opasnost); score ga prati: pada brzo (τ 0.5 s), vraća se za nekoliko sekundi (τ 2.5 s)

`timestamp` mora biti u **lokalnom vremenu sa offsetom** (`safety_client` to radi sam), jer sat iz
njega određuje noć.

| Score | Nivo | Svetlo | Reakcija (samo u pokretu i dok se nešto rizično dešava) |
|---|---|---|---|
| 90–100 | safe | zeleno | – |
| 75–90 | caution | zeleno-žuto | samo svetlo |
| 55–75 | warning | žuto | vibracija + tihi zvuk |
| 35–55 | high_risk | žuto | vibracija + glasan zvuk |
| 10–35 | critical | crveno | vibracija + glasan zvuk |
| < 10 | emergency | crveno | isto; posle 2 s `emergency` događaj i poruka kontaktu (jednom po vožnji) |
| bilo koji | model javi crveno | prati score | vibracija + glasan zvuk odmah (alarm modela) |
| – | stoji (< 5 km/h) | zeleno | ništa, šta god vozač radi |

Slanje poruke kontaktu je za sada stub koji samo loguje: [app/coordinator/services/notifications.py](app/coordinator/services/notifications.py).

## Struktura

```
backend/
  run.py               pokretanje za hotspot (0.0.0.0 + ispis IP adrese)
  app/
    main.py            FastAPI app, CORS, router
    core/config.py     podešavanja iz .env
    api/routes/        HTTP i WebSocket rute (live.py = telemetrija + video + /ws, recording.py = izveštaj, speed.py)
    schemas/           Pydantic modeli (ugovor sa frontom)
    domain/            enumi i stanje vožnje
    services/          scoring, alerts, trips, live (WebSocket), recording (snimanje), speed, video, analytics, notifications
    repositories/      aktivne vožnje u memoriji, Postgres tabele (recordings.py), S3 (media.py)
  scripts/services.ps1 Postgres + RustFS bez Dockera
  docker-compose.yml   Postgres + RustFS sa Dockerom
  tests/
notebooks/
  safety_client.py     most između modela i backenda, plus simulacija vožnje
```
