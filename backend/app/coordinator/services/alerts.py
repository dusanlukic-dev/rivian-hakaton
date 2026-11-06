"""Maps the safety coefficient to what the car does (light, seat vibration, sound)."""

from dataclasses import dataclass

from app.coordinator.services.scoring import DEFAULT_CONFIG, ScoringConfig
from app.domain.enums import DashboardLight, SafetyLevel, SoundLevel
from app.domain.levels import LEVEL_BANDS, level_for
from app.domain.trip import CarResponse, Trip

__all__ = ["CAMERA_ALARM_MESSAGE", "LEVEL_BANDS", "POLICIES", "LevelPolicy", "evaluate_response", "level_for"]


@dataclass(frozen=True)
class LevelPolicy:
    light: DashboardLight
    # How long a behavior must last before the car reacts to it; None = never react.
    risk_threshold_s: float | None
    vibrate: bool
    sound: SoundLevel
    message: str



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


CAMERA_ALARM_MESSAGE = "Danger detected - eyes on the road now."



def evaluate_response(
    trip: Trip, speed_kmh: float, cfg: ScoringConfig = DEFAULT_CONFIG
) -> CarResponse:
    level = level_for(trip.score)
    policy = POLICIES[level]
    moving = speed_kmh >= cfg.stationary_speed_kmh
    flagged = (
        moving
        and policy.risk_threshold_s is not None
        and any(seconds >= policy.risk_threshold_s for seconds in trip.active.values())
    )
    # The camera model's red alert (microsleep, long look away...) raises the alarm on its own, so
    # the first dangerous moment isn't silent just because the trip score is still high.
    camera_alarm = moving and trip.camera is not None and trip.camera.alarm
    if camera_alarm:
        return CarResponse(
            dashboard_light=policy.light,
            vibrate_seat=True,
            sound=SoundLevel.HIGH,
            message=CAMERA_ALARM_MESSAGE if level is SafetyLevel.SAFE else policy.message,
        )
    return CarResponse(
        dashboard_light=policy.light,
        vibrate_seat=flagged and policy.vibrate,
        sound=policy.sound if flagged else SoundLevel.NONE,
        message=policy.message,
    )
