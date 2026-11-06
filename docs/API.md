# API ugovor: backend ↔ mobilna aplikacija

Ovo je **izvor istine** za komunikaciju React Native aplikacije sa backendom. Kad se backend
promeni, menja se i ovaj fajl.

> **Za Claude koji pravi frontend:** koristi tačno ove rute, polja i tipove (sekcija 4 se može
> kopirati u `src/api/types.ts`). Ne izmišljaj endpointe ni polja. Ako nešto fali, to je izmena
> backenda, pa to reci developeru umesto da pretpostavljaš. Aplikacija **ne šalje telemetriju**,
> to rade kamera i model.

Backend ima dva dela ([ARCHITECTURE.md](ARCHITECTURE.md)): **koordinator** (u kolima: WebSocket,
kamera, model, score, sekcije od 2 s) i **server** (nalozi, istorija, izveštaj, slike). U demo-u oba
odgovaraju na istoj adresi (`:8000`), pa aplikacija ima jednu adresu. U §5 piše koji deo služi koju rutu.

## 1. Šta aplikacija radi

1. Povezuje se na backend (laptop) preko hotspota telefona.
2. Vozač se registruje ili prijavi (korisničko ime + lozinka), pa pokreće vožnju. Bez prijave i dalje
   može, sa svojim ID-jem i kontaktom za hitne slučajeve, kao ranije.
3. Tokom vožnje uživo prikazuje dashboard: svetlo, score, trenutna rizična ponašanja, poruku.
   Simulira vibraciju sedišta i zvučni signal.
4. Kad score padne ispod 10, prikazuje uzbunu za hitan slučaj.
5. Vozač završava vožnju i vidi statistiku sa savetima.
6. Izveštaj vožnje (`GET /trips/{id}/report`, sve u jednom pozivu): rezime, ko je vozio, vožnja po
   sekcijama od 2 s za grafik (score, brzina, šta je viđeno, rizik modela, opasnost) i opasni momenti sa
   slikom najrizičnijeg trenutka. Na grafiku: osenčeni opasni delovi, čvor po momentu i kućica sa slikom
   iznad "ultra opasnih" (`critical`).
   Uživo, na svake 2 s, stiže i WS `section` (šta je viđeno u poslednje 2 s), za prikaz tokom vožnje.
7. Istorija vožnji.
8. Opciono (podrazumevano isključeno): telefon šalje svoju GPS brzinu backendu (`POST /speed`).

## 2. Povezivanje

| | |
|---|---|
| REST base URL | `http://<IP>:8000/api/v1` |
| WebSocket | `ws://<IP>:8000/api/v1/ws` |
| Autentifikacija | opciona: `Authorization: Bearer <token>` (token iz `POST /auth/login` ili `/auth/register`, važi 30 dana) |
| Format | JSON, UTF-8 |
| Swagger (samo REST) | `http://<IP>:8000/docs`, šema na `/openapi.json` |

- **Nema DNS-a ni servera.** Backend radi na laptopu koji je povezan na hotspot telefona.
  Backend se pokreće sa `python run.py` (iz `backend/`) i ispisuje IP.
  **IP se menja** pri svakom ponovnom povezivanju na hotspot.
- Zato aplikacija mora imati **ekran za podešavanja sa poljem za adresu** (npr. `192.168.43.57:8000`).
  Adresu treba sačuvati (AsyncStorage) i dodati dugme "Testiraj vezu" koje zove `GET /health`.
  Adresu ne hardkodovati.
- Saobraćaj je običan `http://` / `ws://` (bez TLS-a). U Expo Go / dev buildu radi odmah. Za
  samostalni build:
  - Android: uključiti cleartext (`usesCleartextTraffic`, npr. preko `expo-build-properties`)
  - iOS: dozvoliti lokalnu mrežu (`NSAllowsLocalNetworking` u ATS i `NSLocalNetworkUsageDescription`)

## 3. Tok ekrana (preporuka)

```
Podešavanja (IP + GET /health)
   → Prijava / registracija ── POST /auth/login | /auth/register ──► čuva token (AsyncStorage)
   → Početak vožnje ── POST /trips (sa tokenom) ──► Dashboard (WebSocket, uživo)
                                                  │ dugme "Završi" ── POST /trips/{id}/end
                                                  ▼
                                               Statistika (TripSummary)
                                                  │ "Izveštaj"
                                                  ▼
                       Izveštaj ── GET /trips/{id}/report (rezime + korisnik + sekcije za grafik + momenti sa slikama)
Istorija ── GET /trips (sa tokenom: moje vožnje) ──► Statistika / Izveštaj pojedinačne vožnje
Profil ── GET /auth/me, PATCH /auth/me (ime, kontakt za hitne slučajeve), POST /auth/logout
```

Backend ne traži prijavu: bez tokena sve radi kao ranije (`driver_id` u `POST /trips`; simulator, dashboard).
**Aplikacija vozača je traži** (2026-11-07): ekran za prijavu/registraciju pri prvom otvaranju, token na svakom
REST pozivu, `401` → nazad na prijavu. Sa tokenom je vožnja vezana za nalog i vide je samo vlasnikovi zahtevi.

WebSocket treba otvoriti čim je adresa poznata i držati ga otvorenim (sekcija 6).

## 4. TypeScript tipovi

```ts
// ---------- Enumi ----------
export type Behavior =
  | "looking_at_phone" // gleda u telefon
  | "looking_behind"   // gleda iza sebe
  | "turning_around"   // okreće se telom
  | "hands_off_wheel"  // ruke van volana
  | "drowsy"           // pospan
  | "eyes_off_road";   // pogled van puta

export type SafetyLevel = "safe" | "caution" | "warning" | "high_risk" | "critical" | "emergency";
export type DashboardLight = "green" | "green_yellow" | "yellow" | "red";
export type SoundLevel = "none" | "low" | "high";
export type TripStatus = "active" | "ended";
/** Odakle je brzina: mock vožnja backenda (podrazumevano), GPS telefona, ili poslata u ticku (simulator). */
export type SpeedSource = "mock" | "phone" | "telemetry";
export type CameraAlert = "green" | "yellow" | "red";

// ---------- Zahtevi ----------
export interface EmergencyContact {
  name: string;
  phone: string;
}

export interface TripCreate {
  /** Obavezno bez prijave. Sa tokenom se koristi korisničko ime naloga, pa se može izostaviti. */
  driver_id?: string | null;
  /** Bez njega se koristi kontakt sačuvan u nalogu (ako je vozač prijavljen). */
  emergency_contact?: EmergencyContact | null;
}

// ---------- Nalozi ----------
export interface RegisterIn {
  username: string;              // 3–32: a-z, 0-9, ".", "_", "-" (backend ga pretvara u mala slova). Jedinstveno
  password: string;              // 6–128 znakova
  display_name?: string | null;  // podrazumevano = username
  emergency_contact?: EmergencyContact | null;
}

export interface LoginIn {
  username: string;
  password: string;
}

/** Nalog vozača. Lozinka se nikad ne vraća (u bazi je samo njen heš). */
export interface User {
  user_id: string;
  username: string;              // ujedno `driver_id` njegovih vožnji
  display_name: string;
  emergency_contact: EmergencyContact | null;
  created_at: string;            // ISO 8601 UTC
}

/** Odgovor na login i registraciju. `token` šalji kao `Authorization: Bearer <token>`. */
export interface AuthOut {
  token: string;
  token_type: "bearer";
  expires_at: string;            // ISO 8601 UTC, 30 dana od prijave
  user: User;
}

/** PATCH /auth/me: menjaju se samo poslata polja. `emergency_contact: null` briše kontakt. */
export interface UserUpdate {
  display_name?: string;
  emergency_contact?: EmergencyContact | null;
}

/** GPS očitavanje telefona (POST /speed). Šalje se samo ako je `SpeedStatus.phone_enabled`. */
export interface PhoneSpeedIn {
  speed_kmh: number;   // >= 0. Android daje m/s, pa pomnoži sa 3.6
  lat?: number | null;
  lon?: number | null;
}

// ---------- Odgovori ----------
/** Šta kola treba da urade u ovom trenutku. */
export interface CarResponse {
  dashboard_light: DashboardLight;
  vibrate_seat: boolean;
  sound: SoundLevel;
  message: string; // na engleskom, jedna poruka po nivou (plus poruka za alarm modela, sekcija 7)
}

/** Jedna kategorija onako kako je model kamere vidi u ovom trenutku. */
export interface CameraCategory {
  p: number | null;     // verovatnoća da se dešava sada, 0..1
  active: boolean;      // odluka samog modela da je ponašanje uključeno
  run_s: number | null; // koliko neprekidno traje (s)
  r: number | null;     // doprinos te kategorije riziku modela
}

/** Trenutni pogled modela kamere. Samo za prikaz, jer je reakcija kola već u `response`. */
export interface CameraView {
  risk: number | null;                 // trenutni rizik modela, 0..1 (risk.final)
  alert: "green" | "yellow" | "red" | null;
  rules_triggered: string[];           // tvrda pravila modela, npr. "microsleep", "long_distraction"
  /** Ključevi su imena kategorija modela ("phone_use", "eyes_off_road"...), a ne `Behavior`. */
  categories: Record<string, CameraCategory>;
  groups: Record<string, number | null>; // rizik po kanalu: "visual", "manual", "fatigue"
}

/** Stanje vožnje uživo. Stiže posle svakog ticka sa kamere (~2 u sekundi). */
export interface TripState {
  trip_id: string;
  driver_id: string;
  status: TripStatus;
  score: number;      // 0–100, jedna decimala
  level: SafetyLevel;
  /** Ponašanja koja se trenutno vide → koliko sekundi traju. Prazno = vozač je fokusiran. */
  active_behaviors: Partial<Record<Behavior, number>>;
  response: CarResponse;
  /** null ako tick nije stigao od modela (npr. simulator šalje samo labele). */
  camera: CameraView | null;
  speed_kmh: number;                 // brzina korišćena za poslednji tick (0 pre prvog ticka). Ispod 5 km/h nema opasnosti ni upozorenja
  speed_source: SpeedSource | null;  // null pre prvog ticka
  emergency_alert_sent: boolean; // true kada je u ovoj vožnji već bila uzbuna (score < 10 bar 2 s u vožnji)
}

export interface BehaviorSummary {
  behavior: Behavior;
  occurrences: number;   // koliko puta se desilo
  total_seconds: number; // ukupno trajanje
  tip: string;           // savet za vozača, na engleskom
}

/** Statistika vožnje. */
export interface TripSummary {
  trip_id: string;
  driver_id: string;
  status: TripStatus;
  started_at: string;      // ISO 8601 UTC, npr. "2026-11-06T14:12:55.670995Z"
  ended_at: string | null; // null dok vožnja traje
  duration_s: number;
  final_score: number;     // score u trenutku kraja (trenutno stanje, obično ~100 jer kola stoje)
  average_score: number;   // **glavni broj vožnje**: prosek dok se kola kreću (ponderisan vremenom)
  min_score: number;
  level: SafetyLevel;      // nivo za average_score
  emergency_alert_sent: boolean;
  behaviors: BehaviorSummary[]; // najgore prvo; prazan niz = čista vožnja
}

/** Za dashboard kompanije (nije neophodno za aplikaciju vozača). */
export interface BehaviorBreakdown {
  behavior: Behavior;
  occurrences: number;
  total_seconds: number;
  trips_affected: number;
}

export interface AnalyticsOverview {
  total_trips: number;
  completed_trips: number;
  average_final_score: number | null; // null dok nema završenih vožnji
  average_trip_score: number | null;
  emergency_alerts: number;
  behaviors: BehaviorBreakdown[];
}

// ---------- Izveštaj vožnje: sekcije od 2 s (koordinator ih šalje serveru, server ih čuva) ----------
/** none = ništa rizično (ili kola stoje), dangerous = rizično ponašanje u vožnji, critical = "ultra opasno"
 *  (crveni alarm modela, glasan alarm kola ili uzbuna). Odlučuje koordinator, aplikacija samo prikazuje. */
export type DangerLevel = "none" | "dangerous" | "critical";

/** Jedna kategorija modela unutar jedne sekcije. */
export interface SectionCategory {
  p: number | null;      // prosečna verovatnoća u sekciji
  p_max: number | null;
  active: boolean;       // model ju je bar jednom označio kao aktivnu
  r: number | null;      // najveći doprinos riziku modela
  run_s: number | null;  // najduže neprekidno trajanje (s)
}

/** Sekcija vožnje (`section_s` = 2 s): šta je viđeno i koliki je score. Jedna tačka na grafiku vožnje.
 *  Stiže uživo kao WS `section` i u izveštaju (`TripReport.sections`). */
export interface TripSection {
  section_id: string;
  trip_id: string;
  seq: number;              // 0, 1, 2... sekcija n pokriva t od n*section_s do (n+1)*section_s
  t_start: number;          // sekundi od prvog ticka vožnje (x osa grafika)
  t_end: number;
  started_at: string;       // ISO 8601 UTC
  ended_at: string;
  ticks: number;            // koliko je tickova (detekcija modela ili telemetrije) bodovano u sekciji
  score_start: number;      // score neposredno pre sekcije
  score_end: number;        // score na kraju sekcije (y tačke na grafiku)
  score_min: number;
  level: SafetyLevel;       // nivo za score_end
  danger: DangerLevel;
  behaviors: Partial<Record<Behavior, number>>; // ponašanje → sekundi u sekciji (boduje se samo u vožnji)
  speed_kmh: number;        // prosečna brzina
  speed_max_kmh: number;
  speed_source: SpeedSource | null;
  risk: number | null;      // prosečan rizik modela 0..1; null bez detekcija modela
  risk_max: number | null;
  alert: CameraAlert | null;            // najgori alarm modela u sekciji
  rules_triggered: string[];
  categories: Record<string, SectionCategory>; // ključevi su imena kategorija modela
  groups: Record<string, number | null>;       // najveći rizik po kanalu: visual, manual, fatigue
  dashboard_light: DashboardLight;      // najozbiljnije svetlo u sekciji
  vibrate_seat: boolean;                // sedište je bar jednom vibriralo
  sound: SoundLevel;                    // najglasniji zvuk u sekciji
  emergency: boolean;                   // uzbuna je okinula u ovoj sekciji
  image_t: number | null;               // kada (ista osa kao t_start) je snimljena slika sekcije
  lat: number | null;                   // samo sa GPS-om telefona
  lon: number | null;
  has_image: boolean;                   // koordinator je priložio frejm najrizičnijeg trenutka
  image_url: string | null;             // JPEG tog frejma (opasne sekcije sa videom). Uživo (WS) je uvek null
}

/** Opasan momenat: uzastopne opasne sekcije spojene u jedan (jedna mirna sekcija u sredini se premošćuje).
 *  Na grafiku: čvor na (`peak_t`, `peak_score`), a za `critical` i kućica sa slikom iznad čvora. */
export interface DangerMoment {
  moment_id: string;       // id prve sekcije momenta
  t_start: number;
  t_end: number;
  duration_s: number;
  danger: DangerLevel;     // najgora sekcija; critical = "ultra opasno"
  peak_t: number;          // x čvora: vreme slike, inače sredina najgore sekcije
  peak_score: number;      // y čvora
  behaviors: Partial<Record<Behavior, number>>; // sekundi po ponašanju, najduže prvo
  categories: Record<string, number>;           // kategorije modela aktivne u momentu → najveće p
  rules_triggered: string[];
  alert: CameraAlert | null;
  peak_risk: number | null;
  score_start: number;
  score_end: number;
  score_min: number;
  score_drop: number;      // score_start - score_min: koliko je momenat koštao
  level: SafetyLevel;      // najgori dostignut nivo
  speed_avg_kmh: number;
  speed_max_kmh: number;
  image_url: string | null; // slika najrizičnijeg frejma momenta
  section_ids: string[];
}

// ---------- Brzina ----------
export interface SpeedStatus {
  source: SpeedSource | null;  // izvor za poslednji tick aktivne vožnje; null bez vožnje
  speed_kmh: number | null;
  scenario: string;            // mock vožnja aktivne vožnje (ili podešeni SPEED_SCENARIO)
  scenarios: string[];         // dostupne mock vožnje
  phone_enabled: boolean;      // true = backend prima i preferira GPS brzinu telefona
  phone_age_s: number | null;  // sekundi od poslednjeg očitavanja telefona
}

// ---------- Izveštaj modela kamere (deo izveštaja) ----------
/** Statistika jedne kategorije modela kroz celu vožnju (samo dok se kola kreću). */
export interface ModelCategoryStats {
  active_s: number;       // sekundi koliko ju je model držao aktivnom
  episodes: number;       // epizode od bar 0.5 s
  max_episode_s: number;
}

/** Jedna epizoda ponašanja kako je model vidi: kategorija aktivna, kratki prekidi spojeni. */
export interface ModelEpisode {
  category: string;       // ime kategorije modela ("phone_use", "eyes_off_road"...)
  t_start: number;        // sekunde od prvog ticka (ista osa kao TripSection.t_start)
  t_end: number;
  duration_s: number;
  peak_r: number;         // najveći doprinos riziku modela
  peak_p: number;         // najveće sirovo p među primljenim frejmovima (~2/s)
  open: boolean;          // još traje (aktivna vožnja) ili je trajala do kraja vožnje
}

/** Od trenutka kad alarm modela napusti zeleno do povratka na zeleno. */
export interface ModelAlertEpisode {
  t_start: number;
  t_end: number;
  duration_s: number;
  max_level: CameraAlert;
  peak_risk: number;
  causes: string[];       // kategorije koje su nosile rizik i "rule:<ime>" za tvrda pravila
  open: boolean;
}

/** Pogled modela kamere na celu vožnju. Računa ga backend iz toka frejmova modela.
 *  Samo za prikaz i analizu: score vozača je `TripSummary`. Vreme stajanja (< 5 km/h) se ne broji. */
export interface ModelReport {
  frames: number;                 // primljenih frejmova modela
  duration_s: number;             // sekundi frejmova modela dok se kola kreću
  stationary_s: number;           // sekundi frejmova dok kola stoje (ne ulaze u statistiku)
  risk_mean: number;              // vremenski prosek rizika modela 0..1
  risk_rms: number;               // koren srednjeg kvadrata: duži rizični periodi teže više
  risk_p95: number;
  risk_max: number;
  model_score: number;            // 100 * (1 - risk_rms): ocena vožnje po modelu, 0..100
  time_in_alert_s: Record<CameraAlert, number>;
  time_in_alert_frac: Record<CameraAlert, number>;
  alerts: Record<string, number>;          // koliko puta je alarm porastao na "yellow" / "red"
  alerts_per_hour: Record<string, number>;
  rules: Record<string, number>;           // tvrdo pravilo → koliko puta je opalilo
  categories: Record<string, ModelCategoryStats>; // ključevi su imena kategorija modela
  episodes: ModelEpisode[];                // od najstarije, najviše 200
  alert_episodes: ModelAlertEpisode[];     // od najstarije, najviše 200
}

// ---------- Izveštaj jedne vožnje ----------
/** Sve o jednoj vožnji u jednom odgovoru (GET /trips/{id}/report). */
export interface TripReport {
  trip: TripSummary;        // rezime: final/prosek/min score, trajanje, ponašanja sa savetima
  user: User | null;        // ko je vozio; null ako je vožnja pokrenuta bez prijave
  section_s: number;        // sekundi po sekciji (2)
  /** Vožnja sekcija po sekcija, od najstarije. Grafik pravi aplikacija. */
  sections: TripSection[];
  /** Opasni momenti sa slikom najrizičnijeg frejma, od najstarijeg. */
  moments: DangerMoment[];
  /** Izveštaj modela kamere za celu vožnju; null ako nijedan frejm modela nije stigao (npr. simulator). */
  model: ModelReport | null;
}

// ---------- WebSocket ----------
export type LiveMessage =
  | { type: "trip_started"; data: TripState }
  | { type: "state"; data: TripState }
  | { type: "emergency"; data: TripState }
  | { type: "section"; data: TripSection }
  | { type: "trip_ended"; data: TripSummary };

// ---------- Greške ----------
export interface ValidationIssue {
  type: string;
  loc: (string | number)[];
  msg: string;
  input: unknown;
}

export interface ApiError {
  detail: string | ValidationIssue[]; // string za 404/409, niz za 422
}
```

## 5. REST endpointi

Sve putanje su relativne u odnosu na `http://<IP>:8000/api/v1`. Uz svaku rutu piše deo backenda koji je
služi: **[K]** koordinator (uživo, u kolima) ili **[S]** server (čuvanje, istorija, nalozi).

### `GET /health` [K, S]
Provera veze. Odgovor `200`: `{"status": "ok"}`

### `POST /trips`: početak vožnje [K]
Telo `TripCreate`:
```json
{ "driver_id": "driver-1", "emergency_contact": { "name": "Ana", "phone": "+381601234567" } }
```
Odgovor `201`, `TripState`:
```json
{
  "trip_id": "ccb851e4019f4ce6b2b1b248f21a09a3",
  "driver_id": "driver-1",
  "status": "active",
  "score": 100.0,
  "level": "safe",
  "active_behaviors": {},
  "response": {
    "dashboard_light": "green",
    "vibrate_seat": false,
    "sound": "none",
    "message": "All good - you're driving safely."
  },
  "camera": null,
  "speed_kmh": 0.0,
  "speed_source": null,
  "emergency_alert_sent": false
}
```
- U jednom trenutku postoji samo **jedna aktivna vožnja** (jedan auto). Ako je neka i dalje aktivna,
  backend je prvo završi. Preko WebSocket-a tada stižu `trip_ended` (stara), pa `trip_started` (nova).
- `trip_id` treba sačuvati, jer je potreban za završetak vožnje.
- **Sa tokenom** (`Authorization: Bearer ...`) vožnja pripada nalogu: `driver_id` = korisničko ime, a
  kontakt za hitne slučajeve je iz naloga ako ga telo ne pošalje. Telo može biti i prazno `{}`.
- Greške: `422` ako fali `driver_id`, a vozač nije prijavljen. `401` ako je token pogrešan ili istekao.
- Kola ne čekaju server: ako koordinator ne može da proveri token (server ne odgovara), vožnja ipak kreće.
  Token koji je već video važi po poslednjem odgovoru. Za nov token je `driver_id` iz tela (ili
  `"unverified-login"`), a server vožnju upiše na nalog kad je primi. Do tada je u istoriji nema.

### `POST /trips/{trip_id}/end`: kraj vožnje [K]
Bez tela. Odgovor `200`, `TripSummary`:
```json
{
  "trip_id": "ccb851e4019f4ce6b2b1b248f21a09a3",
  "driver_id": "driver-1",
  "status": "ended",
  "started_at": "2026-11-06T14:12:55.670995Z",
  "ended_at": "2026-11-06T14:20:11.687596Z",
  "duration_s": 436.0,
  "final_score": 100.0,
  "average_score": 97.9,
  "min_score": 77.3,
  "level": "safe",
  "emergency_alert_sent": false,
  "behaviors": [
    {
      "behavior": "looking_at_phone",
      "occurrences": 1,
      "total_seconds": 6.0,
      "tip": "Put your phone in a holder or turn on Do Not Disturb while driving."
    }
  ]
}
```
- Može se pozvati više puta. Ako je vožnja već završena, samo vrati statistiku.
- Koordinator pre odgovora čeka (najviše 3 s) da server primi celu vožnju, pa `GET /trips/{id}/report`
  odmah posle kraja ima i poslednju sekciju.
- Greške: `404` ako vožnja ne postoji (npr. backend je restartovan).

### `GET /trips/{trip_id}`: trenutno stanje [K]
Odgovor `200`, `TripState`. Samo za vožnju koja upravo traje (iz memorije). Uglavnom nije potreban,
jer stanje stiže preko WebSocket-a. Greške: `404`.

### `GET /trips/{trip_id}/summary`: statistika [S]
Odgovor `200`, `TripSummary`, iz Postgresa (preživi restart). Za aktivnu vožnju (`ended_at: null`) je to
rezime do poslednje sekcije (najviše ~2 s unazad). Greške: `404`, `503` ako je baza dole.

### `GET /trips`: istorija [S]
Odgovor `200`, `TripSummary[]`, od najstarije ka najnovijoj, uključujući i aktivnu vožnju. Čita se
iz Postgresa, pa preživi restart. `503` ako je baza dole (koordinator ne čuva istoriju).
- **Sa tokenom:** vožnje tog naloga (`driver_id` se ignoriše).
- **Bez tokena:** vožnje pokrenute bez prijave. `?driver_id=driver-1` sužava na jednog vozača.

**Ko šta vidi:** vožnju pokrenutu sa tokenom vide samo zahtevi sa tokenom istog naloga. Svi ostali
dobijaju `404`, kao da ne postoji (`/summary`, `/report`, `/sections`, `GET /trips/{id}`).
Vožnje bez prijave vidi svako, kao ranije. Živi kanal (WebSocket, `POST /trips/{id}/end`) ostaje
otvoren, jer je to mreža samih kola.

### `POST /auth/register`: novi nalog [S]
Telo `RegisterIn`:
```json
{ "username": "ana", "password": "tajna-123", "display_name": "Ana Anić",
  "emergency_contact": { "name": "Marko", "phone": "+381601234567" } }
```
Odgovor `201`, `AuthOut` (vozač je odmah prijavljen):
```json
{
  "token": "Jx3...b9Q",
  "token_type": "bearer",
  "expires_at": "2026-12-06T17:23:40.971406Z",
  "user": {
    "user_id": "fd0f4be4e5b14d4b99ce0fb0710c820f",
    "username": "ana",
    "display_name": "Ana Anić",
    "emergency_contact": { "name": "Marko", "phone": "+381601234567" },
    "created_at": "2026-11-06T17:23:40.971406Z"
  }
}
```
Greške: `409` ako je korisničko ime zauzeto, `422` za loše ime ili lozinku kraću od 6 znakova.

### `POST /auth/login`: prijava [S]
Telo `LoginIn` `{ "username": "ana", "password": "tajna-123" }`. Odgovor `200`, `AuthOut`.
Greška: `401` `{"detail": "Wrong username or password"}` (isto i za nepostojeće ime).
Token treba sačuvati (AsyncStorage) i slati u svakom zahtevu kao `Authorization: Bearer <token>`.
Na `401` za sačuvani token aplikacija treba da obriše token i ponovo traži prijavu.

### `GET /auth/me`, `PATCH /auth/me`, `POST /auth/logout` [S]
- `GET /auth/me` → `User` (ko je prijavljen). Za ekran profila.
- `PATCH /auth/me` sa `UserUpdate` → `User`. Menja ime ili kontakt za hitne slučajeve.
- `POST /auth/logout` → `204`. Briše samo ovaj token (drugi uređaji ostaju prijavljeni).
- Svi traže token, inače `401`.

### `GET /analytics/overview`: za kompaniju [S]
Odgovor `200`, `AnalyticsOverview`, iz Postgresa. Sadrži samo agregate, bez slika i bez podataka po vozaču.
Nije potreban u aplikaciji vozača.

### `GET /trips/{trip_id}/report`: sve o jednoj vožnji [S]
Odgovor `200`, `TripReport`: `trip` (rezime kao `TripSummary`), `user` (ko je vozio), `section_s` (2),
`sections` (vožnja, sekcija po sekcija od 2 s) i `moments` (opasni momenti sa slikom). **Jedan poziv za
ekran izveštaja.** Grafik pravi aplikacija (§7): x osa `t_start`/`t_end`, y `score_end`, osenčene sekcije
sa `danger` ≠ `none`, čvor po momentu na (`peak_t`, `peak_score`) i za `critical` kućica sa `image_url`.
Šta je viđeno u nekom delu vožnje je u sekciji (`behaviors` u sekundama, `categories` modela, `alert`,
`rules_triggered`, `risk_max`) i u momentu (zbirno). Radi i za aktivnu vožnju (do poslednje sekcije) i
posle restarta backenda.
`model` je pogled modela kamere na celu vožnju (`ModelReport`): vreme po boji alarma, koliko puta je
alarm porastao, tvrda pravila, epizode po kategoriji (npr. "telefon 12 s od t=13") i epizode alarma
sa uzrocima. Računa ga koordinator iz svakog ticka sa frejmom modela (`/telemetry` ili model worker,
`backend/app/services/model_report.py`) i šalje serveru uz svaku sekciju, pa je za aktivnu vožnju star
najviše jednu sekciju (~2 s). `null` ako nije stigao nijedan frejm modela.
Greške: `404` ako vožnja ne postoji ili pripada drugom nalogu. `503` ako je čuvanje isključeno ili Postgres
nije dostupan (tada sakrij izveštaj umesto greške).

Primer jednog momenta:
```json
{
  "moment_id": "9d347aaac3834f818bbcaeef6d1d4128",
  "t_start": 14.0, "t_end": 22.0, "duration_s": 8.0,
  "danger": "critical",
  "peak_t": 19.297, "peak_score": 71.3,
  "behaviors": { "looking_at_phone": 5.7, "eyes_off_road": 5.5 },
  "categories": { "eyes_off_road": 0.9, "phone_use": 0.9 },
  "rules_triggered": ["long_distraction", "phone_sustained"],
  "alert": "red", "peak_risk": 0.944,
  "score_start": 100.0, "score_end": 71.3, "score_min": 71.3, "score_drop": 28.7,
  "level": "warning",
  "speed_avg_kmh": 52.2, "speed_max_kmh": 56.1,
  "image_url": "http://192.168.43.57:8000/api/v1/media/sections/a91741d4.../9d347aaa....jpg",
  "section_ids": ["9d347aaa...", "5c0e...", "b81f...", "e2d4..."]
}
```

### `GET /trips/{trip_id}/sections?after_seq=N`: samo sekcije [S]
Odgovor `200`, `TripSection[]` (isto kao `report.sections`), od najstarije. Sa `after_seq=N` samo sekcije
posle sekcije N, npr. za osvežavanje grafika aktivne vožnje. Greške kao za `report`.

### `GET /media/{key}`: slika momenta [S]
Vraća sliku iz S3 (`image/jpeg`) i podržava `Range`. URL-ove ne sklapaj sam, nego koristi `image_url` iz
sekcije ili momenta. Idu preko backenda (port 8000), pa rade preko hotspota bez obzira na IP.
Greške: `404`, `503`.

### `GET /coordinator/status`: dijagnostika [K]
Da li kamera šalje (fps), da li je model povezan i koliko brzo odgovara, veličina video keša i da li
server prima sekcije. Za debug i demo, nije deo ugovora sa aplikacijom (polja se mogu menjati).

### `GET /speed`: odakle dolazi brzina [K]
Odgovor `200`, `SpeedStatus`. Kamera ne zna brzinu. Backend je uzima ovim redom:
1. **GPS telefona** (`POST /speed`), samo ako je `phone_enabled` i očitavanje nije starije od 5 s;
2. `speed_kmh` iz samog ticka (simulator, testovi);
3. **mock vožnja** backenda: scenario (`city`, `highway`, `stop_and_go`, `country_road`, `cruise`,
   `parked`) izabran po vožnji, sa glatkim ubrzavanjem i kočenjem (Bezier), uključujući stajanje na 0 km/h.

### `POST /speed`: GPS brzina telefona (opciono, podrazumevano isključeno) [K]
Telo `PhoneSpeedIn`: `{ "speed_kmh": 47.5, "lat": 44.8125, "lon": 20.4612 }`. Odgovor `200`, `SpeedStatus`.
Slati ~1/s tokom vožnje, i to **samo ako `GET /speed` vrati `phone_enabled: true`** (backend sa
`PHONE_SPEED_ENABLED=true`). Inače `409`. Sveže očitavanje telefona ima prednost nad mock brzinom,
a `lat`/`lon` se upisuju u izveštaj. Ovo je za kola bez sopstvene računarske snage, gde telefon zna brzinu.

### `POST /telemetry`: NIJE za aplikaciju, samo debug [K]
Ovo zovu simulator (`notebooks/safety_client.py`, `tools/sim.py`) ili, za debug, pipeline CV tima koji sam
računa rizik (`risk_pipeline.py --mode prod`). Pravi put su kamera i model preko koordinatora
(`WS /camera/ws` i `WS /model/ws`, vidi ispod), gde rizik računa koordinator. Aplikacija ga ne koristi.
Dok je model worker povezan, zapis frejma (`frame`) dobija `409`, a labele simulatora i dalje prolaze.
Model šalje svoj zapis frejma neizmenjen (bez `perception`), a backend preslikava njegove aktivne
kategorije na `Behavior` (`phone_use` → `looking_at_phone`, `eyes_closed` i `drowsiness` → `drowsy`...,
tabela u `backend/README.md`) i prosleđuje `camera` aplikaciji. U `camera.categories` mogu da stignu i
kategorije koje se ne boduju (npr. `eating_drinking`), pa ih prikaži sirovim imenom.
`speed_kmh` je opciono i model ga ne šalje: brzinu daje backend (`GET /speed`). Simulator ga šalje
da bi vožnja kroz nivoe bila ista svaki put.
Za debug ga šalje `python notebooks/risk_pipeline.py --video 0 --mode prod` (~2/s plus svaka promena
alarma, i JPEG video na `/video/frames`). Iz istog toka backend pravi i `TripReport.model`.

### `POST /video/frames`: NIJE za aplikaciju [K]
Jedan JPEG frejm kamere kao telo (`Content-Type: image/jpeg`), npr. `SafetyClient.send_video_frame`.
Frejm ide u video keš koordinatora (5 min) i modelu, ako je povezan. Odgovor `204`. Greške: `409` bez
aktivne vožnje, `415` ako nije `image/jpeg`, `413` preko 2 MB, `422` ako telo nije JPEG.

### `WS /camera/ws` i `WS /model/ws`: NISU za aplikaciju [K]
Kamera šalje jedan JPEG po binarnoj poruci (`tools/camera_stream.py`), a model worker (`model/worker.py`)
prima frejmove i vraća detekcije. Protokol je u [ARCHITECTURE.md](ARCHITECTURE.md).

Primer: ovo aplikacija dobija u `camera` kad tick stigne od modela:
```json
"camera": {
  "risk": 0.819,
  "alert": "red",
  "rules_triggered": ["long_distraction", "phone_sustained"],
  "categories": {
    "phone_use":     { "p": 0.715, "active": true, "run_s": 3.2, "r": 0.534 },
    "eyes_off_road": { "p": 0.905, "active": true, "run_s": 3.4, "r": 0.767 }
  },
  "groups": { "visual": 0.767, "manual": 0.374, "fatigue": 0.0 }
}
```

## 6. WebSocket `ws://<IP>:8000/api/v1/ws`

Svaka poruka sa servera je JSON `LiveMessage`: `{"type": ..., "data": ...}`.

| `type` | Kada stiže | `data` |
|---|---|---|
| `state` | ~2/s dok vožnja traje (model daje 5–10 detekcija/s, pa koordinator šalje na 0.5 s i odmah na svaku promenu nivoa, reakcije ili ponašanja; simulator: posle svakog ticka), i **odmah po povezivanju** ako vožnja traje | `TripState` |
| `trip_started` | počela je vožnja | `TripState` |
| `emergency` | score je pao ispod 10, jednom po vožnji, odmah posle `state` iz istog ticka | `TripState` |
| `section` | na svake 2 s vožnje (i poslednja kad se vožnja završi): rezime sekcije, šta je viđeno, opasnost | `TripSection` (`image_url` je uvek `null`) |
| `trip_ended` | vožnja je završena | `TripSummary` |

- Ako nema aktivne vožnje, posle povezivanja ne stiže ništa dok ne stigne `trip_started`.
- Nepoznat `type` aplikacija treba da ignoriše (tako je `section` dodat bez lomljenja starih klijenata).
- Server ignoriše poruke koje aplikacija pošalje. Socket služi samo za prijem.
- Socket se prekida kad hotspot zabode ili aplikacija ode u pozadinu, pa aplikacija mora sama da se
  **ponovo poveže**. Po povezivanju odmah dobija trenutni `state`.
- Ako vožnja počne ili se završi sa drugog uređaja (npr. simulator), aplikacija to vidi preko
  `trip_started` / `trip_ended`.

Primer klijenta sa ponovnim povezivanjem:

```ts
export function connectLive(host: string, onMessage: (msg: LiveMessage) => void): () => void {
  // host = "192.168.43.57:8000"
  let ws: WebSocket | null = null;
  let attempt = 0;
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const open = () => {
    ws = new WebSocket(`ws://${host}/api/v1/ws`);
    ws.onopen = () => { attempt = 0; };
    ws.onmessage = (event) => onMessage(JSON.parse(event.data) as LiveMessage);
    ws.onclose = () => {
      if (!stopped) timer = setTimeout(open, Math.min(1000 * 2 ** attempt++, 10_000));
    };
  };

  open();
  return () => { stopped = true; clearTimeout(timer); ws?.close(); };
}
```

## 7. Kako prikazati stanje

**Backend je izvor istine.** Aplikacija ne računa nivo iz score-a i ne odlučuje sama kad treba
upozorenje, nego prikazuje ono što piše u `response`.

| Polje | Prikaz |
|---|---|
| `response.dashboard_light` | velika lampica / pozadina. Predlog boja: `green` #22C55E, `green_yellow` #A3E635, `yellow` #FACC15, `red` #EF4444 |
| `score` | veliki broj 0–100 (ili prsten / gauge). **Trenutno stanje**: pada dok traje rizično ponašanje i vraća se na 100 nekoliko sekundi posle (nije bodovni saldo) |
| `response.vibrate_seat` | simulira vibraciju sedišta. Za svaku `state` poruku gde je `true`, kratko zavibrira telefon (`Vibration` / `expo-haptics`). Poruke stižu ~2/s, pa to daje ritmičnu vibraciju koja prestaje čim polje postane `false` |
| `response.sound` | `low` je tihi signal, `high` glasan. Pušta se kratak zvuk po poruci, isto kao vibracija (`expo-audio` / `expo-av`) |
| `response.message` | tekst ispod lampice. Ako aplikacija nije na engleskom, napravi svoj tekst po `level` |
| `active_behaviors` | ikonice ili čipovi trenutnih ponašanja sa trajanjem u sekundama |
| `level` | naziv nivoa (tabela ispod) |
| `camera` | opciono, "šta kamera vidi": trake `p` po kategoriji, `risk` modela, `rules_triggered`. Može biti `null` i može imati nepoznate kategorije (prikaži sirovo ime). **Ne pokreći alarm na osnovu `camera.alert`**, to je već uračunato u `response` |
| `speed_kmh` | brzinomer. Ispod 5 km/h nema opasnosti ni upozorenja (npr. semafor), pa je korisno da se vidi. Brzina pojačava opasnost (×0.4 pri hodu, ×1 na 50, ×1.6 na 130 km/h). `speed_source` može da ide sitno ispod (`mock` / `phone`) |

**Score** (backend, `coordinator/services/scoring.py`): opasnost ponašanja koja se sada vide (raste što duže
traje) ili rizik modela, puta faktor brzine, daje cilj `100 × (1 − opasnost)`; score ga prati (pada za ~1 s,
vraća se za ~6–8 s). Dok kola stoje (< 5 km/h) cilj je 100 i nema upozorenja, šta god vozač radi.

Nivoi (informativno, logika je na backendu):

| `level` | Score | Svetlo | Reakcija kola (samo dok se kola kreću i nešto rizično se dešava) |
|---|---|---|---|
| `safe` | 90–100 | zeleno | ništa |
| `caution` | 75–90 | zeleno-žuto | samo svetlo |
| `warning` | 55–75 | žuto | vibracija + tihi zvuk |
| `high_risk` | 35–55 | žuto | vibracija + glasan zvuk |
| `critical` | 10–35 | crveno | vibracija + glasan zvuk |
| `emergency` | < 10 | crveno | isto; posle 2 s u vožnji i događaj `emergency` (jednom po vožnji) |

Vibracija i zvuk prestaju čim ponašanje prestane, a svetlo se vraća zajedno sa score-om. Dok kola stoje:
zeleno svetlo, bez vibracije i zvuka, poruka `"Standing still - no warnings."`.

**Alarm modela:** kad model kamere javi crveno (`camera.alert == "red"`, npr. mikrospavanje ili dug
pogled van puta), kola **odmah** vibriraju i glasno pište na bilo kom nivou, ali samo dok se kreću.
Svetlo i dalje prati score. Ako je nivo `safe`, poruka je `"Danger detected - eyes on the road now."`.

Nazivi ponašanja za prikaz:

| `Behavior` | Srpski | English |
|---|---|---|
| `looking_at_phone` | Gleda u telefon | Looking at phone |
| `looking_behind` | Gleda iza sebe | Looking behind |
| `turning_around` | Okreće se | Turning around |
| `hands_off_wheel` | Ruke van volana | Hands off the wheel |
| `drowsy` | Pospanost | Drowsiness |
| `eyes_off_road` | Pogled van puta | Eyes off the road |

**Uzbuna (`emergency`):** prikaži preko celog ekrana (crveno, glasan zvuk). Backend trenutno **ne
šalje pravi SMS**, samo loguje. Predlog, još nije dogovoreno: aplikacija ponudi slanje SMS-a kontaktu
(`expo-sms` ili `Linking.openURL("sms:...")`), jer telefon ima SIM karticu i mrežu.

**Kraj vožnje (`trip_ended` ili odgovor na `POST /end`):** ekran sa statistikom. Prikaži
`average_score` (prosek dok se kola kreću, glavni broj) sa `level`, pored njega `min_score`, a zatim
`behaviors` kao listu sa `tip` savetima. Prazan `behaviors` znači da je vožnja bila bez grešaka.

**Izveštaj (grafik vožnje):** sa ekrana statistike, jedan `GET /trips/{id}/report`:
- zaglavlje iz `report.trip` (kao statistika) i `report.user.display_name`;
- **grafik**: linija `score_end` kroz `t_end` (početna tačka je `sections[0].score_start` na t = 0),
  pozadina sekcija sa `danger` = `dangerous` (žuto-narandžasto) i `critical` (crveno);
- **čvor** za svaki momenat na (`peak_t`, `peak_score`); za `critical` ("ultra opasno") **kućica sa
  slikom** (`image_url`) iznad čvora, povezana linijom. Ako se kućice preklapaju, drugi red iznad, ili
  samo čvor;
- tap na čvor ili sliku: detalji momenta: slika, `behaviors` (sekunde), `categories` (p modela),
  `rules_triggered`, `-score_drop` poena, brzina;
- lista "Opasni momenti" (najveći `score_drop` prvo).

Uživo (Drive ekran) poslednje `section` poruke daju traku "poslednji minut" (30 sekcija) i red "šta je
viđeno u poslednje 2 s". Opasnost i nivo računa backend: aplikacija samo boji.

Momenti bez slike (`image_url: null`, npr. nije bilo videa) se prikazuju bez kućice. Ako `report` vrati
`503`, čuvanje ne radi (Postgres dole), pa sakrij grafik umesto da prikažeš grešku.

## 8. Greške

| Status | Kada | Telo |
|---|---|---|
| `401` | pogrešan ili istekao token, pogrešna lozinka, `/auth/me` bez tokena | `{"detail": "Invalid or expired token - log in again"}` |
| `404` | nepoznat `trip_id`, ili vožnja drugog naloga | `{"detail": "Trip <id> not found"}` |
| `409` | `POST /auth/register` sa zauzetim imenom | `{"detail": "Username ana is taken"}` |
| `409` | `/telemetry` ili `/video/frames` bez aktivne vožnje | `{"detail": "No active trip - start one from the app first"}` |
| `409` | `POST /speed` dok je GPS telefona isključen na backendu | `{"detail": "Phone speed is disabled (PHONE_SPEED_ENABLED=false); ..."}` |
| `409` | `/telemetry` sa zapisom frejma dok je model worker povezan (debug put ne meša se sa pravim) | `{"detail": "A model worker is connected and drives the score: ..."}` |
| `503` | `/report`, `/sections`, `/summary`, `GET /trips`, `/media`, `/auth/*`: čuvanje je isključeno ili Postgres / S3 nisu dostupni | `{"detail": "Postgres is unreachable (...)"}` |
| `503` | `GET /trips/{id}` sa tokenom koji koordinator nikad nije proverio, dok server ne odgovara (`POST /trips` tada ipak kreće, vidi §5) | `{"detail": "Can't check the login: ..."}` |
| `403` | `/internal/*` bez ispravnog `X-Internal-Token` (ruta za koordinator, ne za aplikaciju) | `{"detail": "Internal route: ..."}` |
| `422` | loše telo zahteva | `{"detail": [{"type": "missing", "loc": ["body", "driver_id"], "msg": "Field required", "input": {}}]}` |

Na `404` za sačuvani `trip_id` aplikacija treba da se vrati na ekran za početak vožnje.

## 9. Testiranje bez modela i bez auta

1. U `backend/`: `docker compose up -d` (Postgres + RustFS; ili `.\scripts\services.ps1 start`), pa
   `python run.py` (zapiši IP).
2. Poveži aplikaciju na taj IP.
3. **Ceo tok kamera → model → koordinator** bez kamere i bez CV paketa (iz korena repoa, backend venv):
   `python tools/camera_stream.py` (test slika, 10 fps) i `python model/worker.py --fake` (skriptovane
   detekcije u krugu od 60 s: telefon, pogled van puta, mikrospavanje, ruke van volana). Pokreni vožnju iz
   aplikacije. Stižu `state` i `section`, a na kraju izveštaj ima sekcije, momente i slike.
   Pravi model: `model/README.md`. Snimak umesto test slike: `camera_stream.py --video snimak.mp4`.
4. **Simulator bez videa:** `python notebooks/safety_client.py` (sa `--interval 0.3` ide brže).
   Simulator sam pokrene vožnju, prođe kroz sve nivoe od zelenog do uzbune i završi vožnju.
   Šalje samo labele, pa je `camera` tada `null`, a sekcije nemaju slike.
5. Sa snimljenim izlazom modela: `python notebooks/safety_client.py --replay frames.jsonl`
   (`--speedup 2` ide duplo brže, `--speed-kmh 90` zakuca brzinu). Tada `camera` stiže popunjen.
6. `--backend-speed`: simulator ne šalje brzinu, nego je određuje mock vožnja backenda.
7. `GET /coordinator/status` pokazuje kameru, model, video keš i isporuku serveru.
8. Debug: pipeline CV tima na snimku iz kabine, bez telefona: `python notebooks/risk_pipeline.py --video
   snimak.mp4 --mode prod --start-trip demo` (pokrene i završi vožnju sam, ide brzinom snimka i šalje video).
   Rizik tada računa pipeline, ne koordinator. Radi samo bez model worker-a (inače `409`).

Simulator pokreće svoju vožnju, pa završava vožnju koju je aplikacija eventualno pokrenula
(pravilo jedne aktivne vožnje). Ne puštaj simulator i model istovremeno: oba boduju istu vožnju.

## 10. Ograničenja

- Uživo stanje aktivne vožnje (`GET /trips/{id}`, WebSocket) je u memoriji koordinatora. Istorija,
  statistika, sekcije i izveštaj su na serveru (Postgres, slike u S3) i preživljavaju restart. Ako
  koordinator padne usred vožnje, ta vožnja ostaje sa rezimeom do poslednje sekcije (~2 s ranije) i
  zatvori se kad se koordinator ponovo pokrene.
- Dok server ne radi, koordinator drži sekcije u memoriji (do 10 000 po vožnji, 300 MB slika) i šalje ih
  kad se server vrati. Istorija i izveštaj su za to vreme `503`.
- Nalozi: nema reseta ni promene lozinke, potvrde emaila ni uloga. Token važi 30 dana.
- `started_at` / `ended_at` su u UTC (`Z`). Za prikaz ih pretvori u lokalno vreme.
- `duration_s` se računa iz vremena tickova, a ne iz `started_at` / `ended_at`.
- Brzinu daje koordinator (mock vožnja, u pravim kolima CAN). GPS telefona (`POST /speed`) postoji, ali je
  podrazumevano isključen (`PHONE_SPEED_ENABLED=false`).
- Slika momenta je jedan frejm (najrizičniji), ne video. Video celog momenta je planiran (ARCHITECTURE.md).
- Slike su za demo u **javnom** lokalnom bucketu (RustFS). Kompanija (`/analytics`) nikad ne dobija slike.
