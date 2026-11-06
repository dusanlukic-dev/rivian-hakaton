"""Trip recording: aggregated samples, risky moments and their clips (SQLite + in-memory S3 here)."""

from datetime import timedelta

from app.repositories.database import Database
from app.repositories.media import MemoryMediaStore
from app.repositories.recordings import RecordingRepository
from app.services.recording import TripRecorder
from tests.conftest import API, DAY, MODEL_FRAME, app_client, send_tick, send_video, start_trip

PHONE = ["looking_at_phone"]


class Drive:
    """Ticks every 0.5 s on the camera clock; the recorder's clock moves along, plus one video frame per tick."""

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


def test_samples_aggregate_ticks_per_second(client, clock, recorder):
    trip_id = start_trip(client)["trip_id"]
    drive = Drive(client, clock)
    drive.run(2)  # clean
    drive.run(2, frame=MODEL_FRAME)  # the model sees phone use and raises a red alert
    end_trip(client, trip_id)

    timeline = client.get(f"{API}/trips/{trip_id}/timeline").json()
    samples = timeline["samples"]
    assert timeline["window_s"] == 1.0
    assert [s["t"] for s in samples] == [0, 1, 2, 3]
    assert all(s["ticks"] == 2 for s in samples)

    clean, risky = samples[0], samples[-1]
    assert (clean["speed_kmh"], clean["speed_source"]) == (50, "telemetry")
    assert clean["behaviors"] == [] and clean["risk"] is None and clean["categories"] == {}
    assert risky["behaviors"] == ["eyes_off_road", "looking_at_phone"]
    assert (risky["alert"], risky["risk"], risky["risk_max"]) == ("red", 0.819, 0.819)
    assert risky["rules_triggered"] == ["long_distraction", "phone_sustained"]
    assert risky["categories"]["phone_use"] == {"p": 0.715, "p_max": 0.715, "active": True, "r": 0.534, "run_s": 3.2}
    assert risky["categories"]["drowsiness"]["active"] is False
    assert risky["groups"] == {"fatigue": 0.0, "manual": 0.374, "visual": 0.767}
    assert risky["vibrate_seat"] is True and risky["sound"] == "high"
    assert risky["score"] < clean["score"] == 100

    trip = client.portal.call(recorder.repo.trip, trip_id)
    assert trip["ended_at"] is not None and trip["final_score"] == round(risky["score"], 1)
    assert trip["behaviors"][0]["behavior"] in ("looking_at_phone", "eyes_off_road")
    assert trip["speed_scenario"] == "city"


def test_risky_moment_is_stored_with_a_clip(client, clock, media, jpeg_frames):
    trip_id = start_trip(client)["trip_id"]
    drive = Drive(client, clock, video=jpeg_frames)
    drive.run(4)  # clean: the clip's pre-roll comes from here
    drive.run(3, behaviors=PHONE)  # 3 s looking at the phone
    drive.run(3)  # quiet for 2 s closes the moment

    events = client.get(f"{API}/trips/{trip_id}/events").json()  # works while the trip is still active
    assert len(events) == 1
    event = events[0]
    assert event["behaviors"] == ["looking_at_phone"]
    assert event["behavior_seconds"] == {"looking_at_phone": 3.0}
    assert (event["t_start"], event["duration_s"]) == (4.0, 3.0)
    assert event["score_start"] == 100 and event["score_drop"] > 0
    assert event["speed_avg_kmh"] == 50

    # 3 s before + 3 s during + 2 s after, one frame per 0.5 s.
    assert event["clip_duration_s"] == 8.0
    key = f"clips/{trip_id}/{event['event_id']}"
    assert set(media.objects) == {f"{key}.mp4", f"{key}.jpg"}
    assert event["video_url"] == f"http://testserver{API}/media/{key}.mp4"

    video = client.get(event["video_url"])
    assert video.status_code == 200 and video.headers["content-type"] == "video/mp4"
    assert video.content[4:8] == b"ftyp"  # an MP4 container
    part = client.get(event["video_url"], headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100
    assert part.headers["content-range"] == f"bytes 0-99/{len(video.content)}"
    thumbnail = client.get(event["thumbnail_url"])
    assert thumbnail.headers["content-type"] == "image/jpeg" and thumbnail.content in jpeg_frames


def test_flicker_is_one_moment_and_standing_still_is_not_risky(client, clock):
    trip_id = start_trip(client)["trip_id"]
    drive = Drive(client, clock)
    drive.run(1)
    drive.run(1, behaviors=PHONE)  # a glance...
    drive.run(1)  # ...1 s apart is still the same moment (merge gap 2 s)
    drive.run(1, behaviors=PHONE)
    drive.run(3)
    drive.run(5, speed=0, behaviors=PHONE)  # at a red light: no penalty, so not a risky moment
    end_trip(client, trip_id)

    events = client.get(f"{API}/trips/{trip_id}/events").json()
    assert len(events) == 1
    assert events[0]["duration_s"] == 2.0
    assert events[0]["video_url"] is None and events[0]["thumbnail_url"] is None  # no video was streamed


def test_long_moments_are_split(client, clock, recorder):
    recorder.cfg.event_max_s = 2.0
    trip_id = start_trip(client)["trip_id"]
    drive = Drive(client, clock)
    drive.run(1)
    drive.run(5, behaviors=PHONE)
    end_trip(client, trip_id)

    events = client.get(f"{API}/trips/{trip_id}/events").json()
    assert [e["duration_s"] for e in events] == [2.0, 2.0, 1.0]
    worst_first = client.get(f"{API}/trips/{trip_id}/events", params={"order": "worst"}).json()
    drops = [e["score_drop"] for e in worst_first]
    assert drops == sorted(drops, reverse=True)


def test_video_frame_validation(client, jpeg_frames):
    def post(content, content_type="image/jpeg"):
        return client.post(f"{API}/video/frames", content=content, headers={"Content-Type": content_type})

    assert post(jpeg_frames[0]).status_code == 409  # no trip yet
    start_trip(client)
    assert post(jpeg_frames[0]).status_code == 204
    assert post(b"not a jpeg").status_code == 422
    assert post(jpeg_frames[0], "image/png").status_code == 415


def test_unknown_trip_and_media(client):
    assert client.get(f"{API}/trips/nope/timeline").status_code == 404
    assert client.get(f"{API}/trips/nope/events").status_code == 404
    assert client.get(f"{API}/media/clips/nope/nope.mp4").status_code == 404


def test_dead_database_never_blocks_the_drive(tmp_path, clock, speed):
    dead = Database(f"sqlite+aiosqlite:///{(tmp_path / 'missing' / 'trips.db').as_posix()}")
    recorder = TripRecorder(RecordingRepository(dead), MemoryMediaStore(), clock=clock)
    with app_client(recorder, speed, dead) as client:
        trip_id = start_trip(client)["trip_id"]
        assert send_tick(client, DAY, 60, PHONE)["score"] < 100  # the live score doesn't care
        end_trip(client, trip_id)
        res = client.get(f"{API}/trips/{trip_id}/timeline")
        assert res.status_code == 503 and "unreachable" in res.json()["detail"]
        assert recorder._pending  # kept for when the database is back


def test_recording_off(clock, speed, db):
    with app_client(TripRecorder(None, None), speed, db) as client:
        trip_id = start_trip(client)["trip_id"]
        assert send_tick(client, DAY, 60, PHONE)["score"] < 100
        assert client.get(f"{API}/trips/{trip_id}/events").status_code == 503
        assert client.get(f"{API}/media/clips/x.mp4").status_code == 503
