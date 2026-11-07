import tempfile
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """All settings of both parts. Every value can be set in `backend/.env` (example: `.env.example`).

    The backend has two parts (docs/ARCHITECTURE.md): the **coordinator** (in the car: phone socket, camera,
    model link, scoring, video cache, 2 s section summaries) and the **server** (accounts, trips, sections,
    images, history and reports). `python run.py` runs both in one process; they still only talk over HTTP.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Personal Safety Reviewer API"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["*"]

    # ---------------- Coordinator ----------------
    # Where the coordinator posts its summaries. Empty = the server part runs in this same process (the demo).
    # Split deployment: the server's API base, e.g. http://10.0.0.5:8001/api/v1
    server_url: str = ""
    # Shared secret on /internal/* (coordinator -> server). Change it whenever the server is reachable by others.
    internal_token: str = "dev-internal-token"
    # Seconds of driving per section summary: one chart point, one WS `section` message, one database row.
    section_s: float = 2.0
    # Model detections arrive 5-10 per second; the phone gets `state` about this often (and at once on a change).
    live_state_interval_s: float = 0.5
    # Thresholds of the coordinator's risk engine. Empty = <repo>/notebooks/risk_config.json
    risk_config_path: str = ""
    # Camera frames kept for pulling the image of a dangerous moment: "disk" (diskcache) or "memory".
    video_cache: str = "disk"
    video_cache_dir: str = ""  # empty = <temp>/safety-reviewer/video-cache (cleared on every start)
    video_cache_s: float = 300.0  # 5 minutes
    video_cache_fps: float = 10.0  # frames stored per second at most (the camera may send 30)
    video_cache_max_mb: int = 1024
    section_image_width: int = 960  # dangerous-moment images are scaled down to this width (JPEG)

    # ---------------- Server ----------------
    # Accounts, trips, sections (Postgres) and images (S3-compatible: RustFS locally). If the database is
    # down, the coordinator keeps its summaries in memory and delivers them once the server answers again.
    recording_enabled: bool = True
    # Port 5433: scripts/services.ps1 and docker-compose.yml use it, since 5432 is often taken.
    database_url: str = "postgresql+asyncpg://safety:safety@127.0.0.1:5433/safety"
    s3_endpoint_url: str = "http://127.0.0.1:9000"  # RustFS locally; AWS S3 / R2 / MinIO work the same
    s3_access_key: str = "safety"
    s3_secret_key: str = "safety-secret"
    s3_bucket: str = "safety-media"
    s3_region: str = "us-east-1"
    # Demo only: anyone can read the bucket. Production access (signed URLs) is still to be designed.
    s3_public_read: bool = True

    # ---------------- Speed (coordinator; in a real car it comes from the CAN bus) ----------------
    # Mocked drive: a scenario name from app/coordinator/services/speed.py, or "random" (picked per trip).
    speed_scenario: str = "random"
    # The phone's GPS through POST /speed. Off by default; when on, a fresh reading beats the mock.
    phone_speed_enabled: bool = False

    @property
    def risk_config_file(self) -> Path:
        return Path(self.risk_config_path) if self.risk_config_path else REPO_DIR / "notebooks" / "risk_config.json"

    @property
    def video_cache_path(self) -> Path:
        if self.video_cache_dir:
            return Path(self.video_cache_dir)
        return Path(tempfile.gettempdir()) / "safety-reviewer" / "video-cache"


@lru_cache
def get_settings() -> Settings:
    return Settings()
