"""Accounts (register, login, tokens), trips owned by an account, history and the per-trip report."""

from datetime import timedelta

from app.repositories.database import Database
from app.repositories.media import MemoryMediaStore
from app.repositories.recordings import RecordingRepository
from app.services.auth import hash_password, verify_password
from app.services.recording import TripRecorder
from tests.conftest import API, CONTACT, DAY, MODEL_FRAME, app_client, bearer, register, send_tick, start_trip


def end_trip(client, trip_id, headers=None):
    res = client.post(f"{API}/trips/{trip_id}/end", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_password_hash_roundtrip():
    stored = hash_password("secret-123")
    assert stored.startswith("scrypt$") and "secret-123" not in stored
    assert verify_password("secret-123", stored)
    assert not verify_password("secret-124", stored)
    assert not verify_password("secret-123", "garbage")


def test_register_login_me_logout(client):
    auth = register(client, "Ana.M", display_name="Ana M", emergency_contact=CONTACT)
    user = auth["user"]
    assert user["username"] == "ana.m"  # lowercased
    assert user["display_name"] == "Ana M" and user["emergency_contact"] == CONTACT
    assert "password" not in str(auth) and auth["token_type"] == "bearer"

    assert client.get(f"{API}/auth/me", headers=bearer(auth)).json() == user
    login = client.post(f"{API}/auth/login", json={"username": "ANA.M", "password": "secret-123"})
    assert login.status_code == 200 and login.json()["token"] != auth["token"]

    assert client.post(f"{API}/auth/logout", headers=bearer(auth)).status_code == 204
    assert client.get(f"{API}/auth/me", headers=bearer(auth)).status_code == 401  # that session is gone
    assert client.get(f"{API}/auth/me", headers=bearer(login.json())).status_code == 200  # the other one isn't


def test_auth_errors(client):
    register(client, "ana")
    assert client.post(f"{API}/auth/register", json={"username": "ana", "password": "another-1"}).status_code == 409
    assert client.post(f"{API}/auth/register", json={"username": "a b", "password": "secret-123"}).status_code == 422
    assert client.post(f"{API}/auth/register", json={"username": "bob", "password": "123"}).status_code == 422
    wrong = client.post(f"{API}/auth/login", json={"username": "ana", "password": "nope-nope"})
    assert wrong.status_code == 401 and wrong.headers["www-authenticate"] == "Bearer"
    assert client.post(f"{API}/auth/login", json={"username": "ghost", "password": "secret-123"}).status_code == 401
    assert client.get(f"{API}/auth/me").status_code == 401
    assert client.get(f"{API}/auth/me", headers=bearer("made-up")).status_code == 401
    # A bad token is an error even where login is optional, instead of silently acting anonymous.
    assert client.post(f"{API}/trips", json={"driver_id": "x"}, headers=bearer("made-up")).status_code == 401


def test_update_profile(client):
    auth = register(client, "ana", emergency_contact=CONTACT)
    headers = bearer(auth)
    user = client.patch(f"{API}/auth/me", json={"display_name": "Ana Anić"}, headers=headers).json()
    assert user["display_name"] == "Ana Anić" and user["emergency_contact"] == CONTACT  # untouched
    user = client.patch(f"{API}/auth/me", json={"emergency_contact": None}, headers=headers).json()
    assert user["emergency_contact"] is None


def test_trip_belongs_to_the_logged_in_driver(client):
    ana, bob = register(client, "ana", emergency_contact=CONTACT), register(client, "bob")
    state = start_trip(client, headers=bearer(ana), driver_id="ignored")
    trip_id = state["trip_id"]
    assert state["driver_id"] == "ana"  # the account, not the body
    send_tick(client, DAY, 60, ["looking_at_phone"])
    end_trip(client, trip_id)  # the car may end it without the token

    mine = client.get(f"{API}/trips", headers=bearer(ana)).json()
    assert [t["trip_id"] for t in mine] == [trip_id]
    assert mine[0]["behaviors"][0]["behavior"] == "looking_at_phone"
    assert client.get(f"{API}/trips", headers=bearer(bob)).json() == []
    assert client.get(f"{API}/trips").json() == []  # anonymous listing shows only trips without login

    assert client.get(f"{API}/trips/{trip_id}/summary", headers=bearer(ana)).status_code == 200
    for headers in (bearer(bob), None):  # someone else's trip looks like it doesn't exist
        assert client.get(f"{API}/trips/{trip_id}/summary", headers=headers).status_code == 404
        assert client.get(f"{API}/trips/{trip_id}", headers=headers).status_code == 404
        assert client.get(f"{API}/trips/{trip_id}/report", headers=headers).status_code == 404
        assert client.get(f"{API}/trips/{trip_id}/events", headers=headers).status_code == 404


def test_trip_without_login_still_needs_a_driver_id(client):
    res = client.post(f"{API}/trips", json={})
    assert res.status_code == 422 and "driver_id" in res.json()["detail"]
    trip_id = start_trip(client)["trip_id"]  # anonymous trips stay readable by anyone
    assert client.get(f"{API}/trips/{trip_id}/summary").status_code == 200
    assert [t["driver_id"] for t in client.get(f"{API}/trips", params={"driver_id": "driver-1"}).json()] == ["driver-1"]


def test_saved_emergency_contact_is_used(client, recorder):
    ana = register(client, "ana", emergency_contact=CONTACT)
    trip_id = start_trip(client, headers=bearer(ana))["trip_id"]
    client.portal.call(recorder.flush)  # the live summary comes from memory, so write the queue out first
    row = client.portal.call(recorder.repo.trip, trip_id)
    assert row["emergency_contact"] == CONTACT and row["user_id"] == ana["user"]["user_id"]


def test_report_has_everything_for_one_drive(client, clock, jpeg_frames):
    ana = register(client, "ana")
    trip_id = start_trip(client, headers=bearer(ana))["trip_id"]
    ts = DAY
    for i in range(16):  # 8 s: 2 s clean, 3 s phone (model frame), 3 s clean; video at every tick
        ts += timedelta(seconds=0.5)
        clock.advance(0.5)
        client.post(f"{API}/video/frames", content=jpeg_frames[i % len(jpeg_frames)], headers={"Content-Type": "image/jpeg"})
        send_tick(client, ts, 50, frame=MODEL_FRAME if 4 <= i < 10 else None)
    end_trip(client, trip_id)

    report = client.get(f"{API}/trips/{trip_id}/report", headers=bearer(ana)).json()
    assert report["user"]["username"] == "ana"
    assert report["trip"]["trip_id"] == trip_id and report["trip"]["status"] == "ended"
    assert report["window_s"] == 1.0
    samples = report["samples"]
    assert len(samples) == 8 and [s["t"] for s in samples] == list(range(8))
    assert samples[0]["score"] == 100 and min(s["score_min"] for s in samples) == report["trip"]["min_score"]
    assert any(s["categories"].get("phone_use", {}).get("active") for s in samples)
    [event] = report["events"]
    assert event["behaviors"] == ["eyes_off_road", "looking_at_phone"]
    assert event["thumbnail_url"].endswith(".jpg") and event["video_url"].endswith(".mp4")
    assert client.get(event["thumbnail_url"]).headers["content-type"] == "image/jpeg"

    # The same data as the separate endpoints.
    timeline = client.get(f"{API}/trips/{trip_id}/timeline", headers=bearer(ana)).json()
    assert timeline["samples"] == samples
    assert client.get(f"{API}/trips/{trip_id}/events", headers=bearer(ana)).json() == report["events"]


def test_running_summary_and_restart(tmp_path, clock, speed):
    """The trips row is updated while driving; a crash leaves a usable trip that the next start closes."""
    url = f"sqlite+aiosqlite:///{(tmp_path / 'trips.db').as_posix()}"

    def fresh_process():
        db = Database(url)
        return TripRecorder(RecordingRepository(db), MemoryMediaStore(), clock=clock), db

    recorder, db = fresh_process()
    with app_client(recorder, speed, db) as client:
        ana = register(client, "ana")
        trip_id = start_trip(client, headers=bearer(ana))["trip_id"]
        ts = DAY
        for _ in range(24):  # 12 s of phone use; the running summary is written every 10 s
            ts += timedelta(seconds=0.5)
            clock.advance(0.5)
            send_tick(client, ts, 50, ["looking_at_phone"])
        live = client.get(f"{API}/trips/{trip_id}/summary", headers=bearer(ana)).json()
        assert live["status"] == "active"
        client.portal.call(recorder.flush)
        row = client.portal.call(recorder.repo.trip, trip_id)
        assert row["ended_at"] is None and row["final_score"] < 100  # summary already in Postgres
    # The app stops without ending the trip (a crash or a reload): memory is gone.

    recorder, db = fresh_process()
    with app_client(recorder, speed, db) as client:
        headers = bearer(ana)  # sessions live in the database, so the token still works
        summary = client.get(f"{API}/trips/{trip_id}/summary", headers=headers).json()
        assert summary["status"] == "ended"  # closed at the last summary write
        assert summary["final_score"] < 100 and summary["behaviors"][0]["behavior"] == "looking_at_phone"
        assert [t["trip_id"] for t in client.get(f"{API}/trips", headers=headers).json()] == [trip_id]
        report = client.get(f"{API}/trips/{trip_id}/report", headers=headers).json()
        assert len(report["samples"]) == 12 and report["events"][0]["behaviors"] == ["looking_at_phone"]
