"""Coordinator: 2 s sections, danger, images from the video cache, delivery to the server (and while it's down)."""

from datetime import timedelta

from app.coordinator.services.video_cache import VideoCache
from app.schemas.sync import SyncResult, TripSync
from app.server.repositories.database import Database
from app.server.repositories.media import MemoryMediaStore
from app.server.repositories.recordings import RecordingRepository
from app.server.services.storage import StorageUnavailable, TripStore
from tests.conftest import API, DAY, MODEL_FRAME, app_client, flush, make_coordinator, send_tick, send_video, start_trip

PHONE = ["looking_at_phone"]


class Drive:
    """Ticks every 0.5 s on the camera clock; the coordinator's clock moves along, plus a video frame per tick."""

    def __init__(self, client, clock, video: list[bytes] | None = None) -> None:
        self.client, self.clock, self.video = client, clock, video
        self.ts = DAY
        self.ticks = 0

    def run(self, seconds: float, speed: float = 50, behaviors=(), frame=None) -> dict:
        state = {}
        for _ in range(int(seconds / 0.5)):
            self.ts += timedelta(seconds=0.5)
            self.clock.advance(0.5)
            if self.video:
                send_video(self.client, self.video[self.ticks % len(self.video)])
            self.ticks += 1
            state = send_tick(self.client, self.ts, speed, behaviors, frame)
        return state


def end_trip(client, trip_id: str) -> None:
    assert client.post(f"{API}/trips/{trip_id}/end").status_code == 200


def report(client, trip_id: str) -> dict:
    res = client.get(f"{API}/trips/{trip_id}/report")
    assert res.status_code == 200, res.text
    return res.json()


def test_sections_fold_two_seconds_of_ticks(client, clock):
    trip_id = start_trip(client)["trip_id"]
    drive = Drive(client, clock)
    drive.run(2)  # clean
    drive.run(2, frame=MODEL_FRAME)  # the model sees phone use and raises a red alert
    drive.run(2, behaviors=PHONE)  # labels only (simulator)
    end_trip(client, trip_id)

    sections = report(client, trip_id)["sections"]
    assert [(s["seq"], s["t_start"], s["t_end"]) for s in sections] == [(0, 0, 2), (1, 2, 4), (2, 4, 6)]
    assert [s["ticks"] for s in sections] == [4, 4, 4]  # the very first tick is t = 0
    clean, model, labels = sections
    assert clean["danger"] == "none" and clean["behaviors"] == {} and clean["risk"] is None
    assert (clean["speed_kmh"], clean["speed_source"]) == (50, "telemetry")
    assert model["danger"] == "critical"  # the model's red alert while moving
    assert model["behaviors"] == {"eyes_off_road": 2.0, "looking_at_phone": 2.0}
    assert (model["alert"], model["risk"], model["risk_max"]) == ("red", 0.819, 0.819)
    assert model["rules_triggered"] == ["long_distraction", "phone_sustained"]
    assert model["categories"]["phone_use"] == {"p": 0.715, "p_max": 0.715, "active": True, "r": 0.534, "run_s": 3.2}
    assert model["vibrate_seat"] is True and model["sound"] == "high"
    assert labels["danger"] in ("dangerous", "critical") and labels["alert"] is None
    assert labels["score_start"] == model["score_end"]  # sections chain up
    assert model["has_image"] is False  # no video was streamed


def test_standing_still_is_never_dangerous(client, clock):
    trip_id = start_trip(client)["trip_id"]
    Drive(client, clock).run(4, speed=0, behaviors=PHONE, frame=MODEL_FRAME)
    end_trip(client, trip_id)
    data = report(client, trip_id)
    assert {s["danger"] for s in data["sections"]} == {"none"} and data["moments"] == []


def test_dangerous_sections_carry_the_riskiest_frame(client, clock, jpeg_frames):
    trip_id = start_trip(client)["trip_id"]
    drive = Drive(client, clock, jpeg_frames)
    drive.run(2)
    drive.run(4, behaviors=PHONE)  # dangerous: phone while moving
    drive.run(2)  # one quiet section: still the same moment
    drive.run(2, behaviors=PHONE)
    drive.run(6)  # long enough to end the moment
    drive.run(2, behaviors=["drowsy"])
    end_trip(client, trip_id)

    data = report(client, trip_id)
    sections = data["sections"]
    risky = [s for s in sections if s["danger"] != "none"]
    assert risky and all(s["has_image"] and s["image_url"] for s in risky)
    assert all(not s["has_image"] for s in sections if s["danger"] == "none")
    assert all(s["t_start"] <= s["image_t"] <= s["t_end"] for s in risky)
    first, second = data["moments"]
    assert list(first["behaviors"]) == ["looking_at_phone"] and first["behaviors"]["looking_at_phone"] >= 5
    assert first["t_start"] == 2 and first["t_end"] == 10  # the quiet section in the middle is bridged
    assert list(second["behaviors"]) == ["drowsy"]
    for moment in data["moments"]:
        assert moment["image_url"] and moment["t_start"] <= moment["peak_t"] <= moment["t_end"]
        assert client.get(moment["image_url"]).headers["content-type"] == "image/jpeg"


def test_live_section_messages(client, clock):
    with client.websocket_connect(f"{API}/ws") as ws:
        trip_id = start_trip(client)["trip_id"]
        Drive(client, clock).run(4, behaviors=PHONE)
        end_trip(client, trip_id)
        messages = []
        while not messages or messages[-1]["type"] != "trip_ended":
            messages.append(ws.receive_json())
    sections = [m["data"] for m in messages if m["type"] == "section"]
    assert [s["seq"] for s in sections] == [0, 1]  # ticks at t = 0..3.5 s; the last one closes with the trip
    assert all(s["trip_id"] == trip_id and s["image_url"] is None for s in sections)
    assert sections[1]["danger"] == "dangerous" and sections[1]["behaviors"] == {"looking_at_phone": 2.0}


def test_ticks_stopping_closes_the_section(client, clock, coordinator):
    trip_id = start_trip(client)["trip_id"]
    Drive(client, clock).run(1, behaviors=PHONE)
    clock.advance(5)  # the camera side stops; the trip stays open
    client.portal.call(coordinator.housekeeping_once)
    flush(client, coordinator)
    sections = client.get(f"{API}/trips/{trip_id}/sections").json()
    assert [s["seq"] for s in sections] == [0]


class FlakyStore(TripStore):
    """Postgres is 'down' while `down` is True."""

    down = True

    async def sync(self, trip_id: str, body: TripSync) -> SyncResult:
        if self.down:
            raise StorageUnavailable("Postgres is unreachable (test)")
        return await super().sync(trip_id, body)


def test_server_down_never_blocks_the_drive(db, clock, speed):
    store = FlakyStore(RecordingRepository(db), MemoryMediaStore())
    coordinator = make_coordinator(clock, speed)
    with app_client(store, coordinator, db) as client:
        trip_id = start_trip(client)["trip_id"]
        state = Drive(client, clock).run(6, behaviors=PHONE)
        assert state["score"] < 100  # the live score works
        assert not client.portal.call(coordinator.outbox.flush, 0.3)  # nothing can be delivered
        assert coordinator.outbox.pending_sections == 2 and not coordinator.outbox.server_ok
        assert client.get(f"{API}/trips/{trip_id}/summary").status_code == 404  # the server never heard of it
        assert client.get(f"{API}/coordinator/status").json()["server"]["reachable"] is False

        store.down = False  # Postgres is back: the queue goes out
        end_trip(client, trip_id)
        flush(client, coordinator)
        data = report(client, trip_id)
        assert [s["seq"] for s in data["sections"]] == [0, 1, 2]  # 2 queued + the one closed by "End"
        assert data["trip"]["status"] == "ended" and coordinator.outbox.server_ok


def test_recording_off_keeps_the_live_path(clock, speed, db):
    coordinator = make_coordinator(clock, speed)
    with app_client(TripStore(repo=None, media=None), coordinator, db) as client:
        trip_id = start_trip(client)["trip_id"]
        assert Drive(client, clock).run(3, behaviors=PHONE)["score"] < 100
        assert client.get(f"{API}/trips/{trip_id}/report").status_code == 503
        assert client.get(f"{API}/trips").status_code == 503
        assert client.post(f"{API}/trips/{trip_id}/end").json()["status"] == "ended"  # from the coordinator


def test_dead_database(tmp_path, clock, speed):
    """Postgres that doesn't answer at all: 503 on reads, the drive goes on."""
    db = Database("postgresql+asyncpg://safety:safety@127.0.0.1:1/safety")  # nothing listens on port 1
    store = TripStore(RecordingRepository(db), MemoryMediaStore())
    coordinator = make_coordinator(clock, speed)
    with app_client(store, coordinator, db) as client:
        trip_id = start_trip(client)["trip_id"]
        assert Drive(client, clock).run(3, behaviors=PHONE)["level"] in ("safe", "caution", "warning")
        assert client.get(f"{API}/trips/{trip_id}/report").status_code == 503


def test_internal_routes_need_the_token(client):
    body = {"keep": []}
    assert client.post(f"{API}/internal/trips/close-interrupted", json=body).status_code == 403
    wrong = {"X-Internal-Token": "guess"}
    assert client.post(f"{API}/internal/trips/close-interrupted", json=body, headers=wrong).status_code == 403
    right = {"X-Internal-Token": "dev-internal-token"}
    assert client.post(f"{API}/internal/trips/close-interrupted", json=body, headers=right).json() == {"closed": 0}


def test_video_frame_validation(client, jpeg_frames):
    def post(content, content_type="image/jpeg"):
        return client.post(f"{API}/video/frames", content=content, headers={"Content-Type": content_type})

    assert post(jpeg_frames[0]).status_code == 409  # no trip yet
    start_trip(client)
    assert post(jpeg_frames[0]).status_code == 204
    assert post(b"not a jpeg").status_code == 422
    assert post(jpeg_frames[0], "image/png").status_code == 415
    assert post(b"\xff\xd8\xff" + b"0" * 2_000_001).status_code == 413


def test_video_cache_keeps_five_minutes_at_most(clock):
    cache = VideoCache(mode="memory", retention_s=300, max_fps=10, clock=clock)
    cache.open()
    first = cache.new_frame_id()
    cache.add(first, clock(), b"\xff\xd8\xff first")
    for _ in range(3100):  # 310 s at 10 fps
        clock.advance(0.1)
        if cache.wants(clock()):
            cache.add(cache.new_frame_id(), clock(), b"\xff\xd8\xff frame")
    stats = cache.stats()
    assert cache.get(first) is None and stats["seconds"] <= 300 and 2900 <= stats["frames"] <= 3001
    frame_id, wall = cache.nearest(clock() - 0.04, max_gap_s=1)
    assert cache.get(frame_id) == b"\xff\xd8\xff frame" and abs(wall - clock()) < 0.15
    assert cache.nearest(clock() + 30, max_gap_s=1) is None
    assert len(cache.frames_between(clock() - 1.05, clock())) == 11
    cache.close()


def test_video_cache_on_disk(tmp_path, clock):
    cache = VideoCache(mode="disk", path=tmp_path / "cache", retention_s=300, max_fps=10, clock=clock)
    cache.open()
    assert cache.mode == "disk"
    ids = []
    for i in range(5):
        clock.advance(0.2)
        ids.append(cache.new_frame_id())
        cache.add(ids[-1], clock(), b"\xff\xd8\xff" + bytes([i]) * 1000)
    assert cache.get(ids[2]) == b"\xff\xd8\xff" + bytes([2]) * 1000
    cache.close()
