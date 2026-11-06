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


class TripReport(BaseModel):
    """Everything about one drive in one response: the summary screen and the drive chart.

    `sections` is the drive, one row per `section_s`, oldest first. `moments` are its dangerous parts.
    """

    trip: TripSummary
    user: User | None = Field(description="The driver's account; null if the trip was started without login.")
    section_s: float = Field(description="Seconds per section.")
    sections: list[TripSection]
    moments: list[DangerMoment] = Field(description="Dangerous moments, oldest first.")
