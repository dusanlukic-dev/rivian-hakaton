"""Collapse (rivian_model/): the driver slumped over and still -> score 0 and the emergency, at any speed."""

from datetime import datetime, timedelta

from app.coordinator.services.alerts import COLLAPSE_MESSAGE, STANDING_MESSAGE, evaluate_response, level_for
from app.coordinator.services.camera import behaviors_from_frame
from app.coordinator.services.risk_engine import RiskEngine, load_risk_config
from app.coordinator.services.scoring import DEFAULT_CONFIG, apply_tick, collapse_confirmed
from app.coordinator.services.trips import process_tick
from app.core.config import get_settings
from app.domain.enums import Behavior, DashboardLight, SafetyLevel, SoundLevel, SpeedSource
from app.domain.trip import EmergencyContact, Trip
from app.schemas.camera import FrameCategory, ModelFrame
from app.schemas.trip import TelemetryTick

DAY = datetime(2026, 11, 7, 14, 0, 0)
COLLAPSE = {Behavior.COLLAPSE}


def new_trip() -> Trip:
    return Trip(id="t", driver_id="d", started_at=DAY, emergency_contact=EmergencyContact("Mama", "+381600000000"))


def ticks(trip: Trip, seconds: float, speed: float, behaviors=frozenset(), step: float = 0.1) -> list[bool]:
    """process_tick every `step` s (like the model path); returns whether each tick triggered the emergency."""
    t = trip.last_tick_at or DAY
    fired = []
    for _ in range(round(seconds / step)):
        t += timedelta(seconds=step)
        tick = TelemetryTick(timestamp=t, behaviors=set(behaviors))
        fired.append(process_tick(trip, tick, speed, SpeedSource.MOCK))
    return fired


def test_confirmed_collapse_zeroes_the_score_and_alerts_once_at_driving_speed():
    trip = new_trip()
    ticks(trip, 3, speed=55)
    assert trip.score == 100
    fired = ticks(trip, 3, speed=55, behaviors=COLLAPSE)
    assert fired.count(True) == 1  # the contact is alerted once
    first = fired.index(True)
    assert 1.9 <= (first + 1) * 0.1 <= 2.2  # right after collapse_confirm_s
    assert trip.score == 0 and level_for(trip.score) is SafetyLevel.EMERGENCY
    assert trip.emergency_alert_sent
    response = evaluate_response(trip, 55)
    assert (response.dashboard_light, response.vibrate_seat, response.sound, response.message) == (
        DashboardLight.RED, True, SoundLevel.HIGH, COLLAPSE_MESSAGE)


def test_nothing_but_a_collapse_alerts_the_contact():
    trip = new_trip()
    fired = ticks(trip, 10, speed=130, behaviors={Behavior.DROWSY, Behavior.LOOKING_AT_PHONE})
    assert True not in fired and not trip.emergency_alert_sent
    assert trip.score >= 10 and level_for(trip.score) is SafetyLevel.CRITICAL


def test_collapse_in_a_stopped_car_is_still_an_emergency():
    trip = new_trip()
    fired = ticks(trip, 3, speed=0, behaviors=COLLAPSE)
    assert True in fired and trip.score == 0
    assert evaluate_response(trip, 0).message == COLLAPSE_MESSAGE


def test_a_short_slump_is_not_an_emergency():
    trip = new_trip()
    fired = ticks(trip, 1.0, speed=0, behaviors=COLLAPSE)  # bending down for a second, standing still
    assert True not in fired and not collapse_confirmed(trip)
    assert evaluate_response(trip, 0).message == STANDING_MESSAGE
    ticks(trip, 3, speed=0)
    assert trip.score == 100 and not trip.emergency_alert_sent


def test_a_flickering_signal_keeps_the_emergency():
    trip = new_trip()
    ticks(trip, 2.5, speed=55, behaviors=COLLAPSE)
    assert trip.score == 0
    for _ in range(4):  # the model loses the slumped pose for half a second, then finds it again
        ticks(trip, 0.5, speed=55)
        assert trip.score == 0 and evaluate_response(trip, 55).message == COLLAPSE_MESSAGE
        ticks(trip, 0.5, speed=55, behaviors=COLLAPSE)
        assert trip.score == 0


def test_the_score_comes_back_when_the_driver_sits_up():
    trip = new_trip()
    ticks(trip, 3, speed=55, behaviors=COLLAPSE)
    ticks(trip, DEFAULT_CONFIG.collapse_hold_s - 0.5, speed=55)
    assert trip.score == 0  # still held
    ticks(trip, 10, speed=55)
    assert trip.score > 90 and not collapse_confirmed(trip)


def test_model_category_collapse_maps_to_the_behavior():
    frame = ModelFrame(categories={"collapse": FrameCategory(p=1.0, active=True),
                                   "phone_use": FrameCategory(p=0.1, active=False)})
    assert behaviors_from_frame(frame) == COLLAPSE


def test_risk_config_raises_a_red_alert_for_a_collapse():
    engine = RiskEngine(load_risk_config(get_settings().risk_config_file))
    assert "collapse" in engine.cats
    rec = None
    for i in range(40):  # 4 s of full collapse evidence at 10 fps
        rec = engine.step(i * 0.1, {"collapse": 1.0})
    assert rec["categories"]["collapse"]["active"]
    assert "collapse" in rec["rules_triggered"] and rec["alert"]["level"] == "red"


def test_an_unconfirmed_collapse_costs_no_points():
    trip = new_trip()
    apply_tick(trip, DAY, 55, COLLAPSE)
    apply_tick(trip, DAY + timedelta(seconds=1), 55, COLLAPSE)
    assert trip.score == 100 and not collapse_confirmed(trip)
    assert DEFAULT_CONFIG.collapse_confirm_s == 2.0


def test_a_short_slump_while_driving_keeps_the_score():
    # 032409 (getting out of the car): the model saw a collapse for ~0.3 s and the score fell 80 -> 47.
    trip = new_trip()
    ticks(trip, 3, speed=55)
    for _ in range(3):
        ticks(trip, 0.3, speed=55, behaviors=COLLAPSE)
        ticks(trip, 2.0, speed=55)
    assert trip.score == 100 and trip.min_score == 100 and not trip.emergency_alert_sent
