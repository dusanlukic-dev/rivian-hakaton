"""Maps the safety coefficient to what the car does (light, seat vibration, sound)."""

from dataclasses import dataclass

from app.domain.enums import DashboardLight, SafetyLevel, SoundLevel
from app.domain.trip import CarResponse, Trip
from app.services.scoring import DEFAULT_CONFIG, ScoringConfig


@dataclass(frozen=True)
class LevelPolicy:
    light: DashboardLight
    # How long a behavior must last before the car reacts to it; None = never react.
    risk_threshold_s: float | None
    vibrate: bool
    sound: SoundLevel
    message: str


# (lower bound inclusive, level), checked top to bottom.
LEVEL_BANDS: tuple[tuple[float, SafetyLevel], ...] = (
    (90.0, SafetyLevel.SAFE),
    (75.0, SafetyLevel.CAUTION),
    (55.0, SafetyLevel.WARNING),
    (35.0, SafetyLevel.HIGH_RISK),
    (10.0, SafetyLevel.CRITICAL),
    (0.0, SafetyLevel.EMERGENCY),
)

POLICIES: dict[SafetyLevel, LevelPolicy] = {
    SafetyLevel.SAFE: LevelPolicy(
        DashboardLight.GREEN, None, False, SoundLevel.NONE,
        "All good - you're driving safely.",
    ),
    SafetyLevel.CAUTION: LevelPolicy(
        DashboardLight.GREEN_YELLOW, 5.0, True, SoundLevel.NONE,
        "Stay focused on the road.",
    ),
    SafetyLevel.WARNING: LevelPolicy(
        DashboardLight.YELLOW, 5.0, True, SoundLevel.LOW,
        "Risky behavior detected - eyes on the road.",
    ),
    SafetyLevel.HIGH_RISK: LevelPolicy(
        DashboardLight.YELLOW, 2.0, True, SoundLevel.HIGH,
        "You're getting distracted often - please focus.",
    ),
    SafetyLevel.CRITICAL: LevelPolicy(
        DashboardLight.RED, 0.0, True, SoundLevel.HIGH,
        "Dangerous driving - focus on the road now.",
    ),
    SafetyLevel.EMERGENCY: LevelPolicy(
        DashboardLight.RED, 0.0, True, SoundLevel.HIGH,
        "Critical risk - your emergency contact has been notified.",
    ),
}


def level_for(score: float) -> SafetyLevel:
    for lower, level in LEVEL_BANDS:
        if score >= lower:
            return level
    return SafetyLevel.EMERGENCY


def evaluate_response(
    trip: Trip, speed_kmh: float, cfg: ScoringConfig = DEFAULT_CONFIG
) -> CarResponse:
    policy = POLICIES[level_for(trip.score)]
    moving = speed_kmh >= cfg.stationary_speed_kmh
    flagged = (
        moving
        and policy.risk_threshold_s is not None
        and any(seconds >= policy.risk_threshold_s for seconds in trip.active.values())
    )
    return CarResponse(
        dashboard_light=policy.light,
        vibrate_seat=flagged and policy.vibrate,
        sound=policy.sound if flagged else SoundLevel.NONE,
        message=policy.message,
    )
