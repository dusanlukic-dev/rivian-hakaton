from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import Behavior, SafetyLevel, SpeedSource, TripStatus
from app.domain.trip import CameraView, CarResponse
from app.schemas.camera import ModelFrame


class EmergencyContactIn(BaseModel):
    name: str
    phone: str


class TripCreate(BaseModel):
    driver_id: str | None = Field(
        default=None,
        description="Required without login. With a login token the account's username is used instead.",
    )
    emergency_contact: EmergencyContactIn | None = Field(
        default=None, description="Without it, a logged-in driver's saved contact is used."
    )


class TelemetryTick(BaseModel):
    """One sample from the camera side, ~2/s. Labels and model numbers only: video goes to POST /video/frames."""

    timestamp: datetime = Field(
        description="Local time with UTC offset, e.g. 2026-11-06T22:15:00+01:00 (used for night penalties)."
    )
    speed_kmh: float | None = Field(
        default=None,
        ge=0,
        description="Leave it out: the backend provides the speed (mock drive, or the phone's GPS). "
        "The simulator and tests send it to force a value.",
    )
    behaviors: set[Behavior] = Field(
        default_factory=set, description="Risky behaviors visible in this sample."
    )
    frame: ModelFrame | None = Field(
        default=None,
        description="One record of the camera model's frames.jsonl, sent unchanged. Its active "
        "categories are added to `behaviors`; risk, alert and categories are forwarded to the app.",
    )


class TripState(BaseModel):
    trip_id: str
    driver_id: str
    status: TripStatus
    score: float
    level: SafetyLevel
    active_behaviors: dict[Behavior, float] = Field(
        description="Currently visible behaviors and how many seconds each has lasted."
    )
    response: CarResponse
    camera: CameraView | None = Field(
        default=None,
        description="The camera model's own view from the latest tick; null if it sent no model frame.",
    )
    speed_kmh: float = Field(description="Speed used for the latest tick (0 before the first tick).")
    speed_source: SpeedSource | None = Field(description="Where that speed came from; null before the first tick.")
    emergency_alert_sent: bool


class BehaviorSummary(BaseModel):
    behavior: Behavior
    occurrences: int
    total_seconds: float
    tip: str


class TripSummary(BaseModel):
    trip_id: str
    driver_id: str
    status: TripStatus
    started_at: datetime
    ended_at: datetime | None
    duration_s: float
    final_score: float
    average_score: float
    min_score: float
    level: SafetyLevel
    emergency_alert_sent: bool
    behaviors: list[BehaviorSummary] = Field(description="Worst behaviors first.")
