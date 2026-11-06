# API ugovor: backend ↔ mobilna aplikacija

Ovo je **izvor istine** za komunikaciju React Native aplikacije sa backendom. Kad se backend
promeni, menja se i ovaj fajl.

> **Za Claude koji pravi frontend:** koristi tačno ove rute, polja i tipove (sekcija 4 se može
> kopirati u `src/api/types.ts`). Ne izmišljaj endpointe ni polja. Ako nešto fali, to je izmena
> backenda, pa to reci developeru umesto da pretpostavljaš. Aplikacija **ne šalje telemetriju**,
> to rade modeli za kameru.

## 1. Šta aplikacija radi

1. Povezuje se na backend (laptop) preko hotspota telefona.
2. Vozač se registruje ili prijavi (korisničko ime + lozinka), pa pokreće vožnju. Bez prijave i dalje
   može, sa svojim ID-jem i kontaktom za hitne slučajeve, kao ranije.
3. Tokom vožnje uživo prikazuje dashboard: svetlo, score, trenutna rizična ponašanja, poruku.
   Simulira vibraciju sedišta i zvučni signal.
4. Kad score padne ispod 10, prikazuje uzbunu za hitan slučaj.
5. Vozač završava vožnju i vidi statistiku sa savetima.
6. Izveštaj vožnje (`GET /trips/{id}/report`, sve u jednom pozivu): rezime, ko je vozio, sirovi zapis
   vožnje po sekundi za grafike (score, brzina, rizik modela...) i najgori momenti sa slikom i video klipom.
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
                       Izveštaj ── GET /trips/{id}/report (rezime + korisnik + uzorci za grafike + momenti sa slikama)
Istorija ── GET /trips (sa tokenom: moje vožnje) ──► Statistika / Izveštaj pojedinačne vožnje
Profil ── GET /auth/me, PATCH /auth/me (ime, kontakt za hitne slučajeve), POST /auth/logout
```

Prijava nije obavezna: bez tokena sve radi kao ranije (`driver_id` u `POST /trips`). Sa tokenom je
vožnja vezana za nalog i vide je samo vlasnikovi zahtevi.

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
  speed_kmh: number;                 // brzina korišćena za poslednji tick (0 pre prvog ticka). Ispod 5 km/h nema penala
  speed_source: SpeedSource | null;  // null pre prvog ticka
  emergency_alert_sent: boolean; // true kada je u ovoj vožnji već bila uzbuna (score < 10)
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
  final_score: number;     // "finalni koeficijent": score na kraju vožnje
  average_score: number;   // prosek tokom cele vožnje (ponderisan vremenom)
  min_score: number;
  level: SafetyLevel;      // nivo za final_score
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

// ---------- Izveštaj vožnje (iz Postgresa, radi i posle restarta backenda) ----------
/** Jedna kategorija modela unutar jednog prozora. */
export interface SampleCategory {
  p: number | null;      // prosečna verovatnoća u prozoru
  p_max: number | null;
  active: boolean;       // model ju je bar jednom označio kao aktivnu
  r: number | null;      // najveći doprinos riziku modela
  run_s: number | null;  // najduže neprekidno trajanje (s)
}

/** Sve o vožnji, sabrano po prozoru od `TripTimeline.window_s` sekundi (1 s). */
export interface TripSample {
  t: number;              // sekundi od prvog ticka vožnje (x osa grafika)
  ts: string;             // ISO 8601 UTC
  ticks: number;          // broj tickova u prozoru
  speed_kmh: number;      // prosečna brzina u prozoru
  speed_max_kmh: number;
  speed_source: SpeedSource;
  score: number;          // score na kraju prozora
  score_min: number;
  level: SafetyLevel;     // nivo za `score`
  behaviors: Behavior[];  // ponašanja viđena u prozoru (boduju se samo dok se kola kreću)
  risk: number | null;    // prosečan rizik modela 0..1; null bez frejmova modela
  risk_max: number | null;
  alert: CameraAlert | null;            // najgori alarm modela u prozoru
  rules_triggered: string[];
  categories: Record<string, SampleCategory>; // ključevi su imena kategorija modela
  groups: Record<string, number | null>;      // najveći rizik po kanalu: visual, manual, fatigue
  dashboard_light: DashboardLight;      // najozbiljnije svetlo u prozoru
  vibrate_seat: boolean;                // sedište je bar jednom vibriralo
  sound: SoundLevel;                    // najglasniji zvuk u prozoru
  lat: number | null;                   // samo sa GPS-om telefona
  lon: number | null;
}

export interface TripTimeline {
  trip_id: string;
  window_s: number;
  samples: TripSample[]; // od najstarijeg
}

/** Rizičan momenat: kola se kreću, a vidi se bodovano ponašanje ili je model dao crveni alarm.
 *  Detekcije razmaknute manje od 2 s su isti momenat. */
export interface RiskEvent {
  event_id: string;
  trip_id: string;
  started_at: string;     // ISO 8601 UTC
  ended_at: string;
  t_start: number;        // sekundi od prvog ticka (isto kao TripSample.t)
  duration_s: number;     // rizične sekunde, računate kao BehaviorSummary.total_seconds
  behaviors: Behavior[];  // najduže prvo; prazno ako je opalio samo alarm modela
  behavior_seconds: Partial<Record<Behavior, number>>;
  categories: Record<string, number>; // kategorije modela aktivne u momentu → najveće p
  rules_triggered: string[];
  alert: CameraAlert | null;          // najgori alarm modela u momentu
  peak_risk: number | null;           // najveći rizik modela 0..1
  score_start: number;    // score neposredno pre momenta
  score_end: number;
  score_min: number;
  score_drop: number;     // score_start - score_min: koliko je ovaj momenat koštao
  level: SafetyLevel;     // najgori dostignut nivo
  speed_avg_kmh: number;
  speed_max_kmh: number;
  lat: number | null;
  lon: number | null;
  video_url: string | null;      // MP4 (H.264) oko momenta, apsolutni URL; null ako video nije strimovan
  thumbnail_url: string | null;  // JPEG najrizičnijeg frejma
  clip_duration_s: number | null;
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

// ---------- Izveštaj jedne vožnje ----------
/** Sve o jednoj vožnji u jednom odgovoru (GET /trips/{id}/report). */
export interface TripReport {
  trip: TripSummary;        // rezime: final/prosek/min score, trajanje, ponašanja sa savetima
  user: User | null;        // ko je vozio; null ako je vožnja pokrenuta bez prijave
  window_s: number;         // sekundi po uzorku (1)
  /** Sirovi zapis vožnje, jedan red po sekundi, od najstarijeg. Grafike pravi aplikacija. */
  samples: TripSample[];
  /** Rizični momenti sa slikom (`thumbnail_url`) i klipom (`video_url`), od najstarijeg. */
  events: RiskEvent[];
}

// ---------- WebSocket ----------
export type LiveMessage =
  | { type: "trip_started"; data: TripState }
  | { type: "state"; data: TripState }
  | { type: "emergency"; data: TripState }
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

Sve putanje su relativne u odnosu na `http://<IP>:8000/api/v1`.

### `GET /health`
Provera veze. Odgovor `200`: `{"status": "ok"}`

### `POST /trips`: početak vožnje
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

### `POST /trips/{trip_id}/end`: kraj vožnje
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
- Greške: `404` ako vožnja ne postoji (npr. backend je restartovan).

### `GET /trips/{trip_id}`: trenutno stanje
Odgovor `200`, `TripState`. Samo za vožnju koja upravo traje (iz memorije). Uglavnom nije potreban,
jer stanje stiže preko WebSocket-a. Greške: `404`.

### `GET /trips/{trip_id}/summary`: statistika
Odgovor `200`, `TripSummary`. Radi za aktivnu vožnju (`ended_at: null`) i, iz Postgresa, za svaku
raniju, **i posle restarta backenda**. Greške: `404`.

### `GET /trips`: istorija
Odgovor `200`, `TripSummary[]`, od najstarije ka najnovijoj, uključujući i aktivnu vožnju. Čita se
iz Postgresa, pa preživi restart.
- **Sa tokenom:** vožnje tog naloga (`driver_id` se ignoriše).
- **Bez tokena:** vožnje pokrenute bez prijave. `?driver_id=driver-1` sužava na jednog vozača.

**Ko šta vidi:** vožnju pokrenutu sa tokenom vide samo zahtevi sa tokenom istog naloga. Svi ostali
dobijaju `404`, kao da ne postoji (`/summary`, `/report`, `/timeline`, `/events`, `GET /trips/{id}`).
Vožnje bez prijave vidi svako, kao ranije. Živi kanal (WebSocket, `POST /trips/{id}/end`) ostaje
otvoren, jer je to mreža samih kola.

### `POST /auth/register`: novi nalog
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

### `POST /auth/login`: prijava
Telo `LoginIn` `{ "username": "ana", "password": "tajna-123" }`. Odgovor `200`, `AuthOut`.
Greška: `401` `{"detail": "Wrong username or password"}` (isto i za nepostojeće ime).
Token treba sačuvati (AsyncStorage) i slati u svakom zahtevu kao `Authorization: Bearer <token>`.
Na `401` za sačuvani token aplikacija treba da obriše token i ponovo traži prijavu.

### `GET /auth/me`, `PATCH /auth/me`, `POST /auth/logout`
- `GET /auth/me` → `User` (ko je prijavljen). Za ekran profila.
- `PATCH /auth/me` sa `UserUpdate` → `User`. Menja ime ili kontakt za hitne slučajeve.
- `POST /auth/logout` → `204`. Briše samo ovaj token (drugi uređaji ostaju prijavljeni).
- Svi traže token, inače `401`.

### `GET /analytics/overview`: za kompaniju
Odgovor `200`, `AnalyticsOverview`. Sadrži samo agregate, bez slika i bez podataka po vozaču.
Nije potreban u aplikaciji vozača.

### `GET /trips/{trip_id}/report`: sve o jednoj vožnji
Odgovor `200`, `TripReport`: `trip` (rezime kao `TripSummary`), `user` (ko je vozio), `samples`
(sirovi zapis vožnje po sekundi) i `events` (rizični momenti sa slikama i klipovima). **Jedan poziv
za ekran izveštaja.** Grafike računa aplikacija iz `samples`, kako god hoće. Npr. x osa `t`, a y
`score` (score kroz vožnju), `speed_kmh`, `risk_max` ili `categories["phone_use"].p_max`. Momente
može da označi na grafiku po `events[].t_start`. Čita se iz Postgresa, pa radi i posle restarta
backenda, a i za aktivnu vožnju (poslednja sekunda još nije upisana).
Greške: `404` ako vožnja ne postoji, nije snimljena ili pripada drugom nalogu. `503` ako je
snimanje isključeno ili Postgres nije dostupan.

### `GET /trips/{trip_id}/timeline`: samo uzorci
Odgovor `200`, `TripTimeline`: isti `samples` kao u izveštaju, bez ostatka. Greške kao za `report`.

### `GET /trips/{trip_id}/events?order=worst`: najgori momenti
Odgovor `200`, `RiskEvent[]`. `order=time` (podrazumevano) ide hronološki, a `order=worst` stavlja
najskuplje momente prvo (najveći `score_drop`, pa `peak_risk`, pa trajanje). Ako je strana sa
kamerom strimovala video, svaki momenat od bar 1 s (ili sa crvenim alarmom modela) ima `video_url`
(MP4, H.264, oko 3 s pre i 2 s posle momenta) i `thumbnail_url` (JPEG najrizičnijeg frejma).
Klip se pušta direktno sa URL-a (`expo-video` / `<video>`). Greške: kao za `timeline`.

Primer jednog momenta:
```json
{
  "event_id": "b6895bbcc632405a98c278170f4538f7",
  "trip_id": "13618edac23b492388e642d1060f3c43",
  "started_at": "2026-11-06T16:20:19.084192Z",
  "ended_at": "2026-11-06T16:20:21.667485Z",
  "t_start": 11.9,
  "duration_s": 3.1,
  "behaviors": ["eyes_off_road", "looking_at_phone"],
  "behavior_seconds": { "eyes_off_road": 3.1, "looking_at_phone": 3.1 },
  "categories": { "phone_use": 0.82, "eyes_off_road": 0.7 },
  "rules_triggered": ["phone_sustained"],
  "alert": "red",
  "peak_risk": 0.78,
  "score_start": 100.0, "score_end": 83.9, "score_min": 83.9, "score_drop": 16.1,
  "level": "caution",
  "speed_avg_kmh": 43.8, "speed_max_kmh": 49.8,
  "lat": null, "lon": null,
  "video_url": "http://192.168.43.57:8000/api/v1/media/clips/13618e.../b6895b....mp4",
  "thumbnail_url": "http://192.168.43.57:8000/api/v1/media/clips/13618e.../b6895b....jpg",
  "clip_duration_s": 7.6
}
```

### `GET /media/{key}`: klip ili thumbnail
Vraća fajl iz S3 (`video/mp4` ili `image/jpeg`) i podržava `Range`, pa plejer može da premotava.
URL-ove ne sklapaj sam, nego koristi `video_url` / `thumbnail_url` iz `RiskEvent`. Oni idu preko
backenda (port 8000), pa rade preko hotspota bez obzira na IP. Greške: `404`, `503`.

### `GET /speed`: odakle dolazi brzina
Odgovor `200`, `SpeedStatus`. Kamera ne zna brzinu. Backend je uzima ovim redom:
1. **GPS telefona** (`POST /speed`), samo ako je `phone_enabled` i očitavanje nije starije od 5 s;
2. `speed_kmh` iz samog ticka (simulator, testovi);
3. **mock vožnja** backenda: scenario (`city`, `highway`, `stop_and_go`, `country_road`, `cruise`,
   `parked`) izabran po vožnji, sa glatkim ubrzavanjem i kočenjem (Bezier), uključujući stajanje na 0 km/h.

### `POST /speed`: GPS brzina telefona (opciono, podrazumevano isključeno)
Telo `PhoneSpeedIn`: `{ "speed_kmh": 47.5, "lat": 44.8125, "lon": 20.4612 }`. Odgovor `200`, `SpeedStatus`.
Slati ~1/s tokom vožnje, i to **samo ako `GET /speed` vrati `phone_enabled: true`** (backend sa
`PHONE_SPEED_ENABLED=true`). Inače `409`. Sveže očitavanje telefona ima prednost nad mock brzinom,
a `lat`/`lon` se upisuju u izveštaj. Ovo je za kola bez sopstvene računarske snage, gde telefon zna brzinu.

### `POST /telemetry`: NIJE za aplikaciju
Ovo zovu modeli za kameru preko `notebooks/safety_client.py`. Aplikacija ga ne koristi.
Model šalje svoj zapis frejma neizmenjen (bez `perception`), a backend preslikava njegove aktivne
kategorije na `Behavior` (`phone_use` → `looking_at_phone`, `eyes_closed` i `drowsiness` → `drowsy`...,
tabela u `backend/README.md`) i prosleđuje `camera` aplikaciji. U `camera.categories` mogu da stignu i
kategorije koje se ne boduju (npr. `eating_drinking`), pa ih prikaži sirovim imenom.
`speed_kmh` je opciono i model ga ne šalje: brzinu daje backend (`GET /speed`). Simulator ga šalje
da bi vožnja kroz nivoe bila ista svaki put.

### `POST /video/frames`: NIJE za aplikaciju
Strana sa kamerom šalje JPEG frejmove (~8/s, telo je sirov JPEG, `Content-Type: image/jpeg`) preko
`SafetyClient.send_video_frame`. Backend u memoriji drži samo poslednjih nekoliko sekundi i iseče klip
samo oko rizičnih momenata (S3). Odgovor `204`. Greške: `409` bez aktivne vožnje, `415` ako nije
`image/jpeg`, `413` preko 2 MB, `422` ako telo nije JPEG.

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
| `state` | posle svakog ticka sa kamere (~2/s, simulator 1/s), i **odmah po povezivanju** ako vožnja traje | `TripState` |
| `trip_started` | počela je vožnja | `TripState` |
| `emergency` | score je pao ispod 10, jednom po vožnji, odmah posle `state` iz istog ticka | `TripState` |
| `trip_ended` | vožnja je završena | `TripSummary` |

- Ako nema aktivne vožnje, posle povezivanja ne stiže ništa dok ne stigne `trip_started`.
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
| `score` | veliki broj 0–100 (ili prsten / gauge) |
| `response.vibrate_seat` | simulira vibraciju sedišta. Za svaku `state` poruku gde je `true`, kratko zavibrira telefon (`Vibration` / `expo-haptics`). Poruke stižu ~2/s, pa to daje ritmičnu vibraciju koja prestaje čim polje postane `false` |
| `response.sound` | `low` je tihi signal, `high` glasan. Pušta se kratak zvuk po poruci, isto kao vibracija (`expo-audio` / `expo-av`) |
| `response.message` | tekst ispod lampice. Ako aplikacija nije na engleskom, napravi svoj tekst po `level` |
| `active_behaviors` | ikonice ili čipovi trenutnih ponašanja sa trajanjem u sekundama |
| `level` | naziv nivoa (tabela ispod) |
| `camera` | opciono, "šta kamera vidi": trake `p` po kategoriji, `risk` modela, `rules_triggered`. Može biti `null` i može imati nepoznate kategorije (prikaži sirovo ime). **Ne pokreći alarm na osnovu `camera.alert`**, to je već uračunato u `response` |
| `speed_kmh` | brzinomer. Ispod 5 km/h nema penala ni upozorenja (npr. semafor), pa je korisno da se vidi. `speed_source` može da ide sitno ispod (`mock` / `phone`) |

Nivoi (informativno, logika je na backendu):

| `level` | Score | Svetlo | Reakcija kola na rizično ponašanje (samo dok se kola kreću) |
|---|---|---|---|
| `safe` | 90–100 | zeleno | ništa |
| `caution` | 75–90 | zeleno-žuto | vibracija ako ponašanje traje ≥ 5 s |
| `warning` | 55–75 | žuto | vibracija + tihi zvuk, ≥ 5 s |
| `high_risk` | 35–55 | žuto | vibracija + glasan zvuk, ≥ 2 s |
| `critical` | 10–35 | crveno | vibracija + glasan zvuk odmah |
| `emergency` | < 10 | crveno | isto + događaj `emergency` |

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
`final_score` (finalni koeficijent), pored njega `average_score` i `min_score`, a zatim
`behaviors` kao listu sa `tip` savetima. Prazan `behaviors` znači da je vožnja bila bez grešaka.

**Izveštaj (predlog):** sa ekrana statistike dugme "Izveštaj", koje radi jedan `GET /trips/{id}/report`:
- zaglavlje iz `report.trip` (kao statistika) i `report.user.display_name`;
- grafik `score` kroz vreme (`samples[].t` / `.score`), ispod njega brzina (`speed_kmh`).
  Pozadinu možeš obojiti po `level`. Podaci su sirovi, pa je oblik grafika na aplikaciji;
- na grafiku oznake za `events[].t_start`;
- lista "Najgori momenti" (`events` sortiraj po `score_drop`, prva 3–5): thumbnail, ponašanja,
  trajanje, `-score_drop` poena, brzina u tom trenutku, a tap pušta `video_url`.

Momenti bez videa (`video_url: null`) se prikazuju bez slike. Ako `report` vrati `503`, snimanje ne
radi (Postgres ili S3 su dole), pa sakrij dugme umesto da prikažeš grešku.

## 8. Greške

| Status | Kada | Telo |
|---|---|---|
| `401` | pogrešan ili istekao token, pogrešna lozinka, `/auth/me` bez tokena | `{"detail": "Invalid or expired token - log in again"}` |
| `404` | nepoznat `trip_id`, ili vožnja drugog naloga | `{"detail": "Trip <id> not found"}` |
| `409` | `POST /auth/register` sa zauzetim imenom | `{"detail": "Username ana is taken"}` |
| `409` | `/telemetry` ili `/video/frames` bez aktivne vožnje | `{"detail": "No active trip - start one from the app first"}` |
| `409` | `POST /speed` dok je GPS telefona isključen na backendu | `{"detail": "Phone speed is disabled (PHONE_SPEED_ENABLED=false); ..."}` |
| `503` | `/timeline`, `/events`, `/media`: snimanje je isključeno ili Postgres / S3 nisu dostupni | `{"detail": "Postgres is unreachable; ..."}` |
| `422` | loše telo zahteva | `{"detail": [{"type": "missing", "loc": ["body", "driver_id"], "msg": "Field required", "input": {}}]}` |

Na `404` za sačuvani `trip_id` aplikacija treba da se vrati na ekran za početak vožnje.

## 9. Testiranje bez modela i bez auta

1. U `backend/`: `python run.py` (zapiši IP).
2. Poveži aplikaciju na taj IP.
3. U drugom terminalu: `python notebooks/safety_client.py` (sa `--interval 0.3` ide brže).
   Simulator sam pokrene vožnju, prođe kroz sve nivoe od zelenog do uzbune i završi vožnju.
   Aplikacija sve to dobija preko WebSocket-a. Simulator šalje samo labele, pa je `camera` tada `null`.
4. Sa pravim podacima modela: `python notebooks/safety_client.py --replay frames.jsonl`
   (`--speedup 2` ide duplo brže, `--speed-kmh 90` zakuca brzinu). Tada `camera` stiže popunjen.
5. Za izveštaj sa klipovima: u `backend/` prvo `.\scripts\services.ps1 start` (Postgres + RustFS),
   pa simulator sa videom: `--video 0` (web kamera) ili `--video snimak.mp4` (treba OpenCV).
   Na kraju simulator ispiše najgore momente sa `video_url`.
6. `--backend-speed`: simulator ne šalje brzinu, nego je određuje mock vožnja backenda.

Simulator pokreće svoju vožnju, pa završava vožnju koju je aplikacija eventualno pokrenula
(pravilo jedne aktivne vožnje).

## 10. Ograničenja

- Samo stanje aktivne vožnje (`GET /trips/{id}`, WebSocket) je u memoriji. Istorija, statistika i
  izveštaj su u Postgresu (klipovi u S3) i preživljavaju restart. Ako backend padne usred vožnje,
  ta vožnja ostaje sa rezimeom do poslednjeg upisa (najviše ~10 s ranije) i na sledećem startu se
  označi kao završena.
- Nalozi: nema reseta ni promene lozinke, potvrde emaila ni uloga. Token važi 30 dana.
- `started_at` / `ended_at` su u UTC (`Z`). Za prikaz ih pretvori u lokalno vreme.
- `duration_s` se računa iz vremena tickova sa kamere, a ne iz `started_at` / `ended_at`.
- Brzinu daje backend (mock vožnja). GPS telefona (`POST /speed`) postoji, ali je podrazumevano
  isključen (`PHONE_SPEED_ENABLED=false`).
- Klipovi su za demo u **javnom** lokalnom bucketu (RustFS). Pristup za produkciju (poseban server
  za izveštaje, potpisani URL-ovi) još nije dizajniran. Kompanija (`/analytics`) nikad ne dobija slike.
