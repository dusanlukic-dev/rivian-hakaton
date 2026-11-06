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


class ModelCategoryStats(BaseModel):
    active_s: float = Field(description="Seconds the model marked the category active (moving only).")
    episodes: int = Field(description="Behavior episodes of at least 0.5 s.")
    max_episode_s: float


class ModelEpisode(BaseModel):
    """One behavior episode as the camera model saw it: a category active, short breaks merged."""

    category: str = Field(description="The model's category name (phone_use, eyes_off_road...).")
    t_start: float = Field(description="Seconds since the trip's first tick (matches `TripSample.t`).")
    t_end: float
    duration_s: float
    peak_r: float = Field(description="Largest contribution to the model's risk.")
    peak_p: float = Field(description="Largest raw probability `p` among the frames received (~2/s).")
    open: bool = Field(description="Still going (live trip) or still going when the trip ended.")


class ModelAlertEpisode(BaseModel):
    """From the model's alert leaving green until it is green again."""

    t_start: float
    t_end: float
    duration_s: float
    max_level: Alert
    peak_risk: float
    causes: list[str] = Field(description="Categories that drove the risk, and `rule:<name>` for hard rules.")
    open: bool


class ModelReport(BaseModel):
    """The camera model's own view of the whole drive, built from its frames (standing time not counted).

    Only for display and analysis: the driver's score is `TripSummary`. Null in the report if no model
    frames came (e.g. the simulator sends labels only).
    """

    frames: int = Field(description="Model frames received.")
    duration_s: float = Field(description="Seconds of model frames while moving.")
    stationary_s: float = Field(description="Seconds of model frames while standing (< 5 km/h), not counted.")
    risk_mean: float = Field(description="Time-weighted mean of the model's risk 0..1.")
    risk_rms: float = Field(description="Root mean square of the risk: long risky stretches weigh more.")
    risk_p95: float
    risk_max: float
    model_score: float = Field(description="100 * (1 - risk_rms): the model's own 0..100 grade of the drive.")
    time_in_alert_s: dict[Alert, float]
    time_in_alert_frac: dict[Alert, float]
    alerts: dict[str, int] = Field(description="Times the alert rose to yellow / to red.")
    alerts_per_hour: dict[str, float]
    rules: dict[str, int] = Field(description="Hard rule -> times it fired (microsleep, long_distraction...).")
    categories: dict[str, ModelCategoryStats] = Field(description="Keys are the model's category names.")
    episodes: list[ModelEpisode] = Field(description="Oldest first, at most 200.")
    alert_episodes: list[ModelAlertEpisode] = Field(description="Oldest first, at most 200.")


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
    model: ModelReport | None = Field(
        default=None, description="The camera model's own trip report; null if no model frames came."
    )
