"""Maps the live score to what the car does (light, seat vibration, sound).

The score already says how dangerous the situation is now (services/scoring.py), so the level decides the reaction:
- standing still (< 5 km/h): never any warning, whatever the driver does;
- the light follows the level;
- vibration and sound come only while something risky is actually happening (a behavior, or the camera model's
  yellow/red alert), so they stop the moment the driver puts the phone away, while the light eases back with the score;
- the camera model's red alert vibrates and sounds loudly at any level.
"""

from dataclasses import dataclass

from app.coordinator.services.scoring import DEFAULT_CONFIG, ScoringConfig
from app.domain.enums import DashboardLight, SafetyLevel, SoundLevel
from app.domain.levels import LEVEL_BANDS, level_for
from app.domain.trip import CarResponse, Trip

__all__ = [
    "CAMERA_ALARM_MESSAGE", "LEVEL_BANDS", "POLICIES", "STANDING_MESSAGE", "LevelPolicy", "evaluate_response",
    "level_for",
]


@dataclass(frozen=True)
class LevelPolicy:
    light: DashboardLight
    vibrate: bool
    sound: SoundLevel
    message: str


POLICIES: dict[SafetyLevel, LevelPolicy] = {
    SafetyLevel.SAFE: LevelPolicy(DashboardLight.GREEN, False, SoundLevel.NONE, "All good - you're driving safely."),
    SafetyLevel.CAUTION: LevelPolicy(DashboardLight.GREEN_YELLOW, False, SoundLevel.NONE, "Stay focused on the road."),
    SafetyLevel.WARNING: LevelPolicy(
        DashboardLight.YELLOW, True, SoundLevel.LOW, "Risky behavior detected - eyes on the road."
    ),
    SafetyLevel.HIGH_RISK: LevelPolicy(DashboardLight.YELLOW, True, SoundLevel.HIGH, "High risk - focus on the road now."),
    SafetyLevel.CRITICAL: LevelPolicy(DashboardLight.RED, True, SoundLevel.HIGH, "Dangerous driving - focus on the road now."),
    SafetyLevel.EMERGENCY: LevelPolicy(
        DashboardLight.RED, True, SoundLevel.HIGH, "Critical danger - eyes on the road and slow down."
    ),
}

CAMERA_ALARM_MESSAGE = "Danger detected - eyes on the road now."
STANDING_MESSAGE = "Standing still - no warnings."


def evaluate_response(trip: Trip, speed_kmh: float, cfg: ScoringConfig = DEFAULT_CONFIG) -> CarResponse:
    if speed_kmh < cfg.stationary_speed_kmh:
        return CarResponse(DashboardLight.GREEN, False, SoundLevel.NONE, STANDING_MESSAGE)
    level = level_for(trip.score)
    policy = POLICIES[level]
    camera = trip.camera
    # The camera model's red alert (microsleep, long look away...) raises the alarm on its own.
    if camera is not None and camera.alarm:
        return CarResponse(
            dashboard_light=policy.light,
            vibrate_seat=True,
            sound=SoundLevel.HIGH,
            message=CAMERA_ALARM_MESSAGE if level is SafetyLevel.SAFE else policy.message,
        )
    happening = bool(trip.active) or (camera is not None and camera.alert in ("yellow", "red"))
    return CarResponse(
        dashboard_light=policy.light,
        vibrate_seat=policy.vibrate and happening,
        sound=policy.sound if happening else SoundLevel.NONE,
        message=policy.message,
    )
