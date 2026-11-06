# Baza podataka: struktura, šta se šalje frontu i review

Stanje: 2026-11-06 (posle podele na koordinator i server, [ARCHITECTURE.md](ARCHITECTURE.md)). Bazu ima
samo **server**: tabele i upiti su u `backend/app/server/repositories/`, a servisi u
`backend/app/server/services/` (`storage.py` prijem i čitanje, `auth.py` nalozi, `history.py` istorija,
izveštaj i momenti). Koordinator bazu nikad ne dira: šalje sekcije serveru preko `/internal/*`.
Ugovor sa frontom: [API.md](API.md).

## Ukratko

- **Postgres** čuva podatke, a **S3** (lokalno RustFS) slike opasnih momenata. U bazi je samo ključ slike.
- Četiri tabele: `users`, `user_sessions`, `trips`, `trip_sections`.
- Jedna sekcija = **2 s vožnje** kako ju je koordinator sažeo (score, šta je viđeno, opasnost, slika).
- Frontu za jednu vožnju sve stiže u jednom pozivu: `GET /trips/{id}/report` (sekcije + momenti).
- Upis nikad ne usporava živi tok (score, alarmi): ako server ili baza ne rade, sekcije čekaju u
  koordinatoru i stignu kad se server vrati.

```
users ─┬─< user_sessions                    (jedan red po prijavi, tj. tokenu)
       └─< trips ──< trip_sections          (jedan red po 2 s vožnje)
                          └──► S3 safety-media/sections/<trip_id>/<section_id>.jpg   (samo opasne sekcije)
```

`trips.user_id` je prazan (`NULL`) za vožnju pokrenutu bez prijave (simulator, stara aplikacija).
Brisanje vožnje briše njene sekcije (`ON DELETE CASCADE`). Brisanje naloga ostavlja vožnje bez vlasnika
(`SET NULL`).

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
| `id`, `user_id`, `driver_id` | koja vožnja i čija (`id` pravi koordinator) |
| `started_at`, `ended_at` | `ended_at` je `NULL` dok vožnja traje |
| `updated_at` | poslednji upis rezimea |
| `emergency_contact` (JSONB), `speed_scenario`, `section_s` | kontakt te vožnje, mock scenario brzine, dužina sekcije (2) |
| `duration_s`, `final_score`, `average_score`, `min_score`, `level`, `emergency_alert_sent` | **rezime vožnje**, isti brojevi kao `TripSummary`, obnavlja se sa svakom sekcijom |
| `behaviors` (JSONB) | `[{behavior, occurrences, total_seconds}]`. Saveti se dodaju pri čitanju |

### `trip_sections`: 2 s vožnje
Rezime koji koordinator pravi na svake 2 s (`SECTION_S`) od svih tickova u tom periodu (detekcije modela
5–10/s ili telemetrija simulatora). Sat vožnje je 1800 redova. Ključ (`id`) pravi koordinator, pa ponovno
slanje istog paketa ne pravi duplikate.

| Grupa | Kolone |
|---|---|
| vreme | `seq` (0, 1, 2...), `t_start`, `t_end` (sekundi od početka, x osa), `started_at`, `ended_at` (UTC), `ticks` |
| **score** | `score_start`, `score_end` (y tačke na grafiku), `score_min`, `level` (za `score_end`) |
| **opasnost** | `danger`: `none`, `dangerous` ili `critical` (pravila u ARCHITECTURE.md), `emergency` (uzbuna u ovoj sekciji) |
| šta je viđeno | `behaviors` (JSONB: labela → sekundi u sekciji) |
| šta je model video | `risk` (prosek), `risk_max`, `alert` (najgori), `rules_triggered`, `categories` (JSONB: po kategoriji `p`, `p_max`, `active`, `r`, `run_s`), `groups` |
| brzina | `speed_kmh` (prosek), `speed_max_kmh`, `speed_source` (`mock` / `phone` / `telemetry`) |
| reakcija kola | `dashboard_light`, `vibrate_seat`, `sound` (najjača u sekciji) |
| **slika** | `image_key` (S3 ključ JPEG-a najrizičnijeg frejma, samo opasne sekcije sa videom), `image_t` (kada je snimljen, ista osa kao `t_start`) |
| lokacija | `lat`, `lon` (samo sa GPS-om telefona) |

**Momenti nisu tabela.** Server ih pravi pri čitanju izveštaja: uzastopne sekcije sa `danger` ≠ `none`
(jedna mirna sekcija u sredini se premošćuje) postaju jedan momenat sa zbirnim ponašanjima, padom score-a
i slikom najrizičnije sekcije (`build_moments` u `server/services/history.py`).

## Šta front dobija

| Potreba | Endpoint | Odakle |
|---|---|---|
| registracija, šifra, login | `POST /auth/register`, `POST /auth/login` → `AuthOut` (token + korisnik) | `users`, `user_sessions` |
| ko je user | `GET /auth/me`, izmena: `PATCH /auth/me` | `users` |
| trip summary | `GET /trips/{id}/summary`, istorija `GET /trips` | `trips` |
| **grafik vožnje** (score kroz vreme, opasni delovi, šta je viđeno) | `GET /trips/{id}/report` → `sections` | `trip_sections` |
| opasni momenti sa slikama | `GET /trips/{id}/report` → `moments[].image_url` | `trip_sections` + S3 |
| **sve za jednu vožnju odjednom** | `GET /trips/{id}/report` → `{trip, user, section_s, sections, moments}` | sve gore |
| samo nove sekcije aktivne vožnje | `GET /trips/{id}/sections?after_seq=N` | `trip_sections` |

Backend ne crta grafike. Šalje sekcije jedne vožnje, a aplikacija od njih crta liniju score-a, senči opasne
delove i stavlja čvor i sliku za momente. Primer odgovora i tipovi su u [API.md](API.md) (§4, §5, §7).

## Kada se šta upisuje

Sve upise radi server kad primi paket od koordinatora (`POST /internal/trips/{id}/sync`, ARCHITECTURE.md).

| Kada | Šta |
|---|---|
| registracija, login | red u `users` / `user_sessions` (odmah) |
| start vožnje | red u `trips` (sa `user_id` ako je vozač prijavljen), stiže u prvom paketu |
| na svake 2 s vožnje | red u `trip_sections` (+ slika u S3 za opasne), i rezime u `trips` |
| kraj vožnje | poslednja sekcija, konačan rezime i `ended_at` u `trips` |
| start koordinatora posle pada | otvorene vožnje dobijaju `ended_at` = poslednji upis rezimea |

Koordinator šalje odmah kad se sekcija zatvori (jedan zahtev u letu, paketi do 40 sekcija). Na "End" čeka
najviše 3 s da server primi sve, pa izveštaj odmah posle kraja vožnje ima i poslednju sekciju.

## Lozinke i tokeni

- **Lozinka:** scrypt (`N=2^14, r=8, p=1`, nasumična so od 16 B) iz standardne biblioteke. Računa
  se u pozadinskoj niti, oko 50 ms, pa prijava ne koči živi score. Za nepostojeće ime se takođe
  računa heš, da vreme odgovora ne otkrije koja imena postoje.
- **Token:** 32 nasumična bajta. U bazi je samo njegov SHA-256, pa procurela tabela ne daje
  pristup. Važi 30 dana, a `POST /auth/logout` ga briše.
- **Zašto ne JWT:** odjava zaista radi, nema tajnog ključa koji bi trebalo čuvati i rotirati, a
  šablon za login na dashboardu prima bilo kakav token.
- Koordinator ne zna lozinke ni tokene: kad telefon pokrene vožnju sa tokenom, pita server
  (`GET /auth/me`) čiji je, i to pamti 30 s.

## Ko šta vidi

- Vožnju pokrenutu **sa tokenom** vidi samo taj nalog. Ostali dobijaju `404` na `/summary`,
  `/report`, `/sections` i `GET /trips/{id}`, a u istoriji je ne vide.
- Vožnju **bez prijave** vidi svako, kao ranije. Simulator, `tools/sim.py` i dashboard rade bez izmena.
- Živi kanal (WebSocket, `POST /telemetry`, `/video/frames`, `/camera/ws`, `POST /trips/{id}/end`) je
  otvoren, jer je to mreža samih kola. `/internal/*` traži `X-Internal-Token`.
- `GET /media/...` nije iza logina. Ključevi su nasumični, pa link zna samo onaj ko vidi izveštaj.
  Bucket je za demo javan.
- Kompanija (`/analytics/overview`) dobija samo agregate, nikad slike.

## Review: šta valja, šta je promenjeno, šta je ostalo

**Promenjeno podelom na koordinator i server (2026-11-06):**
1. `trip_samples` (1 red po sekundi) i `risk_events` (momenti sa klipovima) su zamenjeni sa
   `trip_sections` (1 red po 2 s, sa opasnošću i slikom). Momenti se izvode pri čitanju.
2. Bazu piše samo server, i to samo ono što mu koordinator pošalje. Ranije je snimač radio u istom
   procesu kao živi score i pisao direktno u Postgres.
3. Istorija i rezime se čitaju samo iz baze (koordinator ne čuva istoriju). Rezime aktivne vožnje kasni
   najviše jednu sekciju (~2 s).
4. Klipovi (MP4 oko momenta) se više ne prave: momenat ima jednu sliku. Video celog momenta je planiran
   (koordinator ima 5 min videa u kešu i `encode_mp4`).

**Šta valja (i dalje):**
- Živi tok ne zavisi od baze ni od servera: testirano gašenjem baze usred vožnje, sekcije stignu kad se vrati.
- Sekcija čuva i proseke i maksimume, pa kratak pogled u telefon ne nestane.
- Brojevi modela su u JSONB, pa nova kategorija modela ne traži promenu tabele.
- Slike se prave samo za opasne sekcije: manje prostora i manje snimaka vozača.

**Svesno ostavljeno za posle hakatona:**
- **Nema migracija** (Alembic). Kad se promeni model: `.\scripts\services.ps1 reset` ili
  `docker compose down -v` (prazna baza). Server bar upozori u logu koje kolone fale. Stare tabele
  (`trip_samples`, `risk_events`) u postojećoj bazi samo ostaju neiskorišćene.
- **Javni bucket i otvoren `/media`.** Za produkciju: privatni bucket i potpisani URL-ovi.
- Nema roka čuvanja (brisanje starih slika) ni brisanja naloga i podataka (GDPR).
- Nema promene ni reseta lozinke, potvrde emaila, uloga ni ograničenja broja pokušaja logina.
- Agregati po vozaču kroz vreme (napredak iz vožnje u vožnju) nemaju endpoint, ali su jedan SQL upit
  nad `trips`.

## Kako pogledati ili resetovati bazu

```powershell
cd backend
docker compose exec postgres psql -U safety safety     # SQL nad bazom (Docker)
.\scripts\services.ps1 psql                             # ...ili portabl Postgres
.\scripts\services.ps1 reset                            # prazna baza; server napravi tabele na sledećem startu
```

```sql
select username, display_name, created_at from users;
select id, driver_id, started_at, ended_at, final_score from trips order by started_at desc limit 10;
select seq, score_end, danger, behaviors, image_key from trip_sections where trip_id = '...' order by seq;
select seq, (categories->'phone_use'->>'p_max')::float as phone from trip_sections where trip_id = '...' order by seq;
select seq, danger, image_key from trip_sections where trip_id = '...' and danger <> 'none' order by seq;
```
