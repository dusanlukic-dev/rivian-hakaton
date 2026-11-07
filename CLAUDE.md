# Personal Safety Reviewer: Rivian hakaton

Tim komunicira na srpskom (latinica). Kod, identifikatori, API i labele su na engleskom.

## Ideja

Kamera u kabini prati vozača. Backend računa **koeficijent pažnje 0–100** (100 = potpuno usredsređen,
0 = opasnost po život), a kola reaguju: svetlo na dashboardu, vibracija sedišta, zvučni signal, poruka
kontaktu za hitne slučajeve. Na kraju vožnje vozač dobija statistiku, savete i izveštaj: grafik vožnje
sa opasnim delovima i slikom najopasnijih momenata. Kompanija vidi samo koeficijente i vrste grešaka, **nikad
slike** (privatnost).

## Delovi repoa

| Putanja | Šta je |
|---|---|
| `backend/` | FastAPI u dva dela: **koordinator** (`app/coordinator/`, u kolima: uživo, kamera, model, score, sekcije) i **server** (`app/server/`: nalozi, čuvanje, izveštaj). Detalji u `backend/CLAUDE.md` |
| `backend/docker-compose.yml` | Postgres + RustFS (S3) za server. Bez Docker-a: `backend/scripts/services.ps1` (portabl) |
| `rivian_model/` | **model** (Dušan): svoj proces i okruženje (`.venv`, kasnije Docker), prima frejmove od koordinatora i vraća dokaz po kategoriji (`phone_use`, `eyes_off_road`, `eyes_closed`, `collapse`). YOLO11n + YOLO11n-pose + MediaPipe lice. Uputstvo: `rivian_model/README.md` |
| `tools/camera_stream.py` | kamera za demo: snimak, test slika ili web kamera → koordinator |
| `demo.ps1` | ceo auto na laptopu (skladište, server, koordinator, Bluetooth, model, kamera), svaki deo u svom prozoru |
| `notebooks/risk_config.json` | pragovi koordinatorovog `RiskEngine`-a (kategorije, pravila, alarm) |
| `notebooks/safety_client.py` | simulator cele vožnje (labele na `/telemetry`, bez kamere i modela) |
| `frontend/mobile/` | Expo (SDK 58) Android aplikacija za vozača, dev build. Pravila: `.claude/rules/mobile.md` |
| `frontend/dashboard/` | web mock ekrana u kolima (Vite + React). Pravila: `.claude/rules/dashboard.md` |
| `docs/ARCHITECTURE.md` | **koordinator, server i model**: tok podataka, ugovori između delova, keš, pouzdanost |
| `docs/API.md` | **ugovor backend ↔ aplikacija, izvor istine.** Pročitaj ga pre bilo kakvog rada na frontendu |
| `docs/DATABASE.md` | struktura baze (nalozi, vožnje, sekcije od 2 s, slike), šta se šalje frontu, review |
| `PROGRESS.md` | stanje projekta, bagovi, sledeći koraci. Pročitaj na početku, ažuriraj na kraju |
| `.claude/` | pravila, skillovi i knowledge za agente (frontend, alati, mreža, Android). Indeks: `.claude/CLAUDE.md` |

## Arhitektura i mreža

Celo objašnjenje: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

```
laptop: kamera (tools/camera_stream.py) ──WS 127.0.0.1:8000/api/v1/camera/ws (JPEG, ~10 fps)──► KOORDINATOR
        model (rivian_model/)           ◄─WS 127.0.0.1:8000/api/v1/model/ws: frejm → dokaz po kategoriji─►
        debug: simulator                ──POST /api/v1/telemetry (labele ili snimljen zapis modela)──────►
        KOORDINATOR ──POST /api/v1/internal/trips/{id}/sync (sekcije od 2 s + slike)──► SERVER
        SERVER ──► Postgres 127.0.0.1:5433 (nalozi, vožnje, sekcije) + RustFS S3 127.0.0.1:9000 (slike)
telefon (hotspot): React Native app ◄──WS /api/v1/ws: state ~2/s, emergency, section na 2 s── KOORDINATOR
                                    ──REST /auth, /trips (start, kraj [K]; istorija, izveštaj [S]), /media [S]──►
```

- Za demo **nema servera ni DNS-a**. Laptop pokreće backend (koordinator + server u jednom procesu,
  port 8000), kameru i model, telefon pravi hotspot, a laptop je povezan na njega. Aplikacija gađa IP
  laptopa, koji `python backend/run.py` ispiše pri pokretanju. IP se menja pri svakom ponovnom povezivanju.
- **U kolima:** kamera, model i koordinator. **Van kola:** server (istorija i zapisi vožnji). Sav keš je u
  koordinatoru, a Postgres i RustFS su samo serverovi. Vožnja nikad ne čeka server.
- **Pravi put:** kamera → koordinator → model → koordinator (rizik, score, reakcija). Simulator i snimljeni
  zapisi modela (`POST /telemetry`) su **samo debug**; zapis frejma na `/telemetry` dobija `409` dok je model
  povezan. Koordinator prima **jednu kameru** (druga je odbijena: HTTP 403), jer model pamti stanje vožnje.
- **Jedan auto = jedna aktivna vožnja.** Detekcije i telemetrija idu u aktivnu vožnju, a nova vožnja
  završava prethodnu.
- **Koordinator** prima video, šalje frejmove modelu, od dokaza modela računa rizik (`RiskEngine`,
  `backend/app/coordinator/services/risk_engine.py`), pa naš score i reakciju kola. Telefonu
  šalje stanje i na svake 2 s **sekciju** (šta je viđeno, score, opasnost). Drži 5 min videa u kešu i za
  opasnu sekciju uzima sliku najrizičnijeg frejma. Sekcije sa slikama šalje serveru. Nikad ne dira bazu.
- **Server** čuva naloge, vožnje, sekcije i slike i služi istoriju i izveštaj (grafik vožnje sa opasnim
  momentima). Ne zna ništa o kameri.
- **Model** samo detektuje (`rivian_model/rivian_detector.py`: YOLO11n telefon, YOLO11n-pose, MediaPipe lice,
  pravila u `features.py`). Ne računa rizik ni score. Zona vozača zavisi od kamere (`--camera 05_23|08_14`).
- Ako server, Postgres ili S3 ne rade, score i reakcije kola rade normalno, a sekcije čekaju u koordinatoru.

## Pravila domena (sažetak)

- Labele: `looking_at_phone`, `looking_behind`, `turning_around`, `hands_off_wheel`, `drowsy`,
  `eyes_off_road`, `collapse`.
- **Kolaps** (vozač pao napred i miruje) nije stepen opasnosti nego hitan slučaj: kad traje 2 s, score je odmah
  0, svetlo crveno, glasan alarm i poruka kontaktu, **i kad kola stoje**; drži se 10 s posle poslednjeg viđenja.
  Kraći pad (saginjanje) ne skida poene.
- **Score je trenutno stanje, ne bodovni saldo** (`coordinator/services/scoring.py`): koliko je vožnja bezbedna
  SADA. Pada dok traje rizično ponašanje i vraća se na 100 čim prestane (~6–8 s).
  - opasnost sada = najgore ponašanje (raste što duže traje) + 30 % ostalih; ili rizik modela (bez mirne
    osnove 0.1, ×0.8) ako je veći;
  - **brzina je pojačivač**: < 5 km/h = 0 (stoji: nema opasnosti ni upozorenja, šta god vozač radi), 0.4 pri
    hodu, 1.0 na 50 km/h, 1.6 na 130 km/h; noć (22–06h) ×1.25;
  - cilj = 100 × (1 − opasnost × brzina), score ga prati: pada brzo (τ 0.5 s), raste malo sporije (τ 2.5 s).
- Kalibracija (dan): dug pogled u telefon je `critical` u gradu, a `emergency` od ~70 km/h; mikrospavanje u
  brzini je `emergency`; ruke van volana same su `caution`/`warning`.
- Nivoi: `safe` 90–100, `caution` 75–90, `warning` 55–75, `high_risk` 35–55, `critical` 10–35,
  `emergency` < 10. Svetlo prati nivo; vibracija i zvuk samo dok se nešto rizično dešava i kola se kreću.
  Poruka kontaktu kad `emergency` traje 2 s u vožnji. Detalji: `docs/API.md`, sekcija 7.
- Rezime vožnje: `average_score` = prosek dok se kola kreću, `level` = nivo za taj prosek (score na kraju je
  skoro uvek ~100, jer kola stoje).
- Alarm modela: kad model javi crveno (`alert.level == "red"`), kola u pokretu odmah vibriraju i
  glasno pište, na bilo kom nivou.
- Brzinu daje backend (`backend/app/services/speed.py`), redom: GPS telefona (ako je uključen i
  svež) > `speed_kmh` iz ticka (simulator) > mock vožnja.
- Sekcija = 2 s vožnje. Opasnost sekcije (samo dok se kola kreću): `critical` ("ultra opasno") = crveni
  alarm modela, glasan alarm kola ili uzbuna; `dangerous` = bodovano ponašanje, žuti alarm modela ili
  vibracija; inače `none`. Uzastopne opasne sekcije su jedan **momenat** (jedna mirna sekcija se premošćuje).

## Odluke (tumačenje prvog nacrta ideje)

- U nacrtu je pisalo 75–80 → uzeto 75–90. Pisalo je 35–75 → uzeto 35–55, sa žutim svetlom i
  pragom reakcije od 2 s.
- "Velika pripravnost" (10–35) = crveno svetlo, a vibracija i zvuk kreću odmah.
- Dok kola stoje nema opasnosti ni upozorenja, i to se ne računa u statistiku.
- Jelo, cigareta, konverzacija i ometanje od suvozača su izbačeni, jer ih modeli ne prepoznaju.
- (2026-11-06) Model ima svoj trenutni rizik (0..1, tri boje). **Naš score 0–100 ostaje glavni** za
  svetlo, nivoe i statistiku, a crveni alarm modela samo forsira vibraciju i zvuk. Razlog: kod
  score-a 100 nivo `safe` nikad ne reaguje, pa bi prvo mikrospavanje prošlo bez upozorenja.
- (2026-11-06) `eyes_off_road` je vraćen kao labela sa malom težinom (1.0), jer ga model sada daje.
  Kad ide zajedno sa `phone_use`, dodaje deo svoje opasnosti (30 %).
- `perception` (uglovi glave, oči, šake) ne ide na backend, jer aplikaciji ne treba.
- (2026-11-06) **Skladište: Postgres + S3 (RustFS)**, bez vektorske baze. Izveštaj (gde je bilo
  najgore, šta je najgore uradio, grafici) su obični SQL upiti. MinIO je odbačen jer je Community
  Edition arhiviran (februar 2026) i deli se samo kao izvorni kod. RustFS je Apache 2.0 i ima Windows build.
- (2026-11-06) Tickovi stižu ~2/s, pa se u bazu upisuje **jedan red po sekundi** (prosek i
  maksimum, da kratki skokovi ne nestanu). Prozor od 0.5 s ne bi ništa sabrao.
- (2026-11-06) **Brzina je mock na backendu**: šest scenarija (`city`, `highway`, `stop_and_go`,
  `country_road`, `cruise`, `parked`), nasumično po vožnji (`SPEED_SCENARIO`). Između tačaka je
  kubna Bezier kriva, a stajanje je tačno 0 km/h. GPS telefona (`POST /speed`) postoji kao zaseban
  feature, podrazumevano isključen (`PHONE_SPEED_ENABLED`), npr. za kola bez računarske snage.
- (2026-11-06) Klipovi su za demo u **javnom** lokalnom bucketu. Kompanija (`/analytics`) ih nikad ne
  dobija. Produkcija (poseban server za izveštaje) se dogovara kasnije.
- (2026-11-06) **Kategorije modela → labele**, prema `notebooks/risk_config.json`: `phone_use` →
  `looking_at_phone`, `eyes_off_road` i `hands_off_wheel` → iste labele, `drowsiness` i
  `eyes_closed` → `drowsy`. `eating_drinking` se ne boduje (`IGNORED_CATEGORIES`, jer je jelo
  izbačeno). `microsleep`, `long_distraction`, `phone_sustained` i `vats` su pravila
  (`rules_triggered`), a ne kategorije. Model nema izlaz za `looking_behind` ni `turning_around`, pa
  njih šalje samo simulator. `backend/tests/test_camera_mapping.py` pada ako model doda nepoznatu kategoriju.
- (2026-11-06) **Nalozi:** korisničko ime + lozinka (scrypt), nasumični token od 30 dana (u bazi samo
  SHA-256). Backend ne traži login (aplikacija ga traži): vožnja sa tokenom pripada nalogu i vidi je samo vlasnik (ostali dobijaju 404),
  a vožnja bez tokena radi kao ranije (`driver_id`) i vidi je svako. Živi kanal (WS, telemetrija,
  kraj vožnje) ostaje otvoren, jer je to mreža kola. Detalji i review: `docs/DATABASE.md`.
- (2026-11-06) Za izveštaj backend šalje **podatke jedne vožnje** (`GET /trips/{id}/report`: rezime,
  korisnik, sekcije od 2 s, opasni momenti sa slikama), a grafik crta aplikacija.
- (2026-11-06, kasnije) **Podela backenda na koordinator i server** (docs/ARCHITECTURE.md). Koordinator
  (u kolima) prima video, šalje ga modelu, računa rizik, score i reakciju, šalje stanje telefonu i na
  svake **2 s** rezime sekcije serveru i telefonu; za opasnu sekciju uz rezime ide slika najrizičnijeg
  frejma iz video keša (5 min, diskcache). Server samo čuva i služi. Model je zaseban proces koji samo
  detektuje. Sekcije zamenjuju uzorke po sekundi i momente sa klipovima; video momenta je planiran.
- (2026-11-06) `RiskEngine` CV tima je **izdvojen** u koordinator bez izmene matematike. Od 2026-11-07 je to
  jedina kopija (pipeline CV tima je uklonjen, vidi ispod).
- (2026-11-06) **Izveštaj modela za celu vožnju računa backend**, ne pipeline: `app/services/model_report.py`
  (vreme po boji alarma, pravila, epizode ponašanja i alarma), u `GET /trips/{id}/report` kao `model`. Posle podele
  ga hrani koordinator svakim tickom (frejmovi sa `/telemetry` ili detekcije model worker-a) i šalje serveru uz svaku
  sekciju. Pipeline radi samo matematiku po frejmu i ima dva moda: `--mode dev` (video sa sažetim metrikama, lokalni
  log) i `--mode prod` (bez prikaza, šalje backendu). Modul ostaje na toj putanji jer ga dev mod uvozi.
- (2026-11-06, kasnije) **Pravi put je kamera → koordinator → model worker**, a `risk_pipeline.py --mode prod` je samo
  debug (rizik tada računa pipeline, ne koordinator). Koordinator odbija zapise frejma na `/telemetry` dok je
  worker povezan. Prijava ne blokira kola: bez servera vožnja kreće, a server je upiše na nalog kad je primi
  (`TripMeta.owner_token`).
- (2026-11-07) **Score je trenutno stanje** (zahtev korisnika): nema više penala koji se skupljaju, "krhkosti" ni
  sporog oporavka (+3/min posle 30 s); score prati trenutnu opasnost pojačanu brzinom i vraća se kad je sve ok.
  Pragovi reakcije (≥ 5 s / ≥ 2 s) su izbačeni: nivo već uključuje koliko dugo ponašanje traje.
- (2026-11-07) **Aplikacija traži nalog**: registracija/prijava pri prvom otvaranju, token na svakom pozivu, odjava u
  Profilu. Vožnje iz aplikacije uvek pripadaju nalogu. Backend i dalje prima vožnje bez tokena (simulator, dashboard).
- (2026-11-07) **Model je Dušanov `rivian_model/`** (grana `nas-demo`, spojena u `main`): brži (~60–75 ms po
  frejmu, stiže svih 10 fps), manje lažnih uzbuna i vidi kolaps (`rivian_model/POREDJENJE_MODELA.md`). Model CV
  tima (`model/worker.py`, `notebooks/risk_pipeline.py`, `setup_models.*`) je uklonjen; ostaje u git istoriji
  (`git show 8d05c97:model/worker.py`). Nova labela `collapse` (kategorija `collapse` u `risk_config.json`, grupa
  `medical`). Model ne šalje `hands_off_wheel` ni `drowsiness`: te kategorije ostaju u configu sa dokazom 0.
- (2026-11-06) `hands_off_wheel` = **nijedna ruka na volanu**. Dokaz modela je 0 / 0.45 / 0.85 za
  2 / 1 / 0 ruku na volanu, a prag je 0.5, pa jedna ruka nikad ne aktivira labelu. Težina 1.0 ostaje.

## Otvorena pitanja (ažuriraj kad se dogovori)

1. **`looking_behind` / `turning_around` / `hands_off_wheel`:** model ih ne daje; dolaze samo iz simulatora.
2. **Poruka kontaktu:** backend sada samo loguje. Predlog je da aplikacija pošalje SMS na
   događaj `emergency`.
3. **Produkcija:** podela na koordinator (u kolima) i server (izveštaji) je urađena u kodu
   (docs/ARCHITECTURE.md). Otvoreno: kad server zaista radi van kola, telefon treba ili dve adrese (kola za
   uživo, server za istoriju) ili reverse proxy; outbox koordinatora na disk (sada je u memoriji, pa gašenje kola
   bez interneta gubi neisporučene sekcije); pristup slikama (potpisani URL-ovi umesto javnog bucketa), koliko
   dugo se čuvaju, više kola (`car_id`).
4. ~~**Model → backend uživo**~~ rešeno: `rivian_model/rivian_detector.py` radi preko koordinatora. Ostaje: kamera
   ne javlja koja je (`05_23`/`08_14`), pa se zona vozača bira pri pokretanju modela.

## Pravila za izmene koje prelaze iz jednog dela u drugi

- Promena ruta, šema ili enuma u backendu → **ažuriraj `docs/API.md` u istoj izmeni**.
- Promena labela → `Behavior` enum, težina u `coordinator/services/scoring.py`, savet u `domain/tips.py`,
  `BEHAVIORS` u `notebooks/safety_client.py`, `CATEGORY_TO_BEHAVIOR` u `coordinator/services/camera.py`
  (ako se ime kategorije modela razlikuje) i `docs/API.md`. Na frontendu: kopiraj §4 iz `docs/API.md` u
  `src/api/types.ts` obe aplikacije i dodaj labelu u `BEHAVIORS` (`frontend/mobile/src/config/behaviors.ts`
  + `strings.ts`, `frontend/dashboard/src/pages/CarScreen/carMeta.ts`).
- Nova kategorija u `notebooks/risk_config.json` → `CATEGORY_TO_BEHAVIOR` ili `IGNORED_CATEGORIES`
  u `backend/app/coordinator/services/camera.py`.
- Frontend ne izmišlja endpointe ni polja. Ako nešto fali, to je izmena backenda.
- Promena tabela (`backend/app/server/repositories/recordings.py`, `users.py`): migracija još nema, pa u
  dev-u prazna baza (`.\scripts\services.ps1 reset` ili `docker compose down -v`), pa restart backenda,
  koji napravi tabele. Backend u logu kaže koje kolone fale. Opis tabela drži ažurnim u `docs/DATABASE.md`.
- Koordinator i server se ne uvoze međusobno: koordinator serveru pristupa samo preko HTTP-a
  (`/internal/*`, `GET /auth/me`). Promena tog ugovora → `backend/app/schemas/sync.py` i docs/ARCHITECTURE.md.
- Promena protokola sa modelom → `backend/app/coordinator/services/model_link.py` **i**
  `rivian_model/rivian_detector.py` (`serve`).
- Nova kategorija modela → `CATEGORY_MAP` u `rivian_model/rivian_detector.py`, unos u `notebooks/risk_config.json`
  i mapiranje u `coordinator/services/camera.py` (pravilo iznad).
