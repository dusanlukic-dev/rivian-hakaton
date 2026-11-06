// Verbatim copy of docs/API.md §4 (backend ↔ app contract, source of truth).
// When the backend changes, re-copy this block: don't edit fields by hand.

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
  driver_id: string;
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
