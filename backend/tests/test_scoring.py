from datetime import datetime, timedelta

import pytest

from app.domain.enums import Behavior, DashboardLight, SafetyLevel, SoundLevel
from app.domain.trip import Trip
from app.services.alerts import evaluate_response, level_for
from app.services.scoring import DEFAULT_CONFIG, apply_tick
from app.services.trips import TIPS

DAY = datetime(2026, 11, 6, 14, 0, 0)
NIGHT = datetime(2026, 11, 6, 23, 0, 0)
PHONE = {Behavior.LOOKING_AT_PHONE}


def new_trip() -> Trip:
    return Trip(id="t", driver_id="d", started_at=DAY)


def drive(trip: Trip, seconds: int, speed: float, behaviors=frozenset(), start: datetime = DAY) -> None:
    """Send one tick per second, continuing from the trip's last tick."""
    t = trip.last_tick_at or start
    if trip.last_tick_at is None:
        apply_tick(trip, t, speed, set(behaviors))
    for _ in range(seconds):
        t += timedelta(seconds=1)
        apply_tick(trip, t, speed, set(behaviors))


def test_every_behavior_has_a_weight_and_a_tip():
    assert set(DEFAULT_CONFIG.behavior_weights) == set(Behavior)
    assert set(TIPS) == set(Behavior)


def test_no_penalty_when_stationary():
    trip = new_trip()
    drive(trip, 30, speed=0, behaviors=PHONE)
    assert trip.score == 100
    assert trip.stats == {}


def test_highway_is_stricter_than_city():
    city, highway = new_trip(), new_trip()
    drive(city, 5, speed=40, behaviors=PHONE)
    drive(highway, 5, speed=120, behaviors=PHONE)
    assert highway.score < city.score < 100


def test_night_is_stricter_than_day():
    day, night = new_trip(), new_trip()
    drive(day, 5, speed=40, behaviors=PHONE, start=DAY)
    drive(night, 5, speed=40, behaviors=PHONE, start=NIGHT)
    assert night.score < day.score


def test_lower_score_drops_faster():
    high, low = new_trip(), new_trip()
    low.score = 50
    drive(high, 3, speed=40, behaviors=PHONE)
    drive(low, 3, speed=40, behaviors=PHONE)
    assert (50 - low.score) > (100 - high.score)


def test_recovery_only_after_grace_period():
    trip = new_trip()
    drive(trip, 5, speed=40, behaviors=PHONE)
    after_incident = trip.score

    drive(trip, 30, speed=40)  # grace period: no recovery yet
    assert trip.score == pytest.approx(after_incident)

    drive(trip, 60, speed=40)  # 60 s * 0.05 = +3 points
    assert trip.score == pytest.approx(after_incident + 3)


def test_occurrences_counted_per_streak():
    trip = new_trip()
    drive(trip, 3, speed=40, behaviors=PHONE)
    drive(trip, 2, speed=40)
    drive(trip, 3, speed=40, behaviors=PHONE)
    assert trip.stats[Behavior.LOOKING_AT_PHONE].occurrences == 2
    assert trip.stats[Behavior.LOOKING_AT_PHONE].total_seconds == pytest.approx(6)


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


def test_caution_vibrates_only_after_five_seconds():
    trip = new_trip()
    trip.score = 80
    trip.active = {Behavior.HANDS_OFF_WHEEL: 4.0}
    assert evaluate_response(trip, speed_kmh=50).vibrate_seat is False

    trip.active = {Behavior.HANDS_OFF_WHEEL: 5.0}
    response = evaluate_response(trip, speed_kmh=50)
    assert response.vibrate_seat is True
    assert response.sound is SoundLevel.NONE
    assert response.dashboard_light is DashboardLight.GREEN_YELLOW


def test_high_risk_reacts_faster_and_louder():
    trip = new_trip()
    trip.score = 40
    trip.active = {Behavior.HANDS_OFF_WHEEL: 2.0}
    response = evaluate_response(trip, speed_kmh=50)
    assert response.vibrate_seat is True
    assert response.sound is SoundLevel.HIGH


def test_no_alerts_while_stationary():
    trip = new_trip()
    trip.score = 20
    trip.active = {Behavior.LOOKING_AT_PHONE: 30.0}
    response = evaluate_response(trip, speed_kmh=0)
    assert response.dashboard_light is DashboardLight.RED
    assert response.vibrate_seat is False
    assert response.sound is SoundLevel.NONE
