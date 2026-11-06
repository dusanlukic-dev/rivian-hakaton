from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.trips import InMemoryTripRepository, get_trip_repository
from app.services.live import LiveHub, get_live_hub

API = "/api/v1"
NIGHT = datetime(2026, 11, 6, 23, 0, 0, tzinfo=timezone(timedelta(hours=1)))
CONTACT = {"name": "Ana", "phone": "+381600000000"}


@pytest.fixture
def client():
    repo, hub = InMemoryTripRepository(), LiveHub()
    app.dependency_overrides[get_trip_repository] = lambda: repo
    app.dependency_overrides[get_live_hub] = lambda: hub
    # Context manager = one event loop shared by HTTP calls and WebSocket sessions.
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def start_trip(client, **body):
    res = client.post(f"{API}/trips", json={"driver_id": "driver-1", **body})
    assert res.status_code == 201, res.text
    return res.json()


def send_tick(client, ts, speed, behaviors=()):
    body = {"timestamp": ts.isoformat(), "speed_kmh": speed, "behaviors": list(behaviors)}
    res = client.post(f"{API}/telemetry", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def test_health(client):
    assert client.get(f"{API}/health").json() == {"status": "ok"}


def test_full_trip_flow(client):
    state = start_trip(client, emergency_contact=CONTACT)
    trip_id = state["trip_id"]
    assert state["score"] == 100
    assert state["level"] == "safe"
    assert state["response"]["dashboard_light"] == "green"

    # Phone use on the highway at night until the score bottoms out.
    for i in range(60):
        state = send_tick(client, NIGHT + timedelta(seconds=i), 130, ["looking_at_phone"])
    assert state["trip_id"] == trip_id
    assert state["level"] == "emergency"
    assert state["emergency_alert_sent"] is True
    assert state["response"]["dashboard_light"] == "red"
    assert state["response"]["sound"] == "high"
    assert state["active_behaviors"]["looking_at_phone"] > 0

    summary = client.post(f"{API}/trips/{trip_id}/end").json()
    assert summary["status"] == "ended"
    assert summary["behaviors"][0]["behavior"] == "looking_at_phone"
    assert summary["behaviors"][0]["tip"]

    assert client.get(f"{API}/trips", params={"driver_id": "driver-1"}).json()[0]["trip_id"] == trip_id

    overview = client.get(f"{API}/analytics/overview").json()
    assert overview["completed_trips"] == 1
    assert overview["emergency_alerts"] == 1
    assert overview["behaviors"][0]["behavior"] == "looking_at_phone"


def test_websocket_pushes_live_events(client):
    with client.websocket_connect(f"{API}/ws") as ws:
        trip_id = start_trip(client, emergency_contact=CONTACT)["trip_id"]
        started = ws.receive_json()
        assert started["type"] == "trip_started"
        assert started["data"]["trip_id"] == trip_id

        send_tick(client, NIGHT, 130, ["looking_at_phone"])
        update = ws.receive_json()
        assert update["type"] == "state"
        assert update["data"]["score"] < 100

        for i in range(1, 60):
            send_tick(client, NIGHT + timedelta(seconds=i), 130, ["looking_at_phone"])
        types = [ws.receive_json()["type"] for _ in range(60)]  # 59 states + 1 emergency
        assert types.count("emergency") == 1

        client.post(f"{API}/trips/{trip_id}/end")
        ended = ws.receive_json()
        assert ended["type"] == "trip_ended"
        assert ended["data"]["final_score"] < 10


def test_websocket_sends_current_state_on_connect(client):
    trip_id = start_trip(client)["trip_id"]
    with client.websocket_connect(f"{API}/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "state"
        assert hello["data"]["trip_id"] == trip_id


def test_starting_a_trip_ends_the_previous_one(client):
    first = start_trip(client)["trip_id"]
    second = start_trip(client)["trip_id"]
    assert client.get(f"{API}/trips/{first}").json()["status"] == "ended"
    assert send_tick(client, NIGHT, 50)["trip_id"] == second


def test_telemetry_without_active_trip_is_rejected(client):
    res = client.post(f"{API}/telemetry", json={"timestamp": NIGHT.isoformat(), "speed_kmh": 50})
    assert res.status_code == 409

    trip_id = start_trip(client)["trip_id"]
    client.post(f"{API}/trips/{trip_id}/end")
    res = client.post(f"{API}/telemetry", json={"timestamp": NIGHT.isoformat(), "speed_kmh": 50})
    assert res.status_code == 409


def test_unknown_trip_returns_404(client):
    assert client.get(f"{API}/trips/nope").status_code == 404


def test_unknown_behavior_is_rejected(client):
    start_trip(client)
    res = client.post(
        f"{API}/telemetry",
        json={"timestamp": NIGHT.isoformat(), "speed_kmh": 50, "behaviors": ["dancing"]},
    )
    assert res.status_code == 422
