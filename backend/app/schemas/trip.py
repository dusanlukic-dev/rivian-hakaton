from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import Behavior, SafetyLevel, TripStatus
from app.domain.trip import CarResponse


class EmergencyContactIn(BaseModel):
    name: str
    phone: str


class TripCreate(BaseModel):
    driver_id: str
    emergency_contact: EmergencyContactIn | None = None


class TelemetryTick(BaseModel):
    """One sample from the car, sent roughly every second. Only labels - never images."""

    timestamp: datetime = Field(
        description="Local time with UTC offset, e.g. 2026-11-06T22:15:00+01:00 (used for night penalties)."
    )
    speed_kmh: float = Field(ge=0)
    behaviors: set[Behavior] = Field(
        default_factory=set, description="Risky behaviors visible in this sample."
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
