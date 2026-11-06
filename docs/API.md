# API ugovor: backend ↔ mobilna aplikacija

Ovo je **izvor istine** za komunikaciju React Native aplikacije sa backendom. Kad se backend
promeni, menja se i ovaj fajl.

> **Za Claude koji pravi frontend:** koristi tačno ove rute, polja i tipove (sekcija 4 se može
> kopirati u `src/api/types.ts`). Ne izmišljaj endpointe ni polja. Ako nešto fali, to je izmena
> backenda, pa to reci developeru umesto da pretpostavljaš. Aplikacija **ne šalje telemetriju**,
> to rade modeli za kameru.

## 1. Šta aplikacija radi

1. Povezuje se na backend (laptop) preko hotspota telefona.
2. Vozač pokreće vožnju (unosi svoj ID i kontakt za hitne slučajeve).
3. Tokom vožnje uživo prikazuje dashboard: svetlo, score, trenutna rizična ponašanja, poruku.
   Simulira vibraciju sedišta i zvučni signal.
4. Kad score padne ispod 10, prikazuje uzbunu za hitan slučaj.
5. Vozač završava vožnju i vidi statistiku sa savetima.
6. Istorija vožnji.

## 2. Povezivanje

| | |
|---|---|
| REST base URL | `http://<IP>:8000/api/v1` |
| WebSocket | `ws://<IP>:8000/api/v1/ws` |
| Autentifikacija | nema |
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
   → Početak vožnje (forma) ── POST /trips ──► Dashboard (WebSocket, uživo)
                                                  │ dugme "Završi" ── POST /trips/{id}/end
                                                  ▼
                                               Statistika (TripSummary)
Istorija ── GET /trips?driver_id=... ──► Statistika pojedinačne vožnje
```

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

// ---------- Zahtevi ----------
export interface EmergencyContact {
  name: string;
  phone: string;
}

export interface TripCreate {
  driver_id: string;
  emergency_contact?: EmergencyContact | null;
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
  "emergency_alert_sent": false
}
```
- U jednom trenutku postoji samo **jedna aktivna vožnja** (jedan auto). Ako je neka i dalje aktivna,
  backend je prvo završi. Preko WebSocket-a tada stižu `trip_ended` (stara), pa `trip_started` (nova).
- `trip_id` treba sačuvati, jer je potreban za završetak vožnje.
- Greške: `422` ako fali `driver_id`.

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
Odgovor `200`, `TripState`. Uglavnom nije potreban, jer stanje stiže preko WebSocket-a.
Greške: `404`.

### `GET /trips/{trip_id}/summary`: statistika
Odgovor `200`, `TripSummary`. Radi i za aktivnu vožnju (`ended_at: null`). Greške: `404`.

### `GET /trips?driver_id=driver-1`: istorija
Odgovor `200`, `TripSummary[]`, od najstarije ka najnovijoj, uključujući i aktivnu vožnju.
Bez `driver_id` vraća sve vožnje.

### `GET /analytics/overview`: za kompaniju
Odgovor `200`, `AnalyticsOverview`. Sadrži samo agregate, bez slika i bez podataka po vozaču.
Nije potreban u aplikaciji vozača.

### `POST /telemetry`: NIJE za aplikaciju
Ovo zovu modeli za kameru preko `notebooks/safety_client.py`. Aplikacija ga ne koristi.
Model šalje svoj zapis frejma neizmenjen (bez `perception`), a backend preslikava njegove aktivne
kategorije na `Behavior` (`phone_use` → `looking_at_phone`...) i prosleđuje `camera` aplikaciji.

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

## 8. Greške

| Status | Kada | Telo |
|---|---|---|
| `404` | nepoznat `trip_id` (npr. backend je restartovan, jer se vožnje čuvaju u memoriji) | `{"detail": "Trip <id> not found"}` |
| `409` | samo `/telemetry`, nema aktivne vožnje | `{"detail": "No active trip - start one from the app first"}` |
| `422` | loše telo zahteva | `{"detail": [{"type": "missing", "loc": ["body", "driver_id"], "msg": "Field required", "input": {}}]}` |

Na `404` za sačuvani `trip_id` aplikacija treba da se vrati na ekran za početak vožnje.

## 9. Testiranje bez modela i bez auta

1. U `backend/`: `python run.py` (zapiši IP).
2. Poveži aplikaciju na taj IP.
3. U drugom terminalu: `python notebooks/safety_client.py` (sa `--interval 0.3` ide brže).
   Simulator sam pokrene vožnju, prođe kroz sve nivoe od zelenog do uzbune i završi vožnju.
   Aplikacija sve to dobija preko WebSocket-a. Simulator šalje samo labele, pa je `camera` tada `null`.
4. Sa pravim podacima modela: `python notebooks/safety_client.py --replay frames.jsonl`
   (`--speedup 2` ide duplo brže, `--speed-kmh 90` menja brzinu). Tada `camera` stiže popunjen.

Simulator pokreće svoju vožnju, pa završava vožnju koju je aplikacija eventualno pokrenula
(pravilo jedne aktivne vožnje).

## 10. Ograničenja

- Vožnje se čuvaju u memoriji, pa ih restart backenda briše.
- `started_at` / `ended_at` su u UTC (`Z`). Za prikaz ih pretvori u lokalno vreme.
- `duration_s` se računa iz vremena tickova sa kamere, a ne iz `started_at` / `ended_at`.
- Brzinu za sada šalje strana sa modelima. Da li će aplikacija slati GPS brzinu još nije dogovoreno.
  Ako se uvede, biće dodato ovde.
