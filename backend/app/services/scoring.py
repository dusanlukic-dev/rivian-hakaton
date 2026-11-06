"""Safety coefficient engine (0-100).

The camera pipeline sends a telemetry tick roughly every second with the
current speed and the risky behaviors it sees. Each tick:

* every visible behavior costs ``weight * seconds`` points, plus a one-off
  ``onset`` penalty the first time it is penalized (the score drops fast at first);
* the penalty is scaled by speed (none when stationary, harshest on the
  highway), by time of day (night is harsher) and by how low the score already
  is (the lower it is, the easier it drops);
* after ``recovery_grace_s`` of clean driving the score slowly climbs back.

All the knobs live in ``ScoringConfig`` so the team can tune them in one place.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.domain.enums import Behavior
from app.domain.trip import MAX_SCORE, BehaviorStat, Trip


def _default_weights() -> dict[Behavior, float]:
    # Points lost per second at baseline (city speed, daytime, full score).
    return {
        Behavior.DROWSY: 2.5,  # heaviest: a microsleep means no reaction at all
        Behavior.LOOKING_AT_PHONE: 2.0,
        Behavior.LOOKING_BEHIND: 2.0,
        # Usually reported together with LOOKING_BEHIND, so the two add up.
        Behavior.TURNING_AROUND: 1.0,
        Behavior.HANDS_OFF_WHEEL: 1.0,
    }


@dataclass
class ScoringConfig:
    behavior_weights: dict[Behavior, float] = field(default_factory=_default_weights)
    onset_seconds: float = 2.0  # one-off penalty, expressed in seconds of the behavior
    fragility: float = 1.0  # multiplier = 1 + fragility * (100 - score) / 100
    stationary_speed_kmh: float = 5.0  # below this (parking, traffic light) there is no penalty
    # (upper speed bound in km/h, multiplier); the first band the speed falls under wins.
    speed_bands: tuple[tuple[float, float], ...] = (
        (50.0, 1.0),      # city
        (90.0, 1.3),      # open road
        (math.inf, 1.7),  # highway
    )
    night_start_hour: int = 22
    night_end_hour: int = 6
    night_multiplier: float = 1.5
    recovery_grace_s: float = 30.0
    recovery_per_s: float = 0.05  # 3 points per minute of clean driving
    max_tick_gap_s: float = 5.0  # caps dt so a dropped connection can't swing the score


DEFAULT_CONFIG = ScoringConfig()


def speed_multiplier(speed_kmh: float, cfg: ScoringConfig = DEFAULT_CONFIG) -> float:
    if speed_kmh < cfg.stationary_speed_kmh:
        return 0.0
    for upper, multiplier in cfg.speed_bands:
        if speed_kmh < upper:
            return multiplier
    return cfg.speed_bands[-1][1]


def is_night(ts: datetime, cfg: ScoringConfig = DEFAULT_CONFIG) -> bool:
    """Uses the timestamp's own hour, so clients should send local time with an offset."""
    start, end = cfg.night_start_hour, cfg.night_end_hour
    if start > end:
        return ts.hour >= start or ts.hour < end
    return start <= ts.hour < end


def fragility_multiplier(score: float, cfg: ScoringConfig = DEFAULT_CONFIG) -> float:
    return 1.0 + cfg.fragility * (MAX_SCORE - score) / MAX_SCORE


def _as_utc(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc).replace(tzinfo=None) if ts.tzinfo else ts


def apply_tick(
    trip: Trip,
    timestamp: datetime,
    speed_kmh: float,
    behaviors: set[Behavior],
    cfg: ScoringConfig = DEFAULT_CONFIG,
) -> None:
    """Advance the trip state by one telemetry tick."""
    dt = 0.0
    if trip.last_tick_at is not None:
        dt = (_as_utc(timestamp) - _as_utc(trip.last_tick_at)).total_seconds()
        dt = min(max(dt, 0.0), cfg.max_tick_gap_s)
    if trip.last_tick_at is None or _as_utc(timestamp) > _as_utc(trip.last_tick_at):
        trip.last_tick_at = timestamp

    # Behaviors that disappeared end their streak.
    for behavior in list(trip.active):
        if behavior not in behaviors:
            del trip.active[behavior]
            trip.counted.discard(behavior)
    # A behavior seen in this tick is assumed present for the interval leading up to it.
    for behavior in behaviors:
        trip.active[behavior] = trip.active.get(behavior, 0.0) + dt

    multiplier = speed_multiplier(speed_kmh, cfg)
    if multiplier and is_night(timestamp, cfg):
        multiplier *= cfg.night_multiplier

    if behaviors and multiplier:
        penalty = 0.0
        for behavior in behaviors:
            seconds = dt
            stat = trip.stats.setdefault(behavior, BehaviorStat())
            if behavior not in trip.counted:
                trip.counted.add(behavior)
                stat.occurrences += 1
                seconds += cfg.onset_seconds
            stat.total_seconds += dt
            penalty += cfg.behavior_weights.get(behavior, 1.0) * seconds
        trip.score -= penalty * multiplier * fragility_multiplier(trip.score, cfg)
        trip.clean_streak_s = 0.0
    elif not behaviors:
        trip.clean_streak_s += dt
        recoverable = min(dt, trip.clean_streak_s - cfg.recovery_grace_s)
        if recoverable > 0:
            trip.score += cfg.recovery_per_s * recoverable
    # Behaviors while stationary: no penalty, but no recovery either.

    trip.score = min(max(trip.score, 0.0), MAX_SCORE)
    trip.min_score = min(trip.min_score, trip.score)
    trip.elapsed_s += dt
    trip.score_seconds += trip.score * dt
