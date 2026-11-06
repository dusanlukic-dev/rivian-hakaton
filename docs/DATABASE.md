# Baza podataka: struktura, šta se šalje frontu i review

Stanje: 2026-11-06. Kod je u `backend/app/repositories/` (tabele i upiti) i `backend/app/services/`
(`recording.py` snimanje, `auth.py` nalozi, `history.py` istorija i izveštaj). Ugovor sa frontom:
`docs/API.md`.

## Ukratko

- **Postgres** čuva podatke, a **S3** (lokalno RustFS) čuva slike i klipove. U bazi je samo ključ fajla.
- Pet tabela: `users`, `user_sessions`, `trips`, `trip_samples`, `risk_events`.
- Frontu za jednu vožnju sve stiže u jednom pozivu: `GET /trips/{id}/report`.
- Snimanje nikad ne usporava živi tok (score, alarmi). Ako baza padne, redovi čekaju u memoriji.

```
users ─┬─< user_sessions                    (jedan red po prijavi, tj. tokenu)
       └─< trips ─┬─< trip_samples          (jedan red po sekundi vožnje)
                  └─< risk_events           (jedan red po rizičnom momentu)
                          └──► S3 safety-media/clips/<trip_id>/<event_id>.mp4 + .jpg
```

`trips.user_id` je prazan (`NULL`) za vožnju pokrenutu bez prijave (simulator, stara aplikacija).
Brisanje vožnje briše njene uzorke i momente (`ON DELETE CASCADE`). Brisanje naloga ostavlja vožnje
bez vlasnika (`SET NULL`).

## Tabele

### `users`: nalog vozača
| Kolona | Šta |
|---|---|
| `id` | ključ (32 hex) |
| `username` | jedinstveno, mala slova, 3–32 znaka. Ujedno `driver_id` njegovih vožnji |
| `password_hash` | `scrypt$N$r$p$salt$hash`. **Lozinka se nikad ne čuva**, ni ne vraća |
| `display_name` | ime za prikaz |
| `emergency_contact` | JSONB `{name, phone}`, podrazumevani kontakt za vožnje |
| `created_at` | UTC |

### `user_sessions`: prijave
| Kolona | Šta |
|---|---|
| `token_hash` | SHA-256 tokena (ključ). Sam token zna samo aplikacija |
| `user_id` | čiji je |
| `created_at`, `expires_at` | token važi 30 dana |

### `trips`: jedna vožnja
| Kolona | Šta |
|---|---|
| `id`, `user_id`, `driver_id` | koja vožnja i čija |
| `started_at`, `ended_at` | `ended_at` je `NULL` dok vožnja traje |
| `updated_at` | poslednji upis rezimea |
| `emergency_contact` (JSONB), `speed_scenario` | kontakt te vožnje, mock scenario brzine |
| `duration_s`, `final_score`, `average_score`, `min_score`, `level`, `emergency_alert_sent` | **rezime vožnje**, isti brojevi kao `TripSummary` |
| `behaviors` (JSONB) | `[{behavior, occurrences, total_seconds}]`. Saveti se dodaju pri čitanju |

### `trip_samples`: jedna sekunda vožnje (sirovi zapis za grafike)
Svaki red sabira tickove te sekunde (stižu ~2/s). Za sat vožnje to je oko 3600 redova.

| Grupa | Kolone |
|---|---|
| vreme | `ts` (UTC), `t` (sekundi od početka, x osa), `ticks` |
| brzina | `speed_kmh` (prosek), `speed_max_kmh`, `speed_source` (`mock` / `phone` / `telemetry`) |
| **score tokom vožnje** | `score` (na kraju sekunde), `score_min`, `level` |
| šta je backend bodovao | `behaviors` (lista labela) |
| šta je model video | `risk`, `risk_max`, `alert`, `rules_triggered`, `categories` (JSONB: po kategoriji `p`, `p_max`, `active`, `r`, `run_s`), `groups` |
| reakcija kola | `dashboard_light`, `vibrate_seat`, `sound` (najjača u toj sekundi) |
| lokacija | `lat`, `lon` (samo sa GPS-om telefona) |

### `risk_events`: rizičan momenat
Rizičan momenat je kad se kola kreću (≥ 5 km/h), a vidi se bodovano ponašanje ili model da crveni
alarm. Prekid kraći od 2 s je isti momenat, a duži od 30 s se seče.

| Grupa | Kolone |
|---|---|
| vreme | `started_at`, `ended_at`, `t_start` (ista osa kao `trip_samples.t`), `duration_s` |
| šta je radio | `behaviors` (najduže prvo), `behavior_seconds`, `categories` (kategorija modela → najveće `p`), `rules_triggered`, `alert`, `peak_risk` |
| koliko je koštalo | `score_start`, `score_end`, `score_min`, `score_drop`, `level` |
| okolnosti | `speed_avg_kmh`, `speed_max_kmh`, `lat`, `lon` |
| **slike i video** | `thumbnail_key` (JPEG najrizičnijeg frejma), `video_key` (MP4: 3 s pre, 2 s posle), `clip_duration_s` |

## Šta front dobija

| Potreba | Endpoint | Odakle |
|---|---|---|
| registracija, šifra, login | `POST /auth/register`, `POST /auth/login` → `AuthOut` (token + korisnik) | `users`, `user_sessions` |
| ko je user | `GET /auth/me`, izmena: `PATCH /auth/me` | `users` |
| trip summary | `GET /trips/{id}/summary`, istorija `GET /trips` | `trips` (živa vožnja iz memorije) |
| score tokom vožnje + podaci za grafike (**sirovo**) | `GET /trips/{id}/report` → `samples` | `trip_samples` |
| slike i klipovi tokom vožnje | `GET /trips/{id}/report` → `events[].thumbnail_url`, `video_url` | `risk_events` + S3 |
| **sve za jednu vožnju odjednom** | `GET /trips/{id}/report` → `{trip, user, window_s, samples, events}` | sve gore |

Backend ne pravi grafike. Šalje sirove uzorke jedne vožnje, a aplikacija od njih pravi šta hoće:
score i brzinu kroz vreme, verovatnoću "telefon" po sekundi, oznake rizičnih momenata (`t_start`).
Primer odgovora i tipovi su u `docs/API.md` (§4 `TripReport`, §5).

## Kada se šta upisuje

| Kada | Šta |
|---|---|
| registracija, login | red u `users` / `user_sessions` (odmah) |
| start vožnje | red u `trips` (sa `user_id` ako je vozač prijavljen) |
| svake sekunde | red u `trip_samples` |
| svakih ~10 s | rezime u `trips` (trenutni score, prosek, min, ponašanja) |
| kraj rizičnog momenta | klip i slika u S3, pa red u `risk_events` |
| kraj vožnje | konačan rezime i `ended_at` u `trips` |
| start backenda posle pada | otvorene vožnje dobijaju `ended_at` = poslednji upis rezimea |

Upisi idu u paketima na svake 2 s, u pozadini. Rute za čitanje prvo upišu sve iz reda čekanja, pa
vide i ono što se upravo desilo.

## Lozinke i tokeni

- **Lozinka:** scrypt (`N=2^14, r=8, p=1`, nasumična so od 16 B) iz standardne biblioteke. Računa
  se u pozadinskoj niti, oko 50 ms, pa prijava ne koči živi score. Za nepostojeće ime se takođe
  računa heš, da vreme odgovora ne otkrije koja imena postoje.
- **Token:** 32 nasumična bajta. U bazi je samo njegov SHA-256, pa procurela tabela ne daje
  pristup. Važi 30 dana, a `POST /auth/logout` ga briše.
- **Zašto ne JWT:** odjava zaista radi, nema tajnog ključa koji bi trebalo čuvati i rotirati, a
  šablon za login na dashboardu prima bilo kakav token.

## Ko šta vidi

- Vožnju pokrenutu **sa tokenom** vidi samo taj nalog. Ostali dobijaju `404` na `/summary`,
  `/report`, `/timeline`, `/events` i `GET /trips/{id}`, a u istoriji je ne vide.
- Vožnju **bez prijave** vidi svako, kao ranije. Simulator, `tools/sim.py` i dashboard rade bez izmena.
- Živi kanal (WebSocket, `POST /telemetry`, `/video/frames`, `POST /trips/{id}/end`) je otvoren,
  jer je to mreža samih kola.
- `GET /media/...` nije iza logina. Ključevi su nasumični, pa link zna samo onaj ko vidi izveštaj.
  Bucket je za demo javan.
- Kompanija (`/analytics/overview`) dobija samo agregate, nikad slike.

## Review: šta valja, šta je popravljeno, šta je ostalo

**Šta valja (od ranije):**
- Živi tok ne zavisi od baze. Testirano je gašenjem Postgresa i RustFS-a usred vožnje: score radi,
  a redovi se upišu kad se baza vrati.
- Agregat po sekundi čuva i proseke i maksimume, pa kratak pogled u telefon ne nestane.
- Brojevi modela su u JSONB, pa nova kategorija modela ne traži promenu tabele.
- Klipovi se prave samo za rizične momente: manje prostora i manje snimaka vozača.

**Problemi zatečeni u ovom review-u, sada popravljeni:**
1. **Nije bilo korisnika.** `driver_id` je bio slobodan tekst koji šalje aplikacija, pa je svako
   mogao da se predstavi kao bilo ko i da čita tuđe vožnje i klipove. → nalozi, lozinka, token,
   vlasništvo nad vožnjom.
2. **Statistika i istorija su čitane samo iz memorije**, pa su posle restarta davale `404`, iako su
   podaci bili u bazi. → čitaju se iz Postgresa (živa vožnja i dalje iz memorije).
3. **Rezime vožnje se upisivao tek na kraju.** Pad servera je ostavljao vožnju bez rezimea i zauvek
   "otvorenu". → rezime se upisuje na ~10 s, a na startu se zatvaraju prekinute vožnje. Provereno
   nasilnim gašenjem servera.
4. Kontakt za hitne slučajeve postojao je samo po vožnji. → čuva se i u nalogu, kao podrazumevani.
5. Šemu su paralelno pravile dve korutine (`CREATE TABLE` trka), a testovi su delili jednu SQLite
   konekciju. → baza ima zaključavanje za šemu, a SQLite redom pušta korisnike.
6. Ponašanja sa jednakim trajanjem su stizala u različitom redosledu od poziva do poziva. → kod
   izjednačenja redosled je abecedni.

**Svesno ostavljeno za posle hakatona:**
- **Nema migracija** (Alembic). Kad se promeni model: `.\scripts\services.ps1 reset`. Backend bar
  upozori u logu koje kolone fale.
- **Javni bucket i otvoren `/media`.** Za produkciju: privatni bucket i potpisani URL-ovi, kao i
  poseban server za izveštaje (otvoreno pitanje u root `CLAUDE.md`).
- Nema roka čuvanja (brisanje starih klipova) ni brisanja naloga i podataka (GDPR).
- Nema promene ni reseta lozinke, potvrde emaila, uloga ni ograničenja broja pokušaja logina.
- **"Slike tokom vožnje" su slike rizičnih momenata**, ne periodične slike cele vožnje (privatnost i
  prostor). Periodični snimak bi bio mali dodatak u `TripRecorder`.
- **"Sirovi" podaci su po sekundi** (oko 2 ticka). Ako baš treba svaki tick: `sample_window_s = 0.5` u
  `RecordingConfig` (2× više redova).
- Prilikom pada servera gubi se najviše poslednjih ~2 s uzoraka i ~10 s rezimea.
- Agregati po vozaču kroz vreme (napredak iz vožnje u vožnju) nemaju endpoint, ali su jedan SQL upit
  nad `trips`.

## Kako pogledati ili resetovati bazu

```powershell
cd backend
.\scripts\services.ps1 psql     # SQL nad bazom "safety"
.\scripts\services.ps1 reset    # prazna baza; backend napravi tabele na sledećem startu
```

```sql
select username, display_name, created_at from users;
select id, driver_id, started_at, ended_at, final_score from trips order by started_at desc limit 10;
select t, score, speed_kmh, behaviors from trip_samples where trip_id = '...' order by t;
select behaviors, duration_s, score_drop, thumbnail_key from risk_events where trip_id = '...' order by score_drop desc;
select t, (categories->'phone_use'->>'p_max')::float as phone from trip_samples where trip_id = '...';
```
