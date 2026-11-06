"""Company view: scores and behavior counts only, never images (privacy). Computed from the `trips` rows."""

from statistics import mean
from typing import Any

from app.domain.enums import Behavior
from app.schemas.analytics import AnalyticsOverview, BehaviorBreakdown


def overview(rows: list[dict[str, Any]]) -> AnalyticsOverview:
    completed = [row for row in rows if row["ended_at"] is not None]

    breakdown: dict[Behavior, BehaviorBreakdown] = {}
    for row in completed:
        for item in row["behaviors"] or []:
            try:
                behavior = Behavior(item["behavior"])
            except ValueError:  # a label that no longer exists
                continue
            entry = breakdown.setdefault(
                behavior, BehaviorBreakdown(behavior=behavior, occurrences=0, total_seconds=0.0, trips_affected=0)
            )
            entry.occurrences += item["occurrences"]
            entry.total_seconds = round(entry.total_seconds + item["total_seconds"], 1)
            entry.trips_affected += 1

    finals = [row["final_score"] for row in completed if row["final_score"] is not None]
    averages = [row["average_score"] for row in completed if row["average_score"] is not None]
    return AnalyticsOverview(
        total_trips=len(rows),
        completed_trips=len(completed),
        average_final_score=round(mean(finals), 1) if finals else None,
        average_trip_score=round(mean(averages), 1) if averages else None,
        emergency_alerts=sum(1 for row in rows if row["emergency_alert_sent"]),
        behaviors=sorted(breakdown.values(), key=lambda entry: entry.total_seconds, reverse=True),
    )
