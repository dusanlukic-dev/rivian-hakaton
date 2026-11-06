from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Personal Safety Reviewer API"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["*"]

    # --- Trip recording: Postgres (samples, risky moments) + S3-compatible storage (clips) ---
    # Best effort: if either one is down, the live score and the car's reactions keep working.
    recording_enabled: bool = True
    # Port 5433: scripts/services.ps1 and docker-compose.yml use it, since 5432 is often taken.
    database_url: str = "postgresql+asyncpg://safety:safety@127.0.0.1:5433/safety"
    s3_endpoint_url: str = "http://127.0.0.1:9000"  # RustFS locally; AWS S3 / R2 / MinIO work the same
    s3_access_key: str = "safety"
    s3_secret_key: str = "safety-secret"
    s3_bucket: str = "safety-media"
    s3_region: str = "us-east-1"
    # Demo only: anyone can read the bucket. Production access (a separate report server,
    # signed URLs) is still to be designed.
    s3_public_read: bool = True

    # --- Speed (the camera doesn't know it) ---
    # Mocked drive: a scenario name from app/services/speed.py, or "random" (picked per trip).
    speed_scenario: str = "random"
    # The phone's GPS through POST /speed. Off by default; when on, a fresh reading beats the mock.
    phone_speed_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
