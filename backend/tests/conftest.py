import subprocess
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import imageio_ffmpeg
import pytest
from fastapi.testclient import TestClient

from app.coordinator.repositories.trips import InMemoryTripRepository, get_trip_repository
from app.coordinator.services.coordinator import Coordinator, get_coordinator
from app.coordinator.services.live import LiveHub, get_live_hub
from app.coordinator.services.outbox import ServerOutbox
from app.coordinator.services.risk_engine import load_risk_config
from app.coordinator.services.speed import SpeedService, get_speed_service
from app.coordinator.services.video_cache import VideoCache
from app.core.config import Settings
from app.main import app
from app.server.repositories.database import Database, get_database
from app.server.repositories.media import MemoryMediaStore
from app.server.repositories.recordings import RecordingRepository
from app.server.repositories.users import UserRepository
from app.server.services.auth import AuthService, get_auth_service
from app.server.services.storage import TripStore, get_trip_store

API = "/api/v1"
NIGHT = datetime(2026, 11, 6, 23, 0, 0, tzinfo=timezone(timedelta(hours=1)))
DAY = datetime(2026, 11, 6, 14, 0, 0, tzinfo=timezone(timedelta(hours=1)))
CONTACT = {"name": "Ana", "phone": "+381600000000"}
SETTINGS = Settings(_env_file=None, video_cache="memory", section_s=2.0, server_url="")
RISK_CONFIG = load_risk_config(SETTINGS.risk_config_file)

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
def store(db, media):
    return TripStore(RecordingRepository(db), media)


@pytest.fixture
def speed(clock):
    return SpeedService(scenario="city", clock=clock)


def make_coordinator(clock, speed, settings: Settings = SETTINGS) -> Coordinator:
    return Coordinator(
        InMemoryTripRepository(),
        LiveHub(),
        speed,
        settings,
        clock=clock,
        video=VideoCache(mode="memory", retention_s=300, max_fps=10, clock=clock),
        outbox=ServerOutbox(interval_s=0.05),
        risk_config=RISK_CONFIG,
        housekeeping_s=0,  # tests call coordinator.housekeeping_once() themselves
    )


@pytest.fixture
def coordinator(clock, speed):
    return make_coordinator(clock, speed)


@contextmanager
def app_client(store: TripStore, coordinator: Coordinator, db: Database):
    """A fresh backend process: the given coordinator (empty memory) and server storage (closed when it stops)."""
    auth = AuthService(UserRepository(db))
    app.dependency_overrides.update({
        get_trip_repository: lambda: coordinator.repo,
        get_live_hub: lambda: coordinator.hub,
        get_speed_service: lambda: coordinator.speed,
        get_coordinator: lambda: coordinator,
        get_database: lambda: db,
        get_trip_store: lambda: store,
        get_auth_service: lambda: auth,
    })
    try:
        # Context manager = one event loop shared by HTTP calls, WebSocket sessions and the background tasks.
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client(store, coordinator, db):
    with app_client(store, coordinator, db) as test_client:
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


def send_ticks(client, start, seconds, speed=None, behaviors=(), frame=None, step=0.5):
    """A behavior held for `seconds` (ticks every `step` from `start`), the way a camera reports it: a single tick is
    shorter than any behavior's onset (scoring.Debounce). Returns the last state."""
    state = {}
    for i in range(round(seconds / step) + 1):
        state = send_tick(client, start + timedelta(seconds=i * step), speed, behaviors, frame)
    return state


def send_video(client, jpeg: bytes):
    res = client.post(f"{API}/video/frames", content=jpeg, headers={"Content-Type": "image/jpeg"})
    assert res.status_code == 204, res.text


def flush(client, coordinator: Coordinator, timeout: float = 5.0) -> None:
    """Wait until the coordinator delivered everything to the server (sections, summary)."""
    assert client.portal.call(coordinator.outbox.flush, timeout), "outbox didn't drain"
