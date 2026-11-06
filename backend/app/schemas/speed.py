from pydantic import BaseModel, Field

from app.domain.enums import SpeedSource


class PhoneSpeedIn(BaseModel):
    """One GPS reading from the phone. Send ~1/s while driving, only if `phone_enabled` (GET /speed)."""

    speed_kmh: float = Field(ge=0, description="GPS speed in km/h (Android gives m/s: multiply by 3.6).")
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


class SpeedStatus(BaseModel):
    source: SpeedSource | None = Field(
        description="Source used for the latest tick of the active trip; null without an active trip or ticks."
    )
    speed_kmh: float | None = Field(description="Speed used for the latest tick of the active trip.")
    scenario: str = Field(description="Mock drive of the active trip, or the configured SPEED_SCENARIO.")
    scenarios: list[str] = Field(description="Available mock drives (values for SPEED_SCENARIO).")
    phone_enabled: bool = Field(description="True when the backend accepts and prefers the phone's GPS speed.")
    phone_age_s: float | None = Field(description="Seconds since the last phone reading; null if none yet.")
