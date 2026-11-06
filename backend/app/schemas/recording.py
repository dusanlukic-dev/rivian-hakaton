"""What the backend stores about a trip, for the driver's report (charts, worst moments, clips)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.enums import Behavior, DashboardLight, SafetyLevel, SoundLevel, SpeedSource
from app.schemas.auth import User
from app.schemas.trip import TripSummary

Alert = Literal["green", "yellow", "red"]


class SampleCategory(BaseModel):
    """One camera-model category within a sample window."""

    p: float | None = Field(description="Average probability over the window.")
    p_max: float | None
    active: bool = Field(description="The model marked it active at least once in the window.")
    r: float | None = Field(description="Largest contribution to the model's risk.")
    run_s: float | None = Field(description="Longest uninterrupted run reported by the model (s).")


class TripSample(BaseModel):
    """Everything known about the drive, aggregated over one window (`TripTimeline.window_s`)."""

    t: float = Field(description="Seconds since the trip's first tick (x axis for charts).")
    ts: datetime
    ticks: int = Field(description="Telemetry ticks in this window.")
    speed_kmh: float = Field(description="Average speed in the window.")
    speed_max_kmh: float
    speed_source: SpeedSource
    score: float = Field(description="Score at the end of the window.")
    score_min: float
    level: SafetyLevel = Field(description="Level for `score`.")
    behaviors: list[Behavior] = Field(description="Behaviors seen in the window (scored only while moving).")
    risk: float | None = Field(description="Camera model's average risk 0..1; null without model frames.")
    risk_max: float | None
    alert: Alert | None = Field(description="Worst camera-model alert in the window.")
    rules_triggered: list[str]
    categories: dict[str, SampleCategory] = Field(description="Keys are the model's category names.")
    groups: dict[str, float | None] = Field(description="Largest risk per channel: visual, manual, fatigue.")
    dashboard_light: DashboardLight = Field(description="Most severe light shown in the window.")
    vibrate_seat: bool = Field(description="The seat vibrated at least once in the window.")
    sound: SoundLevel = Field(description="Loudest sound in the window.")
    lat: float | None = Field(description="From the phone's GPS (only with the phone speed source).")
    lon: float | None


class TripTimeline(BaseModel):
    trip_id: str
    window_s: float
    samples: list[TripSample] = Field(description="Oldest first.")


class RiskEvent(BaseModel):
    """One risky moment: moving, and a scored behavior was visible or the model raised a red alert.

    Detections less than a couple of seconds apart are merged into one event.
    """

    event_id: str
    trip_id: str
    started_at: datetime
    ended_at: datetime
    t_start: float = Field(description="Seconds since the trip's first tick (matches `TripSample.t`).")
    duration_s: float = Field(description="Risky seconds, counted like `BehaviorSummary.total_seconds`.")
    behaviors: list[Behavior] = Field(description="Longest first. Empty if only the model's alarm fired.")
    behavior_seconds: dict[Behavior, float]
    categories: dict[str, float] = Field(description="Model categories active during the event -> peak p.")
    rules_triggered: list[str]
    alert: Alert | None = Field(description="Worst camera-model alert during the event.")
    peak_risk: float | None = Field(description="Highest camera-model risk 0..1.")
    score_start: float = Field(description="Score just before the event.")
    score_end: float
    score_min: float
    score_drop: float = Field(description="score_start - score_min: how much this moment cost.")
    level: SafetyLevel = Field(description="Worst level reached (level of score_min).")
    speed_avg_kmh: float
    speed_max_kmh: float
    lat: float | None
    lon: float | None
    video_url: str | None = Field(description="MP4 clip around the moment (H.264); null if no video was streamed.")
    thumbnail_url: str | None = Field(description="JPEG of the riskiest frame.")
    clip_duration_s: float | None


class TripReport(BaseModel):
    """Everything about one drive in one response, for the summary screen and the charts.

    `samples` is the raw recording of the drive, one row per second, oldest first. The app builds its own
    charts from it (score, speed, the model's risk, per-category probabilities...).
    """

    trip: TripSummary
    user: User | None = Field(description="The driver's account; null if the trip was started without login.")
    window_s: float = Field(description="Seconds per sample.")
    samples: list[TripSample]
    events: list[RiskEvent] = Field(description="Risky moments with their images and clips, oldest first.")
