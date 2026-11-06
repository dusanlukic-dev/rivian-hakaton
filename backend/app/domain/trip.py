from dataclasses import dataclass, field
from datetime import datetime

from app.domain.enums import Behavior, DashboardLight, SoundLevel, TripStatus

MAX_SCORE = 100.0


@dataclass
class EmergencyContact:
    name: str
    phone: str


@dataclass
class BehaviorStat:
    occurrences: int = 0
    total_seconds: float = 0.0


@dataclass
class CarResponse:
    """What the car should do right now: dashboard light, seat vibration, sound."""

    dashboard_light: DashboardLight = DashboardLight.GREEN
    vibrate_seat: bool = False
    sound: SoundLevel = SoundLevel.NONE
    message: str = ""


@dataclass
class CameraCategory:
    """One behavior category as the camera model sees it right now."""

    p: float | None = None  # probability that it is happening now, 0..1
    active: bool = False  # the model's own on/off decision
    run_s: float | None = None  # how long it has lasted without a break
    r: float | None = None  # its contribution to the model's risk


@dataclass
class CameraView:
    """The camera model's own instantaneous view, forwarded to the app for display (no raw perception)."""

    risk: float | None = None  # risk.final, 0..1
    alert: str | None = None  # "green" | "yellow" | "red"
    rules_triggered: list[str] = field(default_factory=list)  # hard rules: microsleep, long look away...
    categories: dict[str, CameraCategory] = field(default_factory=dict)  # the model's own category names
    groups: dict[str, float | None] = field(default_factory=dict)  # risk per channel: visual, manual, fatigue

    @property
    def alarm(self) -> bool:
        return self.alert == "red"


@dataclass
class Trip:
    id: str
    driver_id: str
    started_at: datetime
    emergency_contact: EmergencyContact | None = None
    ended_at: datetime | None = None

    score: float = MAX_SCORE
    min_score: float = MAX_SCORE
    elapsed_s: float = 0.0
    score_seconds: float = 0.0  # integral of score over time, for the time-weighted average
    clean_streak_s: float = 0.0  # seconds since the last penalized behavior
    last_tick_at: datetime | None = None

    # Behaviors currently visible on camera -> how long they have lasted (seconds).
    active: dict[Behavior, float] = field(default_factory=dict)
    # Active behaviors already counted as an occurrence (and given the onset penalty).
    counted: set[Behavior] = field(default_factory=set)
    stats: dict[Behavior, BehaviorStat] = field(default_factory=dict)

    response: CarResponse = field(default_factory=CarResponse)
    camera: CameraView | None = None  # from the latest tick; None if it carried no model frame
    emergency_alert_sent: bool = False

    @property
    def status(self) -> TripStatus:
        return TripStatus.ENDED if self.ended_at else TripStatus.ACTIVE

    @property
    def average_score(self) -> float:
        return self.score_seconds / self.elapsed_s if self.elapsed_s else self.score
