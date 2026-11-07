from datetime import datetime, timedelta

import pytest

from app.coordinator.services.alerts import CAMERA_ALARM_MESSAGE, STANDING_MESSAGE, evaluate_response, level_for
from app.coordinator.services.scoring import DEFAULT_CONFIG, apply_tick, speed_factor
from app.coordinator.services.trips import TIPS
from app.domain.enums import Behavior, DashboardLight, SafetyLevel, SoundLevel
from app.domain.trip import CameraView, Trip

DAY = datetime(2026, 11, 6, 14, 0, 0)
NIGHT = datetime(2026, 11, 6, 23, 0, 0)
PHONE = {Behavior.LOOKING_AT_PHONE}


def new_trip() -> Trip:
    return Trip(id="t", driver_id="d", started_at=DAY)


def drive(trip: Trip, seconds: float, speed: float, behaviors=frozenset(), start: datetime = DAY,
          model_risk: float | None = None, step: float = 0.5) -> None:
    """Ticks every `step` seconds (like the camera path), continuing from the trip's last tick."""
    t = trip.last_tick_at or start
    if trip.last_tick_at is None:
        apply_tick(trip, t, speed, set(behaviors), model_risk)
    for _ in range(round(seconds / step)):
        t += timedelta(seconds=step)
        apply_tick(trip, t, speed, set(behaviors), model_risk)


def test_every_behavior_has_a_severity_and_a_tip():
    assert set(DEFAULT_CONFIG.severity) == set(Behavior)
    assert set(TIPS) == set(Behavior)


def test_score_comes_back_once_the_driver_does():
    trip = new_trip()
    drive(trip, 5, speed=50)
    assert trip.score == 100
    drive(trip, 3, speed=50, behaviors=PHONE)
    assert level_for(trip.score) in (SafetyLevel.HIGH_RISK, SafetyLevel.CRITICAL)
    low = trip.score
    drive(trip, 1, speed=50)
    assert trip.score <= low  # the model lost the phone for a second: still the same call (bridge)
    drive(trip, 12, speed=50)
    assert trip.score > 95  # a few clean seconds after the bridge: back to safe
    drive(trip, 3, speed=50, behaviors=PHONE)  # and it drops again the next time: a live reading, not a balance
    assert trip.score < 50


def test_a_flickering_phone_is_one_smooth_call():
    trip = new_trip()
    drive(trip, 0, speed=50)
    scores = []
    for _ in range(6):  # a 12 s call; the model loses the phone for half a second every 2 s
        drive(trip, 1.5, speed=50, behaviors=PHONE, step=0.25)
        scores.append(trip.score)
        drive(trip, 0.5, speed=50, step=0.25)
        scores.append(trip.score)
        assert Behavior.LOOKING_AT_PHONE in trip.active  # the gap doesn't end it
    assert scores == sorted(scores, reverse=True)  # only goes down while the call lasts: no saw-tooth
    assert trip.stats[Behavior.LOOKING_AT_PHONE].occurrences == 1


def test_a_glance_is_not_eyes_off_the_road():
    trip = new_trip()
    drive(trip, 0, speed=50)
    for _ in range(3):  # 1.5 s glances at a mirror, 3 s apart: normal driving
        drive(trip, 1.5, speed=50, behaviors={Behavior.EYES_OFF_ROAD})
        drive(trip, 3, speed=50)
    assert trip.score == 100 and trip.stats == {} and not trip.active
    drive(trip, 3, speed=50, behaviors={Behavior.EYES_OFF_ROAD})  # longer than 2 s: now it counts
    assert Behavior.EYES_OFF_ROAD in trip.active and trip.score < 90


def test_the_longer_it_lasts_the_worse_it_gets():
    trip, scores = new_trip(), []
    drive(trip, 0, speed=50)
    for _ in range(5):
        drive(trip, 1, speed=50, behaviors=PHONE)
        scores.append(trip.score)
    assert scores == sorted(scores, reverse=True) and scores[0] - scores[-1] > 15


def test_speed_amplifies_the_danger():
    assert speed_factor(0) == speed_factor(4.9) == 0
    assert 0 < speed_factor(6) < speed_factor(30) < speed_factor(50) == 1 < speed_factor(90) < speed_factor(130)
    assert speed_factor(200) == speed_factor(130)
    scores = []
    for speed in (8, 30, 50, 90, 130):
        trip = new_trip()
        drive(trip, 2, speed=speed, behaviors=PHONE)
        scores.append(trip.score)
    assert scores == sorted(scores, reverse=True)
    assert level_for(scores[0]) in (SafetyLevel.SAFE, SafetyLevel.CAUTION, SafetyLevel.WARNING)  # walking pace: mild
    assert level_for(scores[-1]) in (SafetyLevel.CRITICAL, SafetyLevel.EMERGENCY)  # highway: severe


def test_standing_still_never_warns():
    trip = new_trip()
    drive(trip, 30, speed=0, behaviors=PHONE | {Behavior.HANDS_OFF_WHEEL})
    assert trip.score == 100 and trip.stats == {} and trip.moving_s == 0
    response = evaluate_response(trip, speed_kmh=0)
    assert response.dashboard_light is DashboardLight.GREEN and not response.vibrate_seat
    assert response.sound is SoundLevel.NONE and response.message == STANDING_MESSAGE


def test_stopping_the_car_ends_the_danger():
    trip = new_trip()
    drive(trip, 3, speed=90, behaviors=PHONE)
    assert trip.score < 35
    drive(trip, 0.5, speed=0, behaviors=PHONE)  # stopped at a light, phone still in hand
    response = evaluate_response(trip, speed_kmh=0)
    assert not response.vibrate_seat and response.sound is SoundLevel.NONE
    drive(trip, 3, speed=0, behaviors=PHONE)
    assert trip.score > 99


def test_night_is_stricter_than_day():
    day, night = new_trip(), new_trip()
    drive(day, 2, speed=40, behaviors=PHONE, start=DAY)
    drive(night, 2, speed=40, behaviors=PHONE, start=NIGHT)
    assert night.score < day.score


def test_the_models_risk_counts():
    calm, alarmed = new_trip(), new_trip()
    drive(calm, 3, speed=90, model_risk=0.02)  # what the CV risk engine gives for a calm driver
    drive(alarmed, 3, speed=90, model_risk=0.9)  # its red alert (e.g. a microsleep)
    assert level_for(calm.score) is SafetyLevel.SAFE
    assert level_for(alarmed.score) is SafetyLevel.CRITICAL


def test_statistics_count_only_while_moving():
    trip = new_trip()
    drive(trip, 3, speed=40, behaviors=PHONE)
    drive(trip, 5, speed=40)  # longer than the phone's bridge: the next look is a new occurrence
    drive(trip, 3, speed=40, behaviors=PHONE)
    drive(trip, 4, speed=0, behaviors=PHONE)
    stat = trip.stats[Behavior.LOOKING_AT_PHONE]
    assert stat.occurrences == 2 and stat.total_seconds == pytest.approx(6, abs=0.6)
    assert trip.moving_s == pytest.approx(11, abs=0.6) and trip.elapsed_s == pytest.approx(15, abs=0.6)
    assert trip.min_score < trip.average_score < 100  # the average covers the 11 s of driving only


def test_only_a_collapse_is_an_emergency():
    trip = new_trip()
    drive(trip, 0, speed=130)
    drive(trip, 10, speed=130, behaviors={Behavior.DROWSY} | PHONE, model_risk=1.0)  # as bad as it gets otherwise
    assert trip.score >= 10 and level_for(trip.score) is SafetyLevel.CRITICAL
    assert DEFAULT_CONFIG.score_floor == 10


@pytest.mark.parametrize(
    ("score", "level"),
    [
        (100, SafetyLevel.SAFE),
        (90, SafetyLevel.SAFE),
        (89.9, SafetyLevel.CAUTION),
        (75, SafetyLevel.CAUTION),
        (60, SafetyLevel.WARNING),
        (40, SafetyLevel.HIGH_RISK),
        (10, SafetyLevel.CRITICAL),
        (9.9, SafetyLevel.EMERGENCY),
        (0, SafetyLevel.EMERGENCY),
    ],
)
def test_level_bands(score, level):
    assert level_for(score) is level


def test_the_car_reacts_while_something_is_happening():
    trip = new_trip()
    trip.score = 40
    trip.active = {Behavior.HANDS_OFF_WHEEL: 2.0}
    response = evaluate_response(trip, speed_kmh=50)
    assert response.dashboard_light is DashboardLight.YELLOW
    assert response.vibrate_seat is True and response.sound is SoundLevel.HIGH

    trip.active = {}  # the driver put the phone away: silence at once, the light follows the score back
    response = evaluate_response(trip, speed_kmh=50)
    assert response.dashboard_light is DashboardLight.YELLOW
    assert response.vibrate_seat is False and response.sound is SoundLevel.NONE


def test_caution_only_lights_up():
    trip = new_trip()
    trip.score = 80
    trip.active = {Behavior.HANDS_OFF_WHEEL: 1.0}
    response = evaluate_response(trip, speed_kmh=50)
    assert response.dashboard_light is DashboardLight.GREEN_YELLOW
    assert response.vibrate_seat is False and response.sound is SoundLevel.NONE


def test_the_models_red_alert_sounds_even_when_the_score_is_high():
    trip = new_trip()
    trip.score = 95
    trip.camera = CameraView(risk=0.3, alert="red")
    response = evaluate_response(trip, speed_kmh=50)
    assert response.vibrate_seat is True and response.sound is SoundLevel.HIGH
    assert response.message == CAMERA_ALARM_MESSAGE
