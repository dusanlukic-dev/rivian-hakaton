"""Coordinator -> server: the internal contract (`/internal/*`, header `X-Internal-Token`).

One call, `POST /internal/trips/{trip_id}/sync`, carries everything new about a trip: who and when (every
time; the server ignores what it already has), new sections with their images, and the running summary.
It is idempotent, so the coordinator can simply resend a batch after a timeout or while the server is down.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import Behavior, SafetyLevel
from app.schemas.report import SectionIn
from app.schemas.trip import EmergencyContactIn


class TripMeta(BaseModel):
    trip_id: str
    driver_id: str
    user_id: str | None = Field(description="The account that started it; null = started without login.")
    started_at: datetime
    emergency_contact: EmergencyContactIn | None = None
    speed_scenario: str | None = None
    section_s: float


class BehaviorTotal(BaseModel):
    behavior: Behavior
    occurrences: int
    total_seconds: float


class RunningSummary(BaseModel):
    """The trip's TripSummary numbers so far; `ended_at` is set once the trip is over."""

    duration_s: float
    final_score: float
    average_score: float
    min_score: float
    level: SafetyLevel
    emergency_alert_sent: bool
    behaviors: list[BehaviorTotal]
    ended_at: datetime | None = None


class TripSync(BaseModel):
    trip: TripMeta
    sections: list[SectionIn] = Field(default_factory=list)
    summary: RunningSummary | None = None


class SyncResult(BaseModel):
    sections: int = Field(description="Sections in the request (already stored ones are skipped).")
    images: int = Field(description="Images stored in S3.")


class CloseInterruptedIn(BaseModel):
    keep: list[str] = Field(default_factory=list, description="Trips the coordinator is still driving.")


class CloseInterruptedOut(BaseModel):
    closed: int
