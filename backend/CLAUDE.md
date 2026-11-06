# Backend (FastAPI)

Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg), boto3. Zavisnosti su u `requirements.txt`,
a virtuelno okruženje u `.venv/`.

## Komande (iz `backend/`, Windows)

```powershell
.venv\Scripts\activate                      # prvi put: python -m venv .venv; pip install -r requirements.txt
.\scripts\services.ps1 install              # jednom: portabl Postgres 18.6 + RustFS 1.0.4 (~450 MB), bez admin prava
.\scripts\services.ps1 start                # Postgres 127.0.0.1:5433 + RustFS (S3) 127.0.0.1:9000, konzola :9001
.\scripts\services.ps1 status               # ...ili stop | psql (SQL nad bazom) | reset (prazna baza)
docker compose up -d                        # isto to, ali sa Dockerom (docker-compose.yml)
python run.py                               # 0.0.0.0:8000 + ispis IP-a za telefon (auto-reload)
fastapi dev app/main.py                     # samo lokalno, http://127.0.0.1:8000/docs
pytest                                      # testovi (SQLite + S3 u memoriji, ne trebaju servisi)
python ..\notebooks\safety_client.py --interval 0.3   # simulirana vožnja (server mora da radi)
python ..\notebooks\safety_client.py --video 0        # ...i web kamera: rizični momenti dobijaju klipove
python ..\notebooks\safety_client.py --replay frames.jsonl --speedup 2   # snimljen izlaz modela
```

## Slojevi

- `app/api/routes/`: tanke rute. Samo HTTP (status kodovi, 404/409/503), poziv servisa i slanje
  događaja preko `hub.broadcast`. `live.py`: `POST /telemetry`, `POST /video/frames`, `WS /ws`.
  `recording.py`: `GET /trips/{id}/report` (sve o vožnji), `/timeline`, `/events`, `/media/{key}`.
  `auth.py`: `/auth/register`, `/login`, `/logout`, `/me`. `speed.py`: `GET/POST /speed`.
  `deps.py`: `OptionalUser` (token nije obavezan, ali loš token je 401), `CurrentUser`, `VisibleTripDep`.
- `app/schemas/`: Pydantic modeli, odnosno ugovor sa frontom. Svaku promenu prenesi u `../docs/API.md`.
- `app/domain/`: enumi (`Behavior`, `SafetyLevel`, `LiveEvent`, `SpeedSource`...) i `Trip` dataclass (interno stanje).
- `app/services/`: sva logika, bez FastAPI-ja (osim `live.py`, koji drži WebSocket konekcije).
  - `recording.py`: `TripRecorder` snima vožnju pored živog toka: uzorke po 1 s, rizične momente i
    klipove. Rute zovu samo memorijske hook-ove (`trip_started`, `on_tick`, `on_video_frame`,
    `trip_ended`), a pozadinski task piše u Postgres svake 2 s.
  - `auth.py`: nalozi. scrypt heš u pozadinskoj niti, nasumični token (u bazi samo SHA-256), 30 dana.
  - `history.py`: istorija, statistika i izveštaj (živa vožnja iz memorije, ostalo iz Postgresa) i
    pravilo vidljivosti `can_see` (vožnju sa nalogom vidi samo vlasnik).
  - `speed.py`: brzina, redom telefon > tick > mock scenario (kubna Bezier kriva između tačaka).
  - `video.py`: JPEG frejmovi → MP4 H.264 (ffmpeg dolazi u `imageio-ffmpeg` wheel-u).
  - `model_report.py`: izveštaj modela kamere za celu vožnju (rezime rizika, vreme po boji alarma,
    epizode ponašanja i alarma) iz toka frejmova. Pipeline to više ne radi. Samo standardna biblioteka,
    pa ga uvozi i dev mode pipeline-a. Offline: `python -m app.services.model_report frames.jsonl`.
- `app/repositories/trips.py`: aktivne vožnje u memoriji (`add/get/active/list`).
- `app/repositories/database.py`: `Database` (engine, pravljenje šeme, SQLite redom), `get_database()`.
  `users.py`: tabele `users`, `user_sessions`. `recordings.py`: `trips`, `trip_samples`, `risk_events`.
  `media.py`: S3 (boto3) i `MemoryMediaStore` za testove. Struktura i review: `../docs/DATABASE.md`.

## Gde šta

| Hoćeš da... | Fajl |
|---|---|
| podesiš penale, brzinu, noć, oporavak | `ScoringConfig` u `app/services/scoring.py` |
| promeniš opsege ili reakciju kola | `LEVEL_BANDS` / `POLICIES` u `app/services/alerts.py` |
| dodaš ponašanje | `Behavior` u `app/domain/enums.py`, `_default_weights` u `scoring.py`, `TIPS` u `app/services/trips.py`, `BEHAVIORS` u `notebooks/safety_client.py`, `docs/API.md` |
| preslikaš kategoriju modela na labelu | `CATEGORY_TO_BEHAVIOR` u `app/services/camera.py` |
| promeniš šta od frejma modela ide aplikaciji | `CameraView` u `app/domain/trip.py`, `to_view` u `app/services/camera.py`, ulaz u `app/schemas/camera.py`, `docs/API.md` |
| promeniš alarm modela | `evaluate_response` i `CAMERA_ALARM_MESSAGE` u `app/services/alerts.py` |
| dodaš WebSocket događaj | `LiveEvent` u `enums.py`, `hub.broadcast` u ruti, `LiveMessage` u `docs/API.md` |
| podesiš snimanje (prozor, spajanje momenata, dužina klipa) | `RecordingConfig` u `app/services/recording.py` |
| podesiš izveštaj modela (min. epizoda, spajanje, uzroci alarma) | `ModelReportConfig` u `app/services/model_report.py` |
| dodaš ili promeniš scenario brzine | `SCENARIOS` / `RANDOM_POOL` u `app/services/speed.py` (test proverava glatkoću i petlju) |
| dodaš kolonu u izveštaj | model u `app/repositories/recordings.py`, `_Window.row` / `_Event.row` u `recording.py`, `app/schemas/recording.py`, `docs/API.md`, pa `services.ps1 reset` |
| promeniš adresu ili ključeve Postgresa / S3 | `Settings` (`DATABASE_URL`, `S3_*`) u `app/core/config.py`, `.env` (primer: `.env.example`) |
| pravi SMS ili push | `app/services/notifications.py` (sada stub) |
| promeniš nalog (polja, trajanje tokena, pravila za ime/lozinku) | `UserRow` u `app/repositories/users.py`, `app/services/auth.py`, `app/schemas/auth.py`, `docs/API.md` |
| promeniš ko šta vidi | `can_see` u `app/services/history.py` |
| novo podešavanje | `Settings` u `app/core/config.py` i `.env` |

## Zamke

- Rute koje menjaju stanje (`POST /trips`, `/telemetry`, `/video/frames`, `/speed`, `/trips/{id}/end`) su
  `async def`, pa se izvršavaju redom na event loop-u i nema trka nad deljenim in-memory stanjem.
  **Ne prebacuj ih u `def`**, jer bi tada radile paralelno u threadpool-u.
- **Snimanje nikad ne blokira živi tok.** Hook-ovi `TripRecorder`-a rade samo u memoriji. Postgres i S3
  zovu samo pozadinski task, taskovi za klipove i rute za čitanje. Ako su dole, score radi, redovi čekaju
  u memoriji (do 20 000), a u logu je jedno upozorenje i jedna poruka kad se vrate.
- `Database.ensure_schema()` pravi tabele samo jednom (zaključano), jer su provera na startu i prvi zahtev
  paralelno radili `CREATE TABLE` (test je padao 4/25 puta). SQLite (testovi) je jedna konekcija, pa
  `Database` pušta njegove korisnike redom. Postgres ima pool i radi paralelno.
- `TripRecorder._flush_lock` drži pakete upisa u redosledu (red `trips` mora pre uzoraka, zbog FK).
- Rute za čitanje (`/report`, `/timeline`, `/events`, istorija) prvo upišu red čekanja (izveštaj
  sačeka i klipove u izradi), pa vide sve do tog trenutka. Poslednja, nezavršena sekunda aktivne
  vožnje još nije u bazi.
- Rezime vožnje se upisuje u `trips` na ~10 s (`summary_interval_s`), a na startu se vožnje bez
  `ended_at` (osim onih koje ovaj proces vozi) zatvaraju na poslednjem upisu. Zato pad servera ne
  ostavlja "večno aktivne" vožnje.
- Nalozi: heširanje lozinke (scrypt, ~50 ms) ide u `asyncio.to_thread`, nikad na event loop, jer bi
  zaustavilo živi score. Loš token je 401 i tamo gde je login opcion. Tuđa vožnja je 404, ne 403.
- Redosled sa jednakim vrednostima (dva ponašanja po 3,0 s) je abecedni. Inače zavisi od redosleda
  iteracije kroz `set`, koji se menja od pokretanja do pokretanja (test je padao 9/20).
- Postgres je na **5433**, jer na ovom laptopu sistemski PostgreSQL 18 servis (`postgresql-x64-18`) drži 5432.
- Tabele pravi `create_all` na startu. Migracija nema, pa posle promene modela: `.\scripts\services.ps1 reset`.
- `services.ps1` pokreće servere preko `Start-Process` bez preusmeravanja izlaza. Server sa preusmerenim
  izlazom nasledi handle-ove shell-a, pa poziv (i agent) visi. RustFS 1.0.4: `--console-enable` je flag
  bez vrednosti. Sa `true` iza njega `true` čita kao drugi disk i ne startuje.
- boto3: path-style adrese i `request_checksum_calculation="when_required"`, jer novi boto3 dodaje CRC
  checksum koji ne prihvata svaki S3 klon.
- Klipove aplikacija dobija preko `GET /api/v1/media/...` (port 8000, podržava `Range`), a ne direktno sa
  9000: Windows firewall i IP hotspota. Bucket je ipak javan (za demo, `S3_PUBLIC_READ`).
- Svaki `Behavior` mora imati težinu i `TIPS` savet. Test `test_every_behavior_has_a_weight_and_a_tip`
  to proverava.
- `timestamp` u ticku je lokalno vreme sa offsetom. Sat iz njega određuje noćne penale. Razmak između
  tickova je ograničen na 5 s. Mock brzina i ose izveštaja (`t`) idu po satu tickova, a isecanje klipa
  po satu servera (`time.monotonic`), jer video stiže nezavisno od tickova.
- Ispod 5 km/h: nema penala, nema oporavka, nema upozorenja, ne ulazi u statistiku i nije rizičan momenat.
- U memoriji je samo stanje aktivne vožnje. Istorija, statistika, izveštaj i nalozi (i tokeni) su u
  Postgresu, pa prežive restart. Prijavljen korisnik ostaje prijavljen i posle restarta.
- Tick može imati `behaviors` (labele), `frame` (zapis modela) ili oba, a labele se spajaju.
  `ModelFrame` deklariše samo polja koja koristimo, a ostala (`perception`, `p_hat`, `D_s`...)
  Pydantic ignoriše. NaN/inf iz modela postaju `null`, jer bi inače pokvarili `JSON.parse` u aplikaciji.
- `trip.camera` se postavlja na svaki tick. Tick bez `frame` ga briše, da crveni alarm modela ne
  ostane zaglavljen.
- Kategorija modela koja nije u `CATEGORY_TO_BEHAVIOR` ide aplikaciji, ali se ne boduje, i jednom
  se loguje warning u konzoli servera.
- WebSocket se ne vidi u OpenAPI-ju ni na `/docs`, pa se dokumentuje ručno u `docs/API.md`.
- Izveštaj modela (`trips.model_report`) koristi `t`/`dt` po satu tickova (ista osa kao `samples`), ne `t`
  modela. `peak_p` je najveće sirovo `p` među primljenim frejmovima (~2/s), jer `p_hat` ne stiže na backend.
- Testovi: `tests/conftest.py` daje `client` sa svežim repo/hub-om, in-memory SQLite umesto Postgresa
  (`db`), `MemoryMediaStore`, `FakeClock`, `SpeedService(scenario="city")` i `AuthService`, plus
  pomoćne `register()` i `bearer()`. Koristi `with TestClient(app)`, da HTTP, WebSocket i recorder dele
  isti event loop. Upit nad bazom iz testa: `client.portal.call(recorder.flush)`, pa
  `client.portal.call(recorder.repo.trip, trip_id)`. Restart se simulira sa dva `app_client` nad istim
  SQLite fajlom (`test_running_summary_and_restart`). Lifespan uzima bazu, recorder i brzinu preko
  `app.dependency_overrides`, kao i rute.
- Windows Firewall blokira konekcije sa hotspota ako Python nije dozvoljen i na **Public** mrežama.
  Komanda za to je u `README.md`. Postgres i RustFS slušaju samo na 127.0.0.1, pa im pravilo ne treba.
