from statistics import mean

from app.domain.enums import Behavior
from app.domain.trip import Trip
from app.schemas.analytics import AnalyticsOverview, BehaviorBreakdown


def overview(trips: list[Trip]) -> AnalyticsOverview:
    completed = [t for t in trips if t.ended_at is not None]

    breakdown: dict[Behavior, BehaviorBreakdown] = {}
    for trip in completed:
        for behavior, stat in trip.stats.items():
            row = breakdown.setdefault(
                behavior,
                BehaviorBreakdown(behavior=behavior, occurrences=0, total_seconds=0.0, trips_affected=0),
            )
            row.occurrences += stat.occurrences
            row.total_seconds = round(row.total_seconds + stat.total_seconds, 1)
            row.trips_affected += 1

    return AnalyticsOverview(
        total_trips=len(trips),
        completed_trips=len(completed),
        average_final_score=round(mean(t.score for t in completed), 1) if completed else None,
        average_trip_score=round(mean(t.average_score for t in completed), 1) if completed else None,
        emergency_alerts=sum(t.emergency_alert_sent for t in trips),
        behaviors=sorted(breakdown.values(), key=lambda r: r.total_seconds, reverse=True),
    )
