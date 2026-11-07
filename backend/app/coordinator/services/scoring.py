"""Attention score 0-100: how safe the driving is RIGHT NOW (100 = nothing risky, 0 = acute danger).

It is a live reading of the current situation, not a points balance: it falls while something risky is happening
and climbs back once it stops. Every tick:

    episodes    what the camera reports flickers (the model loses the phone for a frame or two), people don't: a
                behavior counts once it has been seen for its onset (a glance at the mirror is not "eyes off the
                road"), and once it counts, gaps shorter than its bridge don't end it (`Debounce`). So one phone
                call is one smooth dip and one occurrence, not a saw-tooth.
    danger      D = worst behavior + 30 % of what the others add on top (they mostly come together: the model
                    reports eyes-off-road with every phone look). Severity grows the longer a behavior lasts.
                D = max(D, model risk)             the RiskEngine's risk, minus its calm baseline (0.1), at 80 %
    exposure    E = D × speed factor × night       the speed amplifies the danger: 0 below 5 km/h (standing still:
                                                   anything goes), ×0.4 at walking pace, ×1 at 50 km/h, ×1.6 at 130 km/h
    target      max(100 × (1 - min(E, 1)), 10)     never below 10 without a collapse: the emergency band is the collapse's
    score       follows the target: falls fast (τ 0.5 s) and rises a little slower (τ 2.5 s)

Calibration (daytime): a long phone look is "critical" in town and at speed; a microsleep at speed is critical;
hands off the wheel alone stays at caution/warning in town. None of them is an emergency.

Collapse (the driver slumped over and doesn't move, `rivian_model/`) is not a degree of danger but a medical
emergency, and the only one: once it has been seen for ``collapse_confirm_s`` the score is 0 at once, at any
speed (standing still too), and the emergency contact is alerted (services/trips.py). It holds for
``collapse_hold_s`` after it was last seen, so a flickering signal doesn't bounce the score.

All the knobs live in ``ScoringConfig`` so the team can tune them in one place.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.domain.enums import Behavior
from app.domain.trip import MAX_SCORE, BehaviorStat, Episode, Trip


@dataclass(frozen=True)
class Severity:
    """How dangerous a behavior is at the reference speed (50 km/h, daytime), 0..1."""

    onset: float  # the moment it starts
    per_s: float  # added for every second it lasts
    max: float  # ceiling

    def at(self, seconds: float) -> float:
        return min(self.max, self.onset + self.per_s * max(seconds, 0.0))


def _default_severity() -> dict[Behavior, Severity]:
    return {
        Behavior.DROWSY: Severity(0.60, 0.15, 1.00),  # a microsleep means no reaction at all
        Behavior.LOOKING_AT_PHONE: Severity(0.30, 0.12, 0.80),
        Behavior.LOOKING_BEHIND: Severity(0.30, 0.10, 0.75),
        Behavior.TURNING_AROUND: Severity(0.25, 0.10, 0.70),  # usually together with LOOKING_BEHIND
        Behavior.EYES_OFF_ROAD: Severity(0.20, 0.08, 0.50),  # usually together with LOOKING_AT_PHONE
        Behavior.HANDS_OFF_WHEEL: Severity(0.15, 0.05, 0.45),
        # No weight before it is confirmed (collapse_confirm_s): a short slump (getting out, picking something up)
        # must not cost points. Once confirmed, apply_tick sets the score to 0 directly.
        Behavior.COLLAPSE: Severity(0.0, 0.0, 0.0),
    }


@dataclass(frozen=True)
class Debounce:
    """When a reported behavior counts, and how long a gap it survives once it does."""

    onset_s: float  # seen this long within one episode before it counts
    bridge_s: float  # once it counts, a gap shorter than this doesn't end it


def _default_debounce() -> dict[Behavior, Debounce]:
    return {
        # A phone call doesn't stop because the model lost the phone for two seconds.
        Behavior.LOOKING_AT_PHONE: Debounce(1.0, 2.5),
        # Glances under 2 s (mirrors, instruments) are normal driving: the usual eyes-off-road threshold.
        Behavior.EYES_OFF_ROAD: Debounce(2.0, 1.5),
        Behavior.DROWSY: Debounce(1.0, 1.5),  # longer than a blink
        Behavior.HANDS_OFF_WHEEL: Debounce(2.0, 2.0),
        Behavior.LOOKING_BEHIND: Debounce(1.0, 2.0),
        Behavior.TURNING_AROUND: Debounce(1.0, 2.0),
        # COLLAPSE uses collapse_confirm_s / collapse_hold_s (ScoringConfig.debounce_for).
    }


@dataclass
class ScoringConfig:
    severity: dict[Behavior, Severity] = field(default_factory=_default_severity)
    debounce: dict[Behavior, Debounce] = field(default_factory=_default_debounce)
    # Before a behavior counts, a gap longer than this starts it over: separate glances don't add up.
    flicker_s: float = 0.6
    stationary_speed_kmh: float = 5.0  # below this (parking, traffic light): no danger, no warnings, no statistics
    # (km/h, factor) points of the speed amplification; linear in between, flat past the last point.
    speed_curve: tuple[tuple[float, float], ...] = ((5.0, 0.4), (50.0, 1.0), (130.0, 1.6))
    # Behaviors seen together: the worst counts fully, the rest add this share of what they'd add independently.
    combined_extra: float = 0.3
    # The model's risk: its calm baseline is ignored and the rest counts at this weight (0.96 risk -> 0.77 danger).
    model_risk_floor: float = 0.1
    model_risk_weight: float = 0.8
    night_start_hour: int = 22
    night_end_hour: int = 6
    night_multiplier: float = 1.25
    fall_tau_s: float = 0.5  # how fast the score drops toward a lower target
    rise_tau_s: float = 2.5  # how fast it comes back once things calm down (~95 % in 7.5 s)
    standing_rise_tau_s: float = 0.5  # standing still is safe at once: back to 100 in ~2 s
    # Without a collapse the score stays at or above this ("critical"): the emergency level, and the message to the
    # emergency contact, belong to a driver who no longer responds.
    score_floor: float = 10.0
    # A collapse seen this long is confirmed: score 0 and the emergency, at any speed. Short dips (bending down
    # to pick something up) stay below it; the model already requires the body to be still.
    collapse_confirm_s: float = 2.0
    # Once confirmed, the collapse holds this long after it was last seen: the model's signal flickers while the
    # driver lies on the wheel, and the score must not bounce 0 -> 20 -> 0 in a medical emergency.
    collapse_hold_s: float = 10.0
    max_tick_gap_s: float = 5.0  # caps dt so a dropped connection can't swing the score

    def debounce_for(self, behavior: Behavior) -> Debounce:
        if behavior is Behavior.COLLAPSE:
            return Debounce(self.collapse_confirm_s, self.collapse_hold_s)
        return self.debounce.get(behavior, Debounce(0.0, 0.0))


DEFAULT_CONFIG = ScoringConfig()


def speed_factor(speed_kmh: float, cfg: ScoringConfig = DEFAULT_CONFIG) -> float:
    """How much the speed amplifies the danger: 0 while standing, then rising with speed."""
    if speed_kmh < cfg.stationary_speed_kmh:
        return 0.0
    curve = cfg.speed_curve
    if speed_kmh <= curve[0][0]:
        return curve[0][1]
    for (v0, f0), (v1, f1) in zip(curve, curve[1:]):
        if speed_kmh <= v1:
            return f0 + (f1 - f0) * (speed_kmh - v0) / (v1 - v0)
    return curve[-1][1]


def is_night(ts: datetime, cfg: ScoringConfig = DEFAULT_CONFIG) -> bool:
    """Uses the timestamp's own hour, so clients should send local time with an offset."""
    start, end = cfg.night_start_hour, cfg.night_end_hour
    if start > end:
        return ts.hour >= start or ts.hour < end
    return start <= ts.hour < end


def behavior_danger(active: dict[Behavior, float], cfg: ScoringConfig = DEFAULT_CONFIG) -> float:
    """Combined danger of the behaviors seen now (each with the seconds it has lasted), 0..1."""
    levels = [cfg.severity[b].at(seconds) for b, seconds in active.items() if b in cfg.severity]
    if not levels:
        return 0.0
    worst = max(levels)
    independent = 1.0 - math.prod(1.0 - level for level in levels)
    return worst + cfg.combined_extra * (independent - worst)


def model_danger(model_risk: float, cfg: ScoringConfig = DEFAULT_CONFIG) -> float:
    """The CV risk engine's risk (0..1) as danger: ~0.02 for a calm driver -> 0, 0.96 (red alert) -> 0.77."""
    above = (min(max(model_risk, 0.0), 1.0) - cfg.model_risk_floor) / (1.0 - cfg.model_risk_floor)
    return cfg.model_risk_weight * max(above, 0.0)


def exposure(
    active: dict[Behavior, float],
    speed_kmh: float,
    timestamp: datetime,
    model_risk: float | None = None,
    cfg: ScoringConfig = DEFAULT_CONFIG,
) -> float:
    """Danger now, amplified by speed (and night). 0 = safe, >= 1 = as bad as it gets."""
    factor = speed_factor(speed_kmh, cfg)
    if not factor:
        return 0.0
    danger = behavior_danger(active, cfg)
    if model_risk is not None:
        danger = max(danger, model_danger(model_risk, cfg))
    if is_night(timestamp, cfg):
        factor *= cfg.night_multiplier
    return danger * factor


def collapse_confirmed(trip: Trip, cfg: ScoringConfig = DEFAULT_CONFIG) -> bool:
    """The driver has been slumped over and still for ``collapse_confirm_s``, now or within ``collapse_hold_s``."""
    return Behavior.COLLAPSE in trip.active


def target_score(exposure_now: float, cfg: ScoringConfig = DEFAULT_CONFIG) -> float:
    return max(MAX_SCORE * (1.0 - min(max(exposure_now, 0.0), 1.0)), cfg.score_floor)


def update_episodes(trip: Trip, seen: set[Behavior], dt: float, cfg: ScoringConfig = DEFAULT_CONFIG) -> None:
    """Advance every behavior's episode by one tick and refresh ``trip.active`` (the confirmed ones).

    A behavior seen now is assumed present since the last tick. Before it counts, gaps longer than ``flicker_s``
    start it over; once it counts (``onset_s`` seen), it survives gaps up to ``bridge_s`` and its age keeps
    running through them, so severity, the car's reaction and the app's tile don't stutter.
    """
    for behavior in set(trip.episodes) | seen:
        episode = trip.episodes.setdefault(behavior, Episode())
        debounce = cfg.debounce_for(behavior)
        episode.age_s += dt
        if behavior in seen:
            episode.seen_s += dt
            episode.gap_s = 0.0
            if not episode.confirmed and episode.seen_s >= debounce.onset_s:
                episode.confirmed = True
        else:
            episode.gap_s += dt
            if episode.gap_s > (debounce.bridge_s if episode.confirmed else cfg.flicker_s):
                del trip.episodes[behavior]
    trip.active = {b: e.age_s for b, e in trip.episodes.items() if e.confirmed}


def _count_statistics(trip: Trip, moving: bool) -> None:
    """One occurrence per confirmed episode and its time up to the moment it was last seen, both only while moving
    (a bridged gap is added once the behavior shows up again; the gap at the end of an episode never is)."""
    for behavior, episode in trip.episodes.items():
        if not episode.confirmed or episode.gap_s > 0:
            continue
        if moving:
            stat = trip.stats.setdefault(behavior, BehaviorStat())
            if not episode.counted:
                episode.counted = True
                stat.occurrences += 1
            stat.total_seconds += episode.age_s - episode.stats_s
        episode.stats_s = episode.age_s


def _as_utc(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc).replace(tzinfo=None) if ts.tzinfo else ts


def apply_tick(
    trip: Trip,
    timestamp: datetime,
    speed_kmh: float,
    behaviors: set[Behavior],
    model_risk: float | None = None,
    cfg: ScoringConfig = DEFAULT_CONFIG,
) -> None:
    """Advance the trip by one tick: behavior episodes, the live score, statistics (only while moving)."""
    first = trip.last_tick_at is None
    dt = 0.0
    if not first:
        dt = (_as_utc(timestamp) - _as_utc(trip.last_tick_at)).total_seconds()
        dt = min(max(dt, 0.0), cfg.max_tick_gap_s)
    if first or _as_utc(timestamp) > _as_utc(trip.last_tick_at):
        trip.last_tick_at = timestamp

    update_episodes(trip, behaviors, dt, cfg)

    moving = speed_kmh >= cfg.stationary_speed_kmh
    trip.exposure = exposure(trip.active, speed_kmh, timestamp, model_risk, cfg)
    target = target_score(trip.exposure, cfg)
    if first:
        trip.score = target  # nothing to smooth from
    elif dt > 0:
        if target < trip.score:
            tau = cfg.fall_tau_s
        else:
            tau = cfg.rise_tau_s if moving else cfg.standing_rise_tau_s
        trip.score += (target - trip.score) * (1.0 - math.exp(-dt / tau))
    trip.score = min(max(trip.score, 0.0), MAX_SCORE)
    trip.elapsed_s += dt
    if collapse_confirmed(trip, cfg):
        trip.score = 0.0  # a medical emergency, not a degree of danger: no smoothing, no speed factor
    trip.min_score = min(trip.min_score, trip.score)

    _count_statistics(trip, moving)
    if moving:
        trip.moving_s += dt
        trip.score_seconds += trip.score * dt
