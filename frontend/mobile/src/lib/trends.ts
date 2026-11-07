import type { Behavior, TripSummary } from '@/api/types';

/**
 * Trends over the driver's recent trips (Drive screen card), computed from GET /trips. Only numbers the backend already
 * gave per trip are combined here; levels stay the backend's (each trip's `level`), nothing here decides a warning.
 */

/** Trips shorter than this are test starts (start, then end right away): they would only add noise. */
export const MIN_TRIP_S = 20;
/** A trend needs two halves of at least two trips each. */
export const MIN_TREND_TRIPS = 4;
/** Average score change (points) that still counts as "steady". */
const STEADY_POINTS = 2;
/** A behaviour's rate per driving minute has to change by this factor to count as more / fewer. */
const RATE_CHANGE = 1.25;
const TOP_BEHAVIORS = 3;
const DAY_MS = 24 * 60 * 60 * 1000;

export type TrendWindow = 'last5' | 'last10' | 'month';
export const TREND_WINDOWS: TrendWindow[] = ['last5', 'last10', 'month'];

export type Direction = 'better' | 'worse' | 'steady';
export type BehaviorDirection = 'fewer' | 'more' | 'same' | 'new';

export interface BehaviorTrend {
  behavior: Behavior;
  occurrences: number;
  seconds: number;
  trips: number;
  /** null while there are too few trips for a trend. */
  direction: BehaviorDirection | null;
}

export interface Trends {
  /** The trips in the window, oldest first. */
  trips: TripSummary[];
  /** Finished trips left out as test starts (whole history, not only this window). */
  shortLeftOut: number;
  /** Average score while driving over the window, weighted by trip length. */
  average: number;
  /** Recent half minus earlier half (points); null below MIN_TREND_TRIPS. */
  delta: number | null;
  direction: Direction | null;
  drivingS: number;
  cleanTrips: number;
  riskyMoments: number;
  emergencies: number;
  behaviors: BehaviorTrend[];
  /** Advice for the biggest risk, from the latest trip where it happened. */
  tip: string | null;
}

/** Finished trips long enough to count, oldest first. */
function finished(all: TripSummary[]): { trips: TripSummary[]; shortLeftOut: number } {
  const done = all.filter((t) => t.status !== 'active' && t.ended_at !== null);
  const trips = done
    .filter((t) => t.duration_s >= MIN_TRIP_S)
    .sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at));
  return { trips, shortLeftOut: done.length - trips.length };
}

function inWindow(trips: TripSummary[], window: TrendWindow, now: number): TripSummary[] {
  if (window === 'last5') return trips.slice(-5);
  if (window === 'last10') return trips.slice(-10);
  return trips.filter((t) => now - Date.parse(t.started_at) <= 30 * DAY_MS);
}

function weightedAverage(trips: TripSummary[]): number {
  const total = trips.reduce((sum, t) => sum + Math.max(t.duration_s, 1), 0);
  return trips.reduce((sum, t) => sum + t.average_score * Math.max(t.duration_s, 1), 0) / total;
}

/** The older and the newer half; the middle trip of an odd count belongs to neither. */
function halves(trips: TripSummary[]): [TripSummary[], TripSummary[]] {
  const h = Math.floor(trips.length / 2);
  return [trips.slice(0, h), trips.slice(trips.length - h)];
}

/** Occurrences of one behaviour per driving minute. */
function rate(trips: TripSummary[], behavior: Behavior): number {
  const minutes = trips.reduce((sum, t) => sum + t.duration_s, 0) / 60;
  const count = trips.reduce((sum, t) => sum + (t.behaviors.find((b) => b.behavior === behavior)?.occurrences ?? 0), 0);
  return minutes > 0 ? count / minutes : 0;
}

function behaviorDirection(earlier: number, later: number): BehaviorDirection {
  if (earlier === 0) return later > 0 ? 'new' : 'same';
  if (later * RATE_CHANGE < earlier) return 'fewer';
  if (later > earlier * RATE_CHANGE) return 'more';
  return 'same';
}

/** null when no trip in the window counts (nothing to show yet). */
export function computeTrends(all: TripSummary[], window: TrendWindow, now = Date.now()): Trends | null {
  const { trips: eligible, shortLeftOut } = finished(all);
  const trips = inWindow(eligible, window, now);
  if (trips.length === 0) return null;

  const trend = trips.length >= MIN_TREND_TRIPS;
  const [earlier, later] = halves(trips);
  const delta = trend ? weightedAverage(later) - weightedAverage(earlier) : null;
  const direction: Direction | null =
    delta === null ? null : delta >= STEADY_POINTS ? 'better' : delta <= -STEADY_POINTS ? 'worse' : 'steady';

  const byBehavior = new Map<Behavior, BehaviorTrend>();
  for (const trip of trips) {
    for (const b of trip.behaviors) {
      const entry = byBehavior.get(b.behavior) ?? {
        behavior: b.behavior,
        occurrences: 0,
        seconds: 0,
        trips: 0,
        direction: null,
      };
      entry.occurrences += b.occurrences;
      entry.seconds += b.total_seconds;
      entry.trips += 1;
      byBehavior.set(b.behavior, entry);
    }
  }
  const behaviors = [...byBehavior.values()]
    .sort((a, b) => b.occurrences - a.occurrences || b.seconds - a.seconds)
    .slice(0, TOP_BEHAVIORS)
    .map((b) => ({
      ...b,
      direction: trend ? behaviorDirection(rate(earlier, b.behavior), rate(later, b.behavior)) : null,
    }));

  const top = behaviors[0]?.behavior;
  const tip = top
    ? ([...trips].reverse().flatMap((t) => t.behaviors).find((b) => b.behavior === top)?.tip ?? null)
    : null;

  return {
    trips,
    shortLeftOut,
    average: weightedAverage(trips),
    delta,
    direction,
    drivingS: trips.reduce((sum, t) => sum + t.duration_s, 0),
    cleanTrips: trips.filter((t) => t.behaviors.length === 0).length,
    riskyMoments: trips.reduce((sum, t) => sum + t.behaviors.reduce((s, b) => s + b.occurrences, 0), 0),
    emergencies: trips.filter((t) => t.emergency_alert_sent).length,
    behaviors,
    tip,
  };
}
