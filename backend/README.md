# Personal Safety Reviewer – backend (FastAPI)

Računa koeficijent bezbednosti vozača (0–100) iz rezultata modela za kameru i uživo javlja mobilnoj
aplikaciji kako kola treba da reaguju (svetlo na dashboardu, vibracija sedišta, zvuk, poruka kontaktu).
Usput snima vožnju za izveštaj vozaču: grafik po sekundama i video klipove rizičnih momenata.

## Arhitektura

```
 laptop                                                         telefon (hotspot)
┌─────────────────────────────────────────────────────────┐    ┌──────────────────┐
│ notebooks/  YOLO · MediaPipe · OpenCV                   │    │ React Native app │
│     │  safety_client.send_frame(record)        ~2/s     │    │                  │
│     │  safety_client.send_video_frame(frame)   ~8/s     │    │                  │
│     ▼  POST 127.0.0.1:8000/api/v1/telemetry, /video/... │    │                  │
│ backend/  FastAPI ── računa score ── WS /api/v1/ws ─────┼───►│ live dashboard   │
│     │               ◄── POST /trips, /trips/{id}/end ───┼────│ start / kraj     │
│     │               ── /timeline, /events, /media ──────┼───►│ izveštaj, klipovi│
│     ▼  snimanje u pozadini                              │    │                  │
│ Postgres :5433 (uzorci, momenti) · RustFS S3 :9000      │    │                  │
└─────────────────────────────────────────────────────────┘    └──────────────────┘
```

- Modeli i backend rade na **istom laptopu**, pa modeli gađaju `127.0.0.1`.
- Modeli šalju svoj **zapis frejma** (isti kao red u `frames.jsonl`), bez `perception` i nikad
  slike. Backend preslikava aktivne kategorije na labele i iz njih računa score. Rizik i kategorije
  modela prosleđuje aplikaciji u polju `camera`, a crveni alarm modela odmah pali vibraciju i zvuk.
- U jednom trenutku je aktivna **jedna vožnja** (jedan auto). Aplikacija je pokreće i završava,
  a telemetrija modela automatski ide u aktivnu vožnju.
- **Brzinu daje backend**, jer je kamera ne zna: mock vožnja (scenario po vožnji), ili GPS telefona
  ako je uključen (`PHONE_SPEED_ENABLED=true`). Modeli ne šalju brzinu.

## Snimanje vožnje i nalozi (Postgres + RustFS)

Cela struktura baze, šta se šalje frontu i review su u **[docs/DATABASE.md](../docs/DATABASE.md)**.
Dok vožnja traje, backend u pozadini upisuje:

| Tabela / bucket | Šta | Za izveštaj |
|---|---|---|
| `users`, `user_sessions` | nalog (korisničko ime, scrypt heš lozinke, ime, kontakt) i prijave (samo SHA-256 tokena) | ko je vozio |
| `trips` | početak, rezime na ~10 s i konačan na kraju (final/prosek/min score, ponašanja) | istorija, statistika |
| `trip_samples` | **jedan red po sekundi**: brzina, score, nivo, ponašanja, svi brojevi modela (`p`, `p_max`, `r`, `run_s` po kategoriji, `risk`, `alert`, grupe), reakcija kola, GPS | grafici |
| `risk_events` | jedan red po **rizičnom momentu**: ponašanja i koliko su trajala, pad score-a, najveći rizik, brzina, ključevi klipa | "najgore što je uradio" |
| S3 `safety-media/clips/<trip>/<moment>.mp4` + `.jpg` | H.264 klip (3 s pre, 2 s posle) i najrizičniji frejm | video i slika |

- Rizičan momenat: kola se kreću, a vidi se bodovano ponašanje ili je model dao crveni alarm.
  Detekcije razmaknute < 2 s su isti momenat. Klip se pravi za momente od ≥ 1 s (ili sa crvenim alarmom).
- Čitanje: **`GET /trips/{id}/report`** vraća sve o jednoj vožnji (rezime, korisnik, sirovi uzorci za
  grafike, momenti sa slikama i klipovima). Postoje i `/timeline`, `/events`, istorija `GET /trips` i
  klip preko `GET /media/...` (sve u [docs/API.md](../docs/API.md)). Radi i posle restarta backenda.
- Nalozi: `POST /auth/register`, `POST /auth/login` → token (`Authorization: Bearer ...`). Vožnja
  pokrenuta sa tokenom pripada nalogu i vidi je samo on. Bez prijave sve radi kao ranije (`driver_id`).
- Ako Postgres ili S3 nisu podignuti, **score i reakcije kola rade normalno**. Redovi čekaju u memoriji,
  a klipovi se preskaču, uz upozorenje u konzoli.
- Bucket je za demo **javan** (`http://127.0.0.1:9000/safety-media/...`). Kompanija (`/analytics`) slike nikad ne dobija.

Pokretanje servisa (jednom `install`, posle samo `start`):
```powershell
.\scripts\services.ps1 install   # portabl Postgres 18.6 + RustFS 1.0.4 u %LOCALAPPDATA%\safety-reviewer, bez admin prava
.\scripts\services.ps1 start     # Postgres 127.0.0.1:5433, RustFS 127.0.0.1:9000 (konzola :9001, safety / safety-secret)
.\scripts\services.ps1 psql      # SQL nad bazom, npr. select t, speed_kmh, score from trip_samples order by id desc limit 20;
.\scripts\services.ps1 reset     # prazna baza (posle promene tabela, jer migracija još nema)
docker compose up -d             # ili sve ovo sa Dockerom (iste adrese i ključevi)
```
Adrese i ključevi se menjaju u `.env` (primer: [.env.example](.env.example)). `RECORDING_ENABLED=false` gasi snimanje.

## Brzina

| Izvor | Kada |
|---|---|
| GPS telefona (`POST /speed`) | samo uz `PHONE_SPEED_ENABLED=true` i očitavanje mlađe od 5 s |
| `speed_kmh` u ticku | simulator i testovi, da vožnja kroz nivoe bude ista svaki put |
| mock vožnja | sve ostalo: scenario iz [app/services/speed.py](app/services/speed.py), `SPEED_SCENARIO=random` bira po vožnji |

Scenariji: `city` (30–50 km/h, tri semafora), `highway` (do 130), `stop_and_go` (gužva, dugo stajanje),
`country_road` (60–90), `cruise` (nikad ne staje, dobar za demo na bini), `parked` (stalno 0). Između
tačaka je kubna Bezier kriva sa ravnim ručkama: auto glatko ubrzava i koči, a stoji na tačno 0 km/h
(tada nema penala).

## Pokretanje

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python run.py        # za demo preko hotspota, ispisuje adresu za aplikaciju
fastapi dev app/main.py   # samo lokalno, http://127.0.0.1:8000/docs
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

## Za tim sa modelima ([notebooks/safety_client.py](../notebooks/safety_client.py))

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
  Backend drži samo poslednjih par sekundi, a čuva klip samo oko rizičnog momenta.
- Ni jedno ni drugo ne ruši petlju za kameru ako backend nije podignut ili vožnja još nije počela
  (vraća `None` / `False`).
- Ako imate samo labele: `client.send({"looking_at_phone"})`. Za nepoznatu labelu odmah baca `ValueError`.
- Simulacija cele vožnje bez modela, korisno za front: `python notebooks/safety_client.py`
  (sa `--interval 0.3` ide brže od realnog vremena). `--video 0` usput strimuje web kameru (ili
  `--video snimak.mp4`), pa rizični momenti dobijaju klipove. `--backend-speed` prepušta brzinu mock vožnji.
- Replay snimljenog izlaza modela, kao da kamera radi uživo:
  `python notebooks/safety_client.py --replay frames.jsonl` (`--speedup 2`, `--speed-kmh 90`, `--video run.mp4`).

Kategorije modela → labele (`CATEGORY_TO_BEHAVIOR` u [app/services/camera.py](app/services/camera.py)).
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
`Behavior` u `enums.py`, težina u `scoring.py` i savet u `TIPS` u `services/trips.py`.
Test će pasti ako nešto od toga fali. Ako se kategorija modela zove drugačije, dodaj je i u `CATEGORY_TO_BEHAVIOR`.

## Za mobilnu aplikaciju

Ceo ugovor (rute, WebSocket poruke, TypeScript tipovi, primeri, pravila prikaza) je u
**[docs/API.md](../docs/API.md)**. To je jedini izvor istine, pa ga ažuriraj kad menjaš rute ili šeme.

## Kako radi koeficijent

Sve se podešava na jednom mestu:
- [app/services/scoring.py](app/services/scoring.py) (`ScoringConfig`): težine ponašanja, množioci za brzinu i noć, oporavak
- [app/services/alerts.py](app/services/alerts.py) (`LEVEL_BANDS`, `POLICIES`): opsezi i reakcija kola po nivou

Po ticku:
- svako vidljivo ponašanje skida `težina × sekunde` poena, plus jednokratni udar kad počne (pada brzo na početku)
- penal se množi sa: **brzinom** (< 5 km/h = 0, grad 1.0, vangradski 1.3, autoput 1.7), **noć** (22–06h) ×1.5,
  i **krhkošću** `1 + (100 − score)/100` (što je niži, lakše pada)
- posle 30 s čiste vožnje score raste 3 poena u minutu

`timestamp` mora biti u **lokalnom vremenu sa offsetom** (`safety_client` to radi sam), jer sat iz
njega određuje noćne penale.

| Score | Nivo | Svetlo | Reakcija na rizično ponašanje (samo u pokretu) |
|---|---|---|---|
| 90–100 | safe | zeleno | – |
| 75–90 | caution | zeleno-žuto | vibracija ako traje ≥ 5 s |
| 55–75 | warning | žuto | vibracija + tihi zvuk, ≥ 5 s |
| 35–55 | high_risk | žuto | vibracija + glasan zvuk, ≥ 2 s |
| 10–35 | critical | crveno | vibracija + glasan zvuk odmah |
| < 10 | emergency | crveno | + `emergency` događaj i poruka kontaktu (jednom po vožnji) |
| bilo koji | model javi crveno | prati score | vibracija + glasan zvuk odmah (alarm modela) |

Slanje poruke kontaktu je za sada stub koji samo loguje: [app/services/notifications.py](app/services/notifications.py).

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
