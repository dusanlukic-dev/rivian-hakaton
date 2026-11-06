"""Accounts (register, login, tokens), trips owned by an account, history and the per-trip report."""

from datetime import timedelta

from app.coordinator.services import server_client
from app.coordinator.services.trips import UNVERIFIED_DRIVER
from app.main import app
from app.server.repositories.database import Database
from app.server.repositories.media import MemoryMediaStore
from app.server.repositories.recordings import RecordingRepository
from app.server.repositories.users import UserRepository
from app.server.services.auth import AuthService, AuthUnavailable, get_auth_service, hash_password, verify_password
from app.server.services.storage import TripStore
from tests.conftest import (
    API, CONTACT, DAY, MODEL_FRAME, app_client, bearer, flush, make_coordinator, register, send_tick, send_video,
    start_trip,
)


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
        assert client.get(f"{API}/trips/{trip_id}/sections", headers=headers).status_code == 404


def test_trip_without_login_still_needs_a_driver_id(client):
    res = client.post(f"{API}/trips", json={})
    assert res.status_code == 422 and "driver_id" in res.json()["detail"]
    trip_id = start_trip(client)["trip_id"]  # anonymous trips stay readable by anyone
    assert client.get(f"{API}/trips/{trip_id}/summary").status_code == 200
    assert [t["driver_id"] for t in client.get(f"{API}/trips", params={"driver_id": "driver-1"}).json()] == ["driver-1"]


def test_saved_emergency_contact_is_used(client, store, coordinator):
    ana = register(client, "ana", emergency_contact=CONTACT)
    trip_id = start_trip(client, headers=bearer(ana))["trip_id"]
    flush(client, coordinator)  # the coordinator delivers the trip to the server in the background
    row = client.portal.call(store.trip, trip_id)
    assert row["emergency_contact"] == CONTACT and row["user_id"] == ana["user"]["user_id"]


def test_report_has_everything_for_one_drive(client, clock, jpeg_frames):
    ana = register(client, "ana")
    trip_id = start_trip(client, headers=bearer(ana))["trip_id"]
    ts = DAY
    for i in range(16):  # 8 s: 2 s clean, 3 s phone (model frame, red alert), 3 s clean; video at every tick
        ts += timedelta(seconds=0.5)
        clock.advance(0.5)
        send_video(client, jpeg_frames[i % len(jpeg_frames)])
        send_tick(client, ts, 50, frame=MODEL_FRAME if 4 <= i < 10 else None)
    end_trip(client, trip_id)

    report = client.get(f"{API}/trips/{trip_id}/report", headers=bearer(ana)).json()
    assert report["user"]["username"] == "ana"
    assert report["trip"]["trip_id"] == trip_id and report["trip"]["status"] == "ended"
    assert report["section_s"] == 2.0
    sections = report["sections"]
    assert [s["seq"] for s in sections] == [0, 1, 2, 3]
    assert [s["danger"] for s in sections] == ["none", "critical", "critical", "none"]
    assert sections[0]["score_start"] == 100 and sections[-1]["score_end"] == report["trip"]["final_score"]
    assert sections[1]["categories"]["phone_use"]["active"] is True and sections[1]["alert"] == "red"
    assert all(s["has_image"] and s["image_url"].endswith(".jpg") for s in sections[1:3])
    assert all(s["image_url"] is None for s in (sections[0], sections[3]))
    [moment] = report["moments"]
    assert moment["danger"] == "critical" and moment["section_ids"] == [sections[1]["section_id"], sections[2]["section_id"]]
    assert list(moment["behaviors"]) == ["eyes_off_road", "looking_at_phone"]
    assert moment["image_url"] in (sections[1]["image_url"], sections[2]["image_url"])
    assert 2.0 <= moment["peak_t"] <= 6.0 and moment["score_drop"] > 0
    image = client.get(moment["image_url"])
    assert image.headers["content-type"] == "image/jpeg" and image.content[:3] == bytes.fromhex("ffd8ff")

    # The same sections as the separate endpoint.
    assert client.get(f"{API}/trips/{trip_id}/sections", headers=bearer(ana)).json() == sections
    later = client.get(f"{API}/trips/{trip_id}/sections", params={"after_seq": 1}, headers=bearer(ana)).json()
    assert [s["seq"] for s in later] == [2, 3]


def test_running_summary_and_restart(tmp_path, clock, speed):
    """The server gets a running summary while driving; a crash leaves a usable trip that the next start closes."""
    url = f"sqlite+aiosqlite:///{(tmp_path / 'trips.db').as_posix()}"

    def fresh_process():
        db = Database(url)
        return TripStore(RecordingRepository(db), MemoryMediaStore()), make_coordinator(clock, speed), db

    store, coordinator, db = fresh_process()
    with app_client(store, coordinator, db) as client:
        ana = register(client, "ana")
        trip_id = start_trip(client, headers=bearer(ana))["trip_id"]
        ts = DAY
        for _ in range(24):  # 12 s of phone use: a section (and the running summary) every 2 s
            ts += timedelta(seconds=0.5)
            clock.advance(0.5)
            send_tick(client, ts, 50, ["looking_at_phone"])
        flush(client, coordinator)
        live = client.get(f"{API}/trips/{trip_id}/summary", headers=bearer(ana)).json()
        assert live["status"] == "active" and live["final_score"] < 100  # running summary, from the server
        row = client.portal.call(store.trip, trip_id)
        assert row["ended_at"] is None
    # The process stops without ending the trip (a crash or a reload): the coordinator's memory is gone.

    store, coordinator, db = fresh_process()
    with app_client(store, coordinator, db) as client:
        flush(client, coordinator)  # the new coordinator asks the server to close what the last one left open
        headers = bearer(ana)  # sessions live in the database, so the token still works
        summary = client.get(f"{API}/trips/{trip_id}/summary", headers=headers).json()
        assert summary["status"] == "ended"  # closed at the last summary write
        assert summary["final_score"] < 100 and summary["behaviors"][0]["behavior"] == "looking_at_phone"
        assert [t["trip_id"] for t in client.get(f"{API}/trips", headers=headers).json()] == [trip_id]
        report = client.get(f"{API}/trips/{trip_id}/report", headers=headers).json()
        assert len(report["sections"]) == 6  # the open section was delivered when the first process stopped
        assert report["moments"][0]["behaviors"] == {"looking_at_phone": 11.5}


class FlakyAuth(AuthService):
    """Accounts whose Postgres is 'down' while `down` is True: token checks fail (503 on /auth/me)."""

    down = False

    async def user_for_token(self, token):
        if self.down:
            raise AuthUnavailable("Postgres is unreachable (test)")
        return await super().user_for_token(token)


def test_the_car_starts_a_trip_while_the_server_cant_check_the_login(db, store, clock, speed, monkeypatch):
    coordinator = make_coordinator(clock, speed)
    auth = FlakyAuth(UserRepository(db))
    with app_client(store, coordinator, db) as client:
        app.dependency_overrides[get_auth_service] = lambda: auth
        ana, bob = register(client, "ana"), register(client, "bob")
        start_trip(client, headers=bearer(ana))  # the coordinator checked ana's token once
        monkeypatch.setattr(server_client, "USER_CACHE_S", 0.0)  # every later check asks the server again
        auth.down = True

        # A token checked before: the last answer is used.
        assert start_trip(client, headers=bearer(ana))["driver_id"] == "ana"
        # A token never checked: the trip starts anyway; the server decides whose it is when it gets the trip.
        res = client.post(f"{API}/trips", json={}, headers=bearer(bob))
        assert res.status_code == 201 and res.json()["driver_id"] == UNVERIFIED_DRIVER
        trip_id = res.json()["trip_id"]
        send_tick(client, DAY, 60, ["looking_at_phone"])
        assert not client.portal.call(coordinator.outbox.flush, 0.3)  # the server can't take it yet
        assert client.post(f"{API}/trips/{trip_id}/end").status_code == 200

        auth.down = False
        flush(client, coordinator)
        summary = client.get(f"{API}/trips/{trip_id}/summary", headers=bearer(bob))
        assert summary.status_code == 200 and summary.json()["driver_id"] == "bob"
        assert client.get(f"{API}/trips/{trip_id}/summary").status_code == 404  # bob's trip, not a public one
