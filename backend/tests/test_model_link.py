"""Camera -> coordinator -> model worker -> evidence -> extracted risk engine -> score, sections, images."""

import time

from app.coordinator.services.model_link import pack_frame, unpack_frame
from tests.conftest import API, DAY, MODEL_FRAME, flush, send_tick, start_trip

PHONE = {"phone_use": 0.95, "eyes_off_road": 0.9, "hands_off_wheel": 0.1}
CALM = {"phone_use": 0.02, "eyes_off_road": 0.05, "hands_off_wheel": 0.1}


def wait_for(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.005)


def test_frame_protocol_roundtrip():
    header = {"type": "frame", "id": 7, "t": 1.25, "trip_id": "abc"}
    assert unpack_frame(pack_frame(header, b"\xff\xd8\xffjpeg")) == (header, b"\xff\xd8\xffjpeg")


def test_model_worker_drives_the_score(client, clock, coordinator, jpeg_frames):
    with client.websocket_connect(f"{API}/model/ws") as model, client.websocket_connect(f"{API}/ws") as phone:
        model.send_json({"type": "hello", "worker": "fake", "version": "test"})
        trip_id = start_trip(client)["trip_id"]
        assert model.receive_json() == {"type": "reset", "trip_id": trip_id}

        frames = 170  # 17 s at 10 fps; the mock city drive starts moving after ~7 s
        for i in range(frames):
            clock.advance(0.1)
            res = client.post(f"{API}/video/frames", content=jpeg_frames[i % len(jpeg_frames)],
                              headers={"Content-Type": "image/jpeg"})
            assert res.status_code == 204
            header, jpeg = unpack_frame(model.receive_bytes())
            assert header["type"] == "frame" and header["trip_id"] == trip_id and jpeg[:3] == b"\xff\xd8\xff"
            assert abs(header["t"] - (i + 1) * 0.1) < 1e-6  # seconds since the trip started
            evidence = PHONE if 90 <= i < 140 else CALM  # phone in hand from 9 s to 14 s
            model.send_json({"type": "detection", "id": header["id"], "t": header["t"], "trip_id": trip_id,
                             "evidence": evidence, "ms": 42.0})
            wait_for(lambda n=i + 1: coordinator.model.detections == n)

        status = client.get(f"{API}/coordinator/status").json()
        assert status["model"]["connected"] and status["model"]["worker"] == "fake"
        assert status["model"]["detections"] == frames and status["risk_engine"]["loaded"]

        assert client.post(f"{API}/trips/{trip_id}/end").status_code == 200
        assert model.receive_json() == {"type": "idle"}
        messages = []
        while not messages or messages[-1]["type"] != "trip_ended":
            messages.append(phone.receive_json())

    states = [m["data"] for m in messages if m["type"] == "state"]
    assert 30 <= len(states) < frames  # 10 detections a second reach the phone ~2/s (plus every change)
    assert any(s["camera"] and s["camera"]["alert"] == "red" for s in states)
    assert any("looking_at_phone" in s["active_behaviors"] for s in states)

    flush(client, coordinator)
    report = client.get(f"{API}/trips/{trip_id}/report").json()
    sections = report["sections"]
    assert len(sections) == 9 and all(s["ticks"] >= 10 for s in sections[:-1])
    critical = [s for s in sections if s["danger"] == "critical"]
    assert critical and all(s["has_image"] for s in critical)  # the analysed frame of the riskiest moment
    assert all(s["categories"]["phone_use"]["active"] for s in critical)
    [moment] = [m for m in report["moments"] if m["danger"] == "critical"]
    assert 9 <= moment["t_start"] + 2 and moment["t_end"] <= 18 and moment["image_url"]
    assert "looking_at_phone" in moment["behaviors"] and moment["alert"] == "red"
    assert report["trip"]["min_score"] < 100


def test_slow_model_gets_the_newest_frame_and_lost_frames_time_out(client, clock, coordinator, jpeg_frames):
    def post(i):
        clock.advance(0.1)
        client.post(f"{API}/video/frames", content=jpeg_frames[i], headers={"Content-Type": "image/jpeg"})

    with client.websocket_connect(f"{API}/model/ws") as model:
        model.send_json({"type": "hello", "worker": "slow"})
        trip_id = start_trip(client)["trip_id"]
        model.receive_json()  # reset
        post(0)
        first, _ = unpack_frame(model.receive_bytes())
        for i in range(1, 5):  # the model is busy: these replace each other while they wait
            post(i)
        model.send_json({"type": "detection", "id": first["id"], "trip_id": trip_id, "evidence": CALM})
        newest, _ = unpack_frame(model.receive_bytes())
        assert newest["id"] == first["id"] + 4 and coordinator.model.replaced == 3

        clock.advance(10)  # no answer for the newest frame
        post(5)
        client.portal.call(coordinator.housekeeping_once)
        assert coordinator.model.lost == 1
        after, _ = unpack_frame(model.receive_bytes())
        assert after["id"] == newest["id"] + 1


def test_debug_feed_is_refused_while_a_model_worker_drives(client, coordinator):
    """risk_pipeline.py --mode prod posts frame records it scored itself: a debug feed, never mixed with the worker."""
    with client.websocket_connect(f"{API}/model/ws") as model:
        model.send_json({"type": "hello", "worker": "fake", "version": "test"})
        trip_id = start_trip(client)["trip_id"]
        assert model.receive_json() == {"type": "reset", "trip_id": trip_id}
        res = client.post(f"{API}/telemetry", json={"timestamp": DAY.isoformat(), "frame": MODEL_FRAME})
        assert res.status_code == 409 and "debug feed" in res.json()["detail"]
        res = client.post(f"{API}/telemetry", json={"timestamp": DAY.isoformat(), "behaviors": ["looking_at_phone"]})
        assert res.status_code == 200  # the simulator's labels still go through
    wait_for(lambda: not coordinator.model.connected)
    state = send_tick(client, DAY, 60, frame=MODEL_FRAME)  # no worker: the debug feed scores the trip
    assert state["camera"]["alert"] == "red"
    assert client.get(f"{API}/coordinator/status").json()["debug_feed"] == {"telemetry_frames": 1}
