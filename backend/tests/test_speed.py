from datetime import timedelta

import pytest

from app.domain.enums import SpeedSource
from app.services.speed import (
    RANDOM_POOL,
    SCENARIOS,
    PhoneSpeedDisabled,
    SpeedReading,
    SpeedService,
    bezier,
    ease,
)
from tests.conftest import API, DAY, FakeClock, send_tick, start_trip


def test_ease_is_a_bezier_with_flat_handles():
    assert ease(10, 50, 0) == 10
    assert ease(10, 50, 1) == 50
    assert ease(0, 100, 0.5) == pytest.approx(50)
    # Flat at both ends: the first and last 10 % of the time cover only ~3 % of the change.
    assert ease(0, 100, 0.1) < 5 and ease(0, 100, 0.9) > 95
    # Handles at 1/3 and 2/3 would make it a straight line.
    assert bezier(0, 100 / 3, 200 / 3, 100, 0.25) == pytest.approx(25)


@pytest.mark.parametrize("scenario", SCENARIOS.values(), ids=list(SCENARIOS))
def test_scenarios_are_smooth_loops(scenario):
    times = [t for t, _ in scenario.keyframes]
    assert times[0] == 0 and times == sorted(set(times))
    assert scenario.speed_at(scenario.loop_from_s) == pytest.approx(scenario.keyframes[-1][1])  # seamless loop
    previous = scenario.speed_at(0)
    for i in range(1, int(scenario.duration_s * 2 * 3)):  # three laps, every 0.5 s
        v = scenario.speed_at(i * 0.5)
        assert 0 <= v <= 140
        assert abs(v - previous) <= 8, f"jump at {i * 0.5} s"  # at most 16 km/h per second
        previous = v


def test_scenarios_include_standing_still():
    assert all(SCENARIOS["parked"].speed_at(t) == 0 for t in range(0, 600, 7))
    city = [SCENARIOS["city"].speed_at(t) for t in range(240)]
    assert any(v < 5 for v in city[20:]) and max(city) > 45  # red lights, and real driving
    jam = [SCENARIOS["stop_and_go"].speed_at(t) for t in range(120)]
    assert sum(v < 5 for v in jam) > 30  # long standstills
    assert min(SCENARIOS["cruise"].speed_at(t) for t in range(8, 600)) >= 45  # never stops once going


def test_random_scenario_is_stable_per_trip():
    service = SpeedService()
    picks = {service.scenario_for(f"trip-{i}").name for i in range(40)}
    assert picks <= set(RANDOM_POOL) and len(picks) > 1
    assert SpeedService().scenario_for("trip-7") == service.scenario_for("trip-7")


def test_unknown_scenario_is_rejected():
    with pytest.raises(ValueError, match="SPEED_SCENARIO"):
        SpeedService(scenario="moon")


def test_mock_follows_the_trip_clock():
    service = SpeedService(scenario="city")
    readings = [service.resolve("t", DAY + timedelta(seconds=s), None) for s in (0, 3, 30, 110)]
    assert {r.source for r in readings} == {SpeedSource.MOCK}
    assert readings[0].speed_kmh == 0 and readings[1].speed_kmh == 0  # pulling out
    assert readings[2].speed_kmh > 40  # cruising
    assert readings[3].speed_kmh == 0  # red light at 100-118 s


def test_phone_then_tick_then_mock():
    clock = FakeClock()
    service = SpeedService(scenario="parked", phone_enabled=True, clock=clock)
    assert service.resolve("t", DAY, None) == SpeedReading(0.0, SpeedSource.MOCK)
    assert service.resolve("t", DAY, 70) == SpeedReading(70, SpeedSource.TELEMETRY)
    service.report_phone(42.0, lat=44.81, lon=20.46)
    assert service.resolve("t", DAY, 70) == SpeedReading(42.0, SpeedSource.PHONE, 44.81, 20.46)
    clock.advance(6)  # GPS went quiet: back to the tick's speed
    assert service.resolve("t", DAY, 70).source is SpeedSource.TELEMETRY


def test_phone_speed_is_off_by_default():
    with pytest.raises(PhoneSpeedDisabled):
        SpeedService().report_phone(30)


def test_tick_without_speed_uses_the_mock_drive(client):
    start_trip(client)
    state = send_tick(client, DAY, behaviors=["looking_at_phone"])
    assert (state["speed_kmh"], state["speed_source"]) == (0, "mock")  # the city drive starts parked
    assert state["score"] == 100  # standing still: no penalty
    state = send_tick(client, DAY + timedelta(seconds=30), behaviors=["looking_at_phone"])
    assert state["speed_kmh"] > 40 and state["speed_source"] == "mock"
    assert state["score"] < 100


def test_explicit_tick_speed_beats_the_mock(client):
    start_trip(client)
    state = send_tick(client, DAY, 80)
    assert (state["speed_kmh"], state["speed_source"]) == (80, "telemetry")


def test_phone_speed_endpoint(client, speed):
    status = client.get(f"{API}/speed").json()
    assert status["source"] is None and status["phone_enabled"] is False and "parked" in status["scenarios"]
    start_trip(client)
    res = client.post(f"{API}/speed", json={"speed_kmh": 50})
    assert res.status_code == 409

    speed.phone_enabled = True  # PHONE_SPEED_ENABLED=true
    status = client.post(f"{API}/speed", json={"speed_kmh": 50, "lat": 44.81, "lon": 20.46}).json()
    assert status["phone_enabled"] is True and status["phone_age_s"] == 0
    state = send_tick(client, DAY, 90)  # a fresh phone reading beats even the tick's own speed
    assert (state["speed_kmh"], state["speed_source"]) == (50, "phone")
    status = client.get(f"{API}/speed").json()
    assert (status["source"], status["speed_kmh"], status["scenario"]) == ("phone", 50, "city")
    assert client.post(f"{API}/speed", json={"speed_kmh": -1}).status_code == 422
