# Personal Safety Reviewer: Rivian hakaton

Tim komunicira na srpskom (latinica). Kod, identifikatori, API i labele su na engleskom.

## Ideja

Kamera u kabini prati vozača. Backend računa **koeficijent pažnje 0–100** (100 = potpuno usredsređen,
0 = opasnost po život), a kola reaguju: svetlo na dashboardu, vibracija sedišta, zvučni signal, poruka
kontaktu za hitne slučajeve. Na kraju vožnje vozač dobija statistiku, savete i izveštaj: grafik vožnje
i video klipove svojih najgorih momenata. Kompanija vidi samo koeficijente i vrste grešaka, **nikad
slike** (privatnost).

## Delovi repoa

| Putanja | Šta je |
|---|---|
| `backend/` | FastAPI: računa score, šalje događaje aplikaciji, snima vožnju za izveštaj. Detalji u `backend/CLAUDE.md` |
| `backend/scripts/services.ps1` | Postgres + RustFS (S3) za snimanje vožnji, portabl (bez Dockera i admin prava). Sa Dockerom: `backend/docker-compose.yml` |
| `notebooks/` | CV modeli (YOLO, OpenCV, MediaPipe), rade drugi članovi tima |
| `notebooks/safety_client.py` | most modeli → backend, plus simulator cele vožnje |
| `frontend/mobile/` | Expo (SDK 58) Android aplikacija za vozača, dev build. Pravila: `.claude/rules/mobile.md` |
| `frontend/dashboard/` | web mock ekrana u kolima (Vite + React). Pravila: `.claude/rules/dashboard.md` |
| `docs/API.md` | **ugovor backend ↔ aplikacija, izvor istine.** Pročitaj ga pre bilo kakvog rada na frontendu |
| `docs/DATABASE.md` | struktura baze (nalozi, vožnje, uzorci, momenti, klipovi), šta se šalje frontu, review |
| `PROGRESS.md` | stanje projekta, bagovi, sledeći koraci. Pročitaj na početku, ažuriraj na kraju |
| `.claude/` | pravila, skillovi i knowledge za agente (frontend, alati, mreža, Android). Indeks: `.claude/CLAUDE.md` |

## Arhitektura i mreža

```
laptop: notebooks (modeli) ──POST 127.0.0.1:8000/api/v1/telemetry (~2/s, frejm modela ili labele)──► backend
                           ──POST 127.0.0.1:8000/api/v1/video/frames (~8/s, JPEG)──────────────────► backend
        backend ──► Postgres 127.0.0.1:5433 (nalozi, vožnje, uzorci po 1 s, rizični momenti) + RustFS S3 127.0.0.1:9000 (klipovi)
telefon (hotspot): React Native app ◄──WS /api/v1/ws (uživo)── backend
                                    ──REST /auth (login), /trips (start, kraj, istorija, izveštaj, klipovi)──►
```

- Za demo **nema servera ni DNS-a**. Laptop pokreće backend i modele, telefon pravi hotspot, a laptop
  je povezan na njega. Aplikacija gađa IP laptopa, koji `python backend/run.py` ispiše pri
  pokretanju. IP se menja pri svakom ponovnom povezivanju.
- **Jedan auto = jedna aktivna vožnja.** Telemetrija ide u aktivnu vožnju, a nova vožnja završava
  prethodnu.
- Model šalje svoj zapis frejma (isti kao red u `frames.jsonl`) preko `SafetyClient.send_frame`,
  bez `perception` i bez slika. Backend preslikava aktivne kategorije modela na labele
  (`CATEGORY_TO_BEHAVIOR` u `backend/app/services/camera.py`), a rizik i kategorije modela
  prosleđuje aplikaciji u polju `camera`.
- Video ide posebno: `SafetyClient.send_video_frame(frame)` šalje JPEG frejmove. Backend drži samo
  par sekundi u memoriji, a klip (3 s pre i 2 s posle) čuva samo oko **rizičnog momenta**.
- Snimanje (`backend/app/services/recording.py`) radi pored živog toka i nikad ga ne usporava. Ako
  Postgres ili S3 nisu dostupni, score i reakcije kola rade normalno, a redovi čekaju u memoriji.

## Pravila domena (sažetak)

- Labele: `looking_at_phone`, `looking_behind`, `turning_around`, `hands_off_wheel`, `drowsy`,
  `eyes_off_road`.
- Penal = težina × sekunde, plus jednokratni udar kad ponašanje počne. Penal se množi sa:
  - brzinom (< 5 km/h nema penala, autoput 1.7×)
  - noći (22–06h, 1.5×)
  - "krhkošću" (što je score niži, lakše pada)
- Oporavak: posle 30 s čiste vožnje, +3 poena/min.
- Nivoi: `safe` 90–100, `caution` 75–90, `warning` 55–75, `high_risk` 35–55, `critical` 10–35,
  `emergency` < 10. Reakcija kola po nivou je opisana u `docs/API.md`, sekcija 7.
- Alarm modela: kad model javi crveno (`alert.level == "red"`), kola u pokretu odmah vibriraju i
  glasno pište, na bilo kom nivou.
- Brzinu daje backend (`backend/app/services/speed.py`), redom: GPS telefona (ako je uključen i
  svež) > `speed_kmh` iz ticka (simulator) > mock vožnja.
- Rizičan momenat = kola se kreću (≥ 5 km/h), a vidi se bodovano ponašanje ili je model dao crveni
  alarm. Detekcije razmaknute manje od 2 s su isti momenat, a duži od 30 s se seče.

## Odluke (tumačenje prvog nacrta ideje)

- U nacrtu je pisalo 75–80 → uzeto 75–90. Pisalo je 35–75 → uzeto 35–55, sa žutim svetlom i
  pragom reakcije od 2 s.
- "Velika pripravnost" (10–35) = crveno svetlo, a vibracija i zvuk kreću odmah.
- Dok kola stoje nema penala ni upozorenja, i to se ne računa u statistiku.
- Jelo, cigareta, konverzacija i ometanje od suvozača su izbačeni, jer ih modeli ne prepoznaju.
- (2026-11-06) Model ima svoj trenutni rizik (0..1, tri boje). **Naš score 0–100 ostaje glavni** za
  svetlo, nivoe i statistiku, a crveni alarm modela samo forsira vibraciju i zvuk. Razlog: kod
  score-a 100 nivo `safe` nikad ne reaguje, pa bi prvo mikrospavanje prošlo bez upozorenja.
- (2026-11-06) `eyes_off_road` je vraćen kao labela sa malom težinom (1.0), jer ga model sada daje.
  Kad ide zajedno sa `phone_use`, penali se sabiraju.
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
  SHA-256). Login nije obavezan: vožnja sa tokenom pripada nalogu i vidi je samo vlasnik (ostali dobijaju 404),
  a vožnja bez tokena radi kao ranije (`driver_id`) i vidi je svako. Živi kanal (WS, telemetrija,
  kraj vožnje) ostaje otvoren, jer je to mreža kola. Detalji i review: `docs/DATABASE.md`.
- (2026-11-06) Za izveštaj backend šalje **sirove podatke jedne vožnje** (`GET /trips/{id}/report`:
  rezime, korisnik, uzorci po sekundi, momenti sa slikama), a grafike računa aplikacija. Rezime vožnje
  se upisuje na ~10 s, pa pad servera ne briše vožnju.
- (2026-11-06) `hands_off_wheel` = **nijedna ruka na volanu**. Dokaz modela je 0 / 0.45 / 0.85 za
  2 / 1 / 0 ruku na volanu, a prag je 0.5, pa jedna ruka nikad ne aktivira labelu. Težina 1.0 ostaje.

## Otvorena pitanja (ažuriraj kad se dogovori)

1. **`looking_behind` / `turning_around`:** da li CV tim pravi te izlaze? Do tada dolaze samo iz simulatora.
2. **Poruka kontaktu:** backend sada samo loguje. Predlog je da aplikacija pošalje SMS na
   događaj `emergency`.
3. **Produkcija:** odvojiti server za računanje (u kolima) od servera za izveštaje (dostupan i van
   kola)? Pristup klipovima (potpisani URL-ovi umesto javnog bucketa) i koliko dugo se čuvaju.
4. **Model → backend uživo:** `risk_pipeline.py` još ne zove `SafetyClient.send_frame`. To je
   jedna linija u petlji, ali je fajl CV tima.

## Pravila za izmene koje prelaze iz jednog dela u drugi

- Promena ruta, šema ili enuma u backendu → **ažuriraj `docs/API.md` u istoj izmeni**.
- Promena labela → `Behavior` enum, težina u `scoring.py`, savet u `TIPS`, `BEHAVIORS` u
  `notebooks/safety_client.py`, `CATEGORY_TO_BEHAVIOR` u `services/camera.py` (ako se ime
  kategorije modela razlikuje) i `docs/API.md`. Na frontendu: kopiraj §4 iz `docs/API.md` u
  `src/api/types.ts` obe aplikacije i dodaj labelu u `BEHAVIORS` (`frontend/mobile/src/config/behaviors.ts`
  + `strings.ts`, `frontend/dashboard/src/pages/CarScreen/carMeta.ts`).
- Nova kategorija u `notebooks/risk_config.json` → `CATEGORY_TO_BEHAVIOR` ili `IGNORED_CATEGORIES`
  u `services/camera.py`.
- Frontend ne izmišlja endpointe ni polja. Ako nešto fali, to je izmena backenda.
- Promena tabela (`backend/app/repositories/recordings.py`, `users.py`): migracija još nema, pa u dev-u
  `.\scripts\services.ps1 reset` (prazna baza), pa restart backenda, koji napravi tabele. Backend u
  logu kaže koje kolone fale. Opis tabela drži ažurnim u `docs/DATABASE.md`.
