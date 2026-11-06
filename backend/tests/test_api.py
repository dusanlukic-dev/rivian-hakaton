from datetime import timedelta

from tests.conftest import API, CONTACT, DAY, MODEL_FRAME, NIGHT, send_tick, start_trip


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


def send_frame(client, ts, speed, frame):
    body = {"timestamp": ts.isoformat(), "speed_kmh": speed, "frame": frame}
    res = client.post(f"{API}/telemetry", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def test_model_frame_is_scored_and_forwarded(client):
    start_trip(client)
    with client.websocket_connect(f"{API}/ws") as ws:
        ws.receive_json()  # current state on connect
        state = send_frame(client, DAY, 60, MODEL_FRAME)  # daytime city: 6 pts x 1.3 -> still safe
        pushed = ws.receive_json()

    assert pushed["data"] == state
    # Active categories become backend labels and cost points; inactive ones don't.
    assert set(state["active_behaviors"]) == {"looking_at_phone", "eyes_off_road"}
    assert state["score"] < 100

    camera = state["camera"]
    assert camera["risk"] == 0.819
    assert camera["alert"] == "red"
    assert camera["rules_triggered"] == ["long_distraction", "phone_sustained"]
    assert camera["groups"]["visual"] == 0.767
    assert camera["categories"]["phone_use"] == {"p": 0.715, "active": True, "run_s": 3.2, "r": 0.534}
    assert "perception" not in str(state)

    # Still "safe" by score, but the model's red alert makes the car react right away.
    assert state["level"] == "safe"
    assert state["response"]["vibrate_seat"] is True
    assert state["response"]["sound"] == "high"
    assert state["response"]["message"] == "Danger detected - eyes on the road now."


def test_camera_alarm_is_silent_while_stationary(client):
    start_trip(client)
    state = send_frame(client, NIGHT, 0, MODEL_FRAME)
    assert state["score"] == 100
    assert state["response"]["vibrate_seat"] is False
    assert state["response"]["sound"] == "none"


def test_unknown_camera_category_is_shown_but_not_scored(client):
    start_trip(client)
    frame = {"categories": {"eating": {"p": 0.9, "active": True}}, "alert": {"code": 1}}
    state = send_frame(client, NIGHT, 60, frame)
    assert state["score"] == 100
    assert state["active_behaviors"] == {}
    assert state["camera"]["categories"]["eating"]["active"] is True
    assert state["camera"]["alert"] == "yellow"  # from the code when the level is missing


def test_camera_view_clears_on_a_tick_without_frame(client):
    start_trip(client)
    assert send_frame(client, NIGHT, 60, MODEL_FRAME)["camera"] is not None
    assert send_tick(client, NIGHT + timedelta(seconds=1), 60)["camera"] is None


def test_nan_in_model_frame_becomes_null(client):
    start_trip(client)
    # Python's json.dumps writes NaN for float("nan"); it must not reach the app.
    raw = (
        '{"timestamp": "%s", "speed_kmh": 60, "frame": '
        '{"categories": {"phone_use": {"p": NaN, "active": false}}, "risk": {"final": NaN}}}'
    ) % NIGHT.isoformat()
    res = client.post(f"{API}/telemetry", content=raw, headers={"Content-Type": "application/json"})
    assert res.status_code == 200, res.text
    assert res.json()["camera"]["risk"] is None
    assert res.json()["camera"]["categories"]["phone_use"]["p"] is None


def test_unknown_behavior_is_rejected(client):
    start_trip(client)
    res = client.post(
        f"{API}/telemetry",
        json={"timestamp": NIGHT.isoformat(), "speed_kmh": 50, "behaviors": ["dancing"]},
    )
    assert res.status_code == 422
