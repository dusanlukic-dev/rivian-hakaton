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
