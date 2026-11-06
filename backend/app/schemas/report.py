"""The drive as the coordinator summarized it: one section per `section_s` (2 s), plus the dangerous moments.

Sections are what the coordinator posts to the server (and pushes live as WS `section`). The server stores
them, merges back-to-back dangerous sections into moments, and serves both in the trip report.
"""

import base64
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field, PlainSerializer

from app.domain.enums import Behavior, DangerLevel, DashboardLight, SafetyLevel, SoundLevel, SpeedSource
from app.schemas.auth import User
from app.schemas.trip import TripSummary

Alert = Literal["green", "yellow", "red"]


def _from_base64(value: Any) -> Any:
    return base64.b64decode(value, validate=True) if isinstance(value, str) else value


# Raw bytes in Python, base64 text on the JSON wire. (pydantic's Base64Bytes would also base64-*decode* raw
# bytes handed to it in Python, which garbles an image the coordinator builds the model with.)
JpegBytes = Annotated[
    bytes,
    BeforeValidator(_from_base64),
    PlainSerializer(lambda data: base64.b64encode(data).decode("ascii"), return_type=str, when_used="json"),
]


class SectionCategory(BaseModel):
    """One camera-model category within a section."""

    p: float | None = Field(description="Average probability over the section.")
    p_max: float | None
    active: bool = Field(description="The model marked it active at least once in the section.")
    r: float | None = Field(description="Largest contribution to the model's risk.")
    run_s: float | None = Field(description="Longest uninterrupted run reported by the model (s).")


class SectionBase(BaseModel):
    """What the coordinator measured in one section of driving."""

    section_id: str
    trip_id: str
    seq: int = Field(description="0, 1, 2... Section n covers t = n * section_s up to (n + 1) * section_s.")
    t_start: float = Field(description="Seconds since the trip's first tick (x axis of the drive chart).")
    t_end: float
    started_at: datetime
    ended_at: datetime
    ticks: int = Field(description="Scored ticks in the section (model detections or telemetry).")
    score_start: float = Field(description="Score just before the section.")
    score_end: float = Field(description="Score at the end of the section (y of the chart point).")
    score_min: float
    level: SafetyLevel = Field(description="Level for `score_end`.")
    danger: DangerLevel = Field(description="none | dangerous | critical (critical = the 'ultra dangerous' nodes).")
    behaviors: dict[Behavior, float] = Field(
        description="Behaviors seen -> seconds visible in this section (scored only while moving)."
    )
    speed_kmh: float = Field(description="Average speed.")
    speed_max_kmh: float
    speed_source: SpeedSource | None
    risk: float | None = Field(description="Camera model's average risk 0..1; null without model frames.")
    risk_max: float | None
    alert: Alert | None = Field(description="Worst camera-model alert in the section.")
    rules_triggered: list[str]
    categories: dict[str, SectionCategory] = Field(description="Keys are the model's category names.")
    groups: dict[str, float | None] = Field(description="Largest risk per channel: visual, manual, fatigue.")
    dashboard_light: DashboardLight = Field(description="Most severe light shown in the section.")
    vibrate_seat: bool = Field(description="The seat vibrated at least once.")
    sound: SoundLevel = Field(description="Loudest sound in the section.")
    emergency: bool = Field(description="The emergency alert fired in this section.")
    image_t: float | None = Field(
        description="Time (same axis as t_start) of the frame chosen as this section's image, if any."
    )
    lat: float | None = Field(description="From the phone's GPS (only with the phone speed source).")
    lon: float | None


class TripSection(SectionBase):
    """A section as the apps get it (trip report, WS `section`)."""

    has_image: bool = Field(description="The coordinator attached the frame of the riskiest moment.")
    image_url: str | None = Field(
        description="JPEG of the riskiest moment (dangerous/critical sections with video). Always null in the live "
        "WS message: the server stores the image first, the report then has the URL."
    )


class SectionIn(SectionBase):
    """Coordinator -> server: a section plus the frame of its riskiest moment (base64 JPEG in JSON)."""

    image_jpeg: JpegBytes | None = None


class DangerMoment(BaseModel):
    """Back-to-back dangerous sections merged into one moment: one node on the drive chart."""

    moment_id: str = Field(description="Id of the moment's first section.")
    t_start: float
    t_end: float
    duration_s: float
    danger: DangerLevel = Field(description="Worst section; `critical` = ultra dangerous (draw a node + image).")
    peak_t: float = Field(description="Where the node goes on the x axis: time of the image, else the worst section.")
    peak_score: float = Field(description="Score at that point (y of the node).")
    behaviors: dict[Behavior, float] = Field(description="Seconds per behavior, longest first.")
    categories: dict[str, float] = Field(description="Model categories active in the moment -> peak p.")
    rules_triggered: list[str]
    alert: Alert | None
    peak_risk: float | None
    score_start: float
    score_end: float
    score_min: float
    score_drop: float = Field(description="score_start - score_min: what this moment cost.")
    level: SafetyLevel = Field(description="Worst level reached (level of score_min).")
    speed_avg_kmh: float
    speed_max_kmh: float
    image_url: str | None = Field(description="Image of the riskiest frame of the moment.")
    section_ids: list[str]


class ModelCategoryStats(BaseModel):
    active_s: float = Field(description="Seconds the model marked the category active (moving only).")
    episodes: int = Field(description="Behavior episodes of at least 0.5 s.")
    max_episode_s: float


class ModelEpisode(BaseModel):
    """One behavior episode as the camera model saw it: a category active, short breaks merged."""

    category: str = Field(description="The model's category name (phone_use, eyes_off_road...).")
    t_start: float = Field(description="Seconds since the trip's first tick (same axis as `TripSection.t_start`).")
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
    """Everything about one drive in one response: the summary screen and the drive chart.

    `sections` is the drive, one row per `section_s`, oldest first. `moments` are its dangerous parts.
    """

    trip: TripSummary
    user: User | None = Field(description="The driver's account; null if the trip was started without login.")
    section_s: float = Field(description="Seconds per section.")
    sections: list[TripSection]
    moments: list[DangerMoment] = Field(description="Dangerous moments, oldest first.")
    model: ModelReport | None = Field(
        default=None, description="The camera model's own trip report; null if no model frames came."
    )
