from pydantic import BaseModel

from app.domain.enums import Behavior


class BehaviorBreakdown(BaseModel):
    behavior: Behavior
    occurrences: int
    total_seconds: float
    trips_affected: int


class AnalyticsOverview(BaseModel):
    """Company-facing aggregates: scores and behaviors only, no images or raw video."""

    total_trips: int
    completed_trips: int
    average_final_score: float | None
    average_trip_score: float | None
    emergency_alerts: int
    behaviors: list[BehaviorBreakdown]
