import subprocess
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import imageio_ffmpeg
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.database import Database, get_database
from app.repositories.media import MemoryMediaStore
from app.repositories.recordings import RecordingRepository
from app.repositories.trips import InMemoryTripRepository, get_trip_repository
from app.repositories.users import UserRepository
from app.services.auth import AuthService, get_auth_service
from app.services.live import LiveHub, get_live_hub
from app.services.recording import RecordingConfig, TripRecorder, get_recorder
from app.services.speed import SpeedService, get_speed_service

API = "/api/v1"
NIGHT = datetime(2026, 11, 6, 23, 0, 0, tzinfo=timezone(timedelta(hours=1)))
DAY = datetime(2026, 11, 6, 14, 0, 0, tzinfo=timezone(timedelta(hours=1)))
CONTACT = {"name": "Ana", "phone": "+381600000000"}

# A record from the camera model's frames.jsonl, as the CV team writes it.
MODEL_FRAME = {
    "t": 38.6,
    "frame": 1158,
    "dt": 0.033,
    "categories": {
        "phone_use": {"p": 0.715, "p_hat": 0.7, "active": True, "run_s": 3.2, "D_s": 3.5, "h": 1.2, "r": 0.534},
        "eyes_off_road": {"p": 0.905, "active": True, "run_s": 3.4, "r": 0.767},
        "drowsiness": {"p": 0.05, "active": False, "run_s": 0.0, "r": 0.0},
    },
    "groups": {"visual": 0.767, "manual": 0.374, "fatigue": 0.0},
    "risk": {"raw": 0.854, "smoothed": 0.84, "floor": 0.5, "final": 0.819},
    "rules_triggered": ["long_distraction", "phone_sustained"],
    "alert": {"level": "red", "code": 2},
    "top_contributors": [["eyes_off_road", 0.767], ["phone_use", 0.534]],
    "perception": {"head": {"yaw": -31.2, "pitch": -18.0}, "eyes": {"ear": 0.21}, "objects": ["cell phone"]},
}


class FakeClock:
    """Stands in for time.monotonic, so tests decide when video frames and ticks 'arrive'."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def media():
    return MemoryMediaStore()


@pytest.fixture
def db():
    # In-memory SQLite stands in for Postgres; same tables, same queries.
    return Database("sqlite+aiosqlite://")


@pytest.fixture
def recorder(db, media, clock):
    return TripRecorder(RecordingRepository(db), media, RecordingConfig(), clock=clock)


@pytest.fixture
def speed(clock):
    return SpeedService(scenario="city", clock=clock)


@contextmanager
def app_client(recorder: TripRecorder, speed: SpeedService, db: Database):
    """A fresh app process: empty in-memory trips, the given database (closed when the app stops)."""
    repo, hub, auth = InMemoryTripRepository(), LiveHub(), AuthService(UserRepository(db))
    app.dependency_overrides.update({
        get_trip_repository: lambda: repo,
        get_live_hub: lambda: hub,
        get_recorder: lambda: recorder,
        get_speed_service: lambda: speed,
        get_database: lambda: db,
        get_auth_service: lambda: auth,
    })
    try:
        # Context manager = one event loop shared by HTTP calls, WebSocket sessions and the recorder.
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client(recorder, speed, db):
    with app_client(recorder, speed, db) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def jpeg_frames(tmp_path_factory) -> list[bytes]:
    """Twenty real JPEGs (ffmpeg test pattern) to stream as camera video."""
    out = tmp_path_factory.mktemp("frames")
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10", "-frames:v", "20",
            str(out / "f%03d.jpg"),
        ],
        check=True,
        capture_output=True,
    )
    return [path.read_bytes() for path in sorted(out.glob("*.jpg"))]


def start_trip(client, headers=None, **body):
    res = client.post(f"{API}/trips", json={"driver_id": "driver-1", **body}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def register(client, username="ana", password="secret-123", **extra) -> dict:
    """New account; returns the AuthOut body (token + user)."""
    res = client.post(f"{API}/auth/register", json={"username": username, "password": password, **extra})
    assert res.status_code == 201, res.text
    return res.json()


def bearer(auth: dict | str) -> dict:
    token = auth if isinstance(auth, str) else auth["token"]
    return {"Authorization": f"Bearer {token}"}


def send_tick(client, ts, speed=None, behaviors=(), frame=None):
    body = {"timestamp": ts.isoformat(), "behaviors": list(behaviors)}
    if speed is not None:
        body["speed_kmh"] = speed
    if frame is not None:
        body["frame"] = frame
    res = client.post(f"{API}/telemetry", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def send_video(client, jpeg: bytes):
    res = client.post(f"{API}/video/frames", content=jpeg, headers={"Content-Type": "image/jpeg"})
    assert res.status_code == 204, res.text
