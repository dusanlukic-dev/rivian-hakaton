# Backend (FastAPI): koordinator + server

Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg), boto3, diskcache, Pillow. Zavisnosti su u
`requirements.txt`, a virtuelno okruženje u `.venv/`.

Backend ima **dva dela** sa jasnom granicom. Celu sliku (tok podataka, ugovori, keš, pouzdanost) vidi u
**`../docs/ARCHITECTURE.md`**:
- `app/coordinator/`: **koordinator**, u kolima. WebSocket za telefon i dashboard, kamera, veza sa modelom,
  izdvojen `RiskEngine` CV tima, score 0–100 i reakcija kola, 5 min video keša, sekcije od 2 s koje šalje
  serveru i telefonu. **Nikad ne dira Postgres ni S3.**
- `app/server/`: **server**. Nalozi, prijem sekcija od koordinatora (`/internal/*`), Postgres + S3,
  istorija, izveštaj sa grafikom i slikama, analitika. Ne zna ništa o kameri, modelu ni WS-u.
- `app/domain/`, `app/schemas/`, `app/core/`: zajedničko (enumi, nivoi, saveti, ko šta vidi, ugovori, podešavanja).

Koordinator serveru pristupa **samo preko HTTP-a** (`coordinator/services/server_client.py`): u jednom
procesu kroz `httpx.ASGITransport` (bez socket-a), a odvojeno preko `SERVER_URL`. Ne uvozi ništa iz
`app/server/`, a server ništa iz `app/coordinator/`.

## Komande (iz `backend/`, Windows)

```powershell
.venv\Scripts\activate                      # prvi put: python -m venv .venv; pip install -r requirements.txt
docker compose up -d                        # Postgres 127.0.0.1:5433 + RustFS (S3) 127.0.0.1:9000 (konzola :9001)
.\scripts\services.ps1 start                # ...isto bez Docker-a (portabl, jednom `install`)
python run.py                               # koordinator + server na 0.0.0.0:8000 + ispis IP-a za telefon (reload)
python run.py --role server --port 8001     # odvojeno: server...
$env:SERVER_URL="http://127.0.0.1:8001/api/v1"; python run.py --role coordinator   # ...i koordinator
pytest                                      # testovi (SQLite + S3 i video keš u memoriji, ne trebaju servisi)
python ..\tools\camera_stream.py            # kamera: test slika (--video snimak.mp4, --webcam "ime")
python ..\model\worker.py --fake            # model worker bez CV paketa (pravi: ../model/README.md)
python ..\notebooks\safety_client.py --interval 0.3   # simulirana vožnja bez kamere i modela
curl http://127.0.0.1:8000/api/v1/coordinator/status  # kamera, model, keš, isporuka serveru
```

## Slojevi

**Koordinator** (`app/coordinator/`):
- `routes/`: tanke rute. `live.py`: `WS /ws` (telefon), `POST /telemetry` (samo debug: simulator, `--mode prod`;
  zapis frejma `409` dok je model worker povezan), `POST /video/frames`,
  `WS /camera/ws` (kamera). `model.py`: `WS /model/ws` (model worker). `trips.py`: start, kraj, živo stanje.
  `speed.py`: `GET/POST /speed`. `status.py`: `GET /coordinator/status`.
- `services/coordinator.py`: **`Coordinator`**, ceo živi tok na jednom mestu: tick → brzina → score →
  `state` (~2/s) → sekcija → slika iz keša → WS `section` + outbox. Frejm → keš + model. Detekcija →
  `RiskEngine` → tick.
- `services/risk_engine.py`: `RiskEngine` CV tima, **izdvojen** iz `notebooks/risk_pipeline.py` bez izmena
  matematike (`tests/test_risk_engine.py` poredi sa originalom). Pragovi: `notebooks/risk_config.json`.
- `services/model_link.py`: veza sa model worker-om (protokol, jedan frejm u letu, najnoviji pobeđuje).
- `services/sections.py`: `SectionRecorder`, tickovi → sekcije od 2 s, opasnost, najrizičniji frejm.
- `services/video_cache.py`: `VideoCache`, 5 min frejmova (diskcache na disku ili memorija).
- `services/outbox.py` + `server_client.py`: isporuka serveru, redom, ponavlja dok server ne odgovori.
- `services/scoring.py`, `alerts.py`, `camera.py`, `speed.py`, `trips.py`, `live.py`, `notifications.py`:
  score, nivoi i reakcija, preslikavanje kategorija modela, brzina (mock), stanje vožnje, WS hub, SMS stub.
- `repositories/trips.py`: aktivne vožnje u memoriji.

**Server** (`app/server/`):
- `routes/`: `auth.py` (`/auth/*`), `history.py` (`GET /trips`, `/summary`, `/report`, `/sections`),
  `media.py` (`/media/{key}`, `Range`), `analytics.py`, `internal.py` (`/internal/*`, `X-Internal-Token`).
- `services/storage.py`: `TripStore`, prijem paketa (slike u S3 pa redovi u Postgres) i čitanja.
- `services/history.py`: istorija, rezime, izveštaj, **momenti** (`build_moments`). `auth.py`: nalozi.
- `repositories/`: `database.py` (engine, šema, SQLite redom), `users.py`, `recordings.py` (`trips`,
  `trip_sections`), `media.py` (S3, `MemoryMediaStore` za testove). Struktura: `../docs/DATABASE.md`.

**Zajedničko:** `app/services/model_report.py` (CV tim): izveštaj modela kamere za celu vožnju (rizik, vreme po
boji alarma, epizode ponašanja i alarma) iz toka frejmova. Koordinator ga hrani svakim tickom i šalje snimak uz
svaku sekciju (`RunningSummary.model_report` → `trips.model_report` → `TripReport.model`). Samo standardna
biblioteka, pa ga uvozi i dev mode pipeline-a; offline: `python -m app.services.model_report frames.jsonl`.
**Ne pomeraj ga** (dev mode ga uvozi po toj putanji).

**Spajanje:** `app/main.py` pravi aplikaciju za ulogu `all` / `coordinator` / `server` (rute + lifespan).
`app/coordinator/main.py` i `app/server/main.py` su odvojeni ulazi.

## Gde šta

| Hoćeš da... | Fajl |
|---|---|
| podesiš penale, brzinu, noć, oporavak | `ScoringConfig` u `coordinator/services/scoring.py` |
| promeniš opsege ili reakciju kola | `LEVEL_BANDS` u `domain/levels.py`, `POLICIES` u `coordinator/services/alerts.py` |
| dodaš ponašanje | `Behavior` u `domain/enums.py`, `_default_weights` u `scoring.py`, `TIPS` u `domain/tips.py`, `BEHAVIORS` u `notebooks/safety_client.py`, `docs/API.md` |
| preslikaš kategoriju modela na labelu | `CATEGORY_TO_BEHAVIOR` u `coordinator/services/camera.py` |
| promeniš dužinu sekcije ili pravila opasnosti | `SECTION_S` u `.env`, `tick_danger` u `coordinator/services/sections.py` |
| promeniš video keš | `VIDEO_CACHE*` u `core/config.py`, `coordinator/services/video_cache.py` |
| promeniš protokol sa modelom | `coordinator/services/model_link.py` **i** `../model/worker.py` |
| promeniš šta koordinator šalje serveru | `schemas/sync.py`, `coordinator/services/outbox.py`, `server/routes/internal.py`, `server/services/storage.py` |
| dodaš kolonu u sekciju | `SectionBase` u `schemas/report.py`, `_close` u `sections.py`, `SectionRow` u `server/repositories/recordings.py`, `docs/API.md` §4, `docs/DATABASE.md`, pa prazna baza |
| promeniš momente | `build_moments` u `server/services/history.py` |
| podesiš izveštaj modela (min. epizoda, spajanje, uzroci alarma) | `ModelReportConfig` u `app/services/model_report.py` |
| promeniš šta od frejma modela ide aplikaciji | `CameraView` u `domain/trip.py`, `to_view` u `coordinator/services/camera.py`, ulaz u `schemas/camera.py`, `docs/API.md` |
| promeniš alarm modela | `evaluate_response` i `CAMERA_ALARM_MESSAGE` u `coordinator/services/alerts.py` |
| dodaš ili promeniš scenario brzine | `SCENARIOS` / `RANDOM_POOL` u `coordinator/services/speed.py` (test proverava glatkoću i petlju) |
| dodaš WebSocket događaj | `LiveEvent` u `domain/enums.py`, `hub.broadcast` u `Coordinator`, `LiveMessage` u `docs/API.md` |
| promeniš adresu ili ključeve Postgresa / S3, token za `/internal` | `Settings` u `core/config.py`, `.env` (primer: `.env.example`) |
| pravi SMS ili push | `coordinator/services/notifications.py` (sada stub) |
| promeniš nalog ili ko šta vidi | `server/services/auth.py`, `schemas/auth.py`, `domain/access.py` |

## Zamke

- Rute koje menjaju stanje (`POST /trips`, `/telemetry`, `/video/frames`, `/speed`, `/trips/{id}/end`) i
  WS petlje su `async`, pa se izvršavaju redom na event loop-u i nema trka nad stanjem u memoriji.
  **Ne prebacuj ih u `def`**, jer bi tada radile paralelno u threadpool-u.
- **Živi tok nikad ne čeka server.** `ServerOutbox` dira samo memoriju; isporuku radi jedan pozadinski task,
  jedan zahtev u letu, pa sekcije stižu redom. Paket je idempotentan (ključ sekcije pravi koordinator), pa se
  posle greške samo ponovi. Izuzetak: `POST /trips/{id}/end` čeka do 3 s da server primi sve (izveštaj odmah
  posle kraja je ceo). Dok je server dole, End ne čeka.
- **Model detekcije stižu 5–10/s, a telefon reaguje na svaku `state` poruku** (vibracija, zvuk). Zato
  koordinator detekcije šalje telefonu na 0.5 s (`LIVE_STATE_INTERVAL_S`), ali odmah na promenu nivoa,
  reakcije, ponašanja ili alarma modela. `POST /telemetry` (simulator) ide i dalje posle svakog ticka.
- MediaPipe u VIDEO modu traži strogo rastuće vreme, pa worker na novoj vožnji ne vraća sat na nulu nego
  nastavlja (`_base_ms`); `FeatureExtractor` (kalibracija pogleda) se pravi ispočetka.
- Video keš je temp folder koji se **briše na svakom startu** (id-jevi frejmova kreću od 1). Upis na disk ide
  kroz jednu nit; frejm koji je model analizirao se uvek upiše (može postati slika sekcije).
- `pydantic.Base64Bytes` dekodira base64 i kad mu se u Pythonu da sirov JPEG (iskvari sliku). Zato
  `SectionIn.image_jpeg` koristi `JpegBytes` iz `schemas/report.py`: sirovi bajtovi u Pythonu, base64 u JSON-u.
- FastAPI 0.162 uključuje routere lenjo (`app.routes` sadrži `_IncludedRouter`), pa spisak ruta gledaj u
  `app.openapi()["paths"]`. WebSocket rute tamo nisu.
- **Windows + `--reload`:** kad se ubije samo uvicorn reloader (ili mu se ugasi konzola), njegov worker
  (`python -c "from multiprocessing.spawn import ..."`) ostane živ i **i dalje drži port 8000** (Windows dozvoljava
  dva socket-a na istom portu). Tada stari kod nastavlja da odgovara, a novi se ne vidi. Ubij celo stablo
  (`taskkill /T /F /PID <reloader>`) i proveri `Get-NetTCPConnection -LocalPort 8000`.
- `Database.ensure_schema()` pravi tabele samo jednom (zaključano). SQLite (testovi) je jedna konekcija, pa
  `Database` pušta korisnike redom. Postgres ima pool i radi paralelno.
- Na startu koordinator traži od servera `close-interrupted` (preko outbox-a, ponavlja dok server ne odgovori),
  pa vožnje koje je pad ostavio otvorene dobijaju `ended_at` na poslednjem rezimeu.
- Nalozi: heširanje lozinke (scrypt, ~50 ms) ide u `asyncio.to_thread`, nikad na event loop. Loš token je 401
  i tamo gde je login opcion. Tuđa vožnja je 404, ne 403. Koordinator proverava token pitajući server
  (`GET /auth/me`) i pamti odgovor 30 s; ako server ne odgovara, `POST /trips` sa tokenom je 503.
- Redosled sa jednakim vrednostima (dva ponašanja po 3,0 s) je abecedni, inače zavisi od iteracije kroz `set`.
- Postgres je na **5433**, jer na ovom laptopu sistemski PostgreSQL 18 servis drži 5432.
- Tabele pravi `create_all` na startu servera. Migracija nema, pa posle promene modela: prazna baza
  (`.\scripts\services.ps1 reset` ili `docker compose down -v`).
- `services.ps1` pokreće servere preko `Start-Process` bez preusmeravanja izlaza. Server sa preusmerenim
  izlazom nasledi handle-ove shell-a, pa poziv (i agent) visi. RustFS 1.0.4: `--console-enable` je flag
  bez vrednosti.
- boto3: path-style adrese i `request_checksum_calculation="when_required"`, jer novi boto3 dodaje CRC
  checksum koji ne prihvata svaki S3 klon.
- Slike aplikacija dobija preko `GET /api/v1/media/...` (port 8000, podržava `Range`), a ne direktno sa
  9000: Windows firewall i IP hotspota.
- Svaki `Behavior` mora imati težinu i `TIPS` savet. Test `test_every_behavior_has_a_weight_and_a_tip` to proverava.
- `timestamp` u ticku je lokalno vreme sa offsetom. Sat iz njega određuje noćne penale. Za detekcije modela
  koordinator pravi timestamp iz vremena kad je frejm stigao (`_local_time`). Razmak između tickova je
  ograničen na 5 s. Mock brzina i ose grafika (`t`) idu po satu tickova; video keš po satu servera (`time.monotonic`).
- Ispod 5 km/h: nema penala, nema oporavka, nema upozorenja, ne ulazi u statistiku i sekcija nije opasna.
- Tick može imati `behaviors` (labele), `frame` (zapis modela) ili oba, a labele se spajaju.
  `ModelFrame` deklariše samo polja koja koristimo. NaN/inf iz modela postaju `null`.
- `trip.camera` se postavlja na svaki tick. Tick bez `frame` ga briše, da crveni alarm modela ne ostane zaglavljen.
- Kategorija modela koja nije u `CATEGORY_TO_BEHAVIOR` ide aplikaciji, ali se ne boduje (jedan warning).
- WebSocket se ne vidi u OpenAPI-ju ni na `/docs`, pa se dokumentuje ručno (`docs/API.md`, `docs/ARCHITECTURE.md`).
- Izveštaj modela (`trips.model_report`) koristi `t`/`dt` po satu tickova (ista osa kao sekcije), ne `t`
  modela. `peak_p` je najveće sirovo `p` među primljenim frejmovima, jer `p_hat` ne stiže do koordinatora.
- Testovi: `tests/conftest.py` daje `client` sa svežim koordinatorom (`make_coordinator`: `FakeClock`, video keš
  u memoriji, risk config iz `notebooks/`, bez pozadinskog housekeeping-a) i serverom (`store`: SQLite u
  memoriji + `MemoryMediaStore`). `flush(client, coordinator)` čeka da outbox isporuči sve serveru. Restart se
  simulira sa dva `app_client` nad istim SQLite fajlom. `test_model_link.py` glumi model worker preko WS-a.
- Windows Firewall blokira konekcije sa hotspota ako Python nije dozvoljen i na **Public** mrežama.
  Komanda za to je u `README.md`. Postgres i RustFS slušaju samo na 127.0.0.1, model se javlja na 8000.
