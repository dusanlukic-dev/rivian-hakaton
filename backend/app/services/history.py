"""Trip history and the per-trip report: the live trip from memory, everything else from Postgres.

Visibility: a trip started while logged in belongs to that account and only its token can read it
(anyone else gets 404, as if it didn't exist). A trip started without login is readable by anyone, as
before accounts existed. The live path (/telemetry, /ws, /trips/{id}/end) stays open: it's the car's own network.
"""

from collections.abc import Callable
from typing import Any

from app.domain.enums import Behavior, SafetyLevel, TripStatus
from app.repositories.trips import InMemoryTripRepository
from app.schemas.auth import User
from app.schemas.recording import RiskEvent, TripReport, TripSample
from app.schemas.trip import BehaviorSummary, TripSummary
from app.services.alerts import level_for
from app.services.auth import AuthService
from app.services.recording import RecordingUnavailable, TripRecorder
from app.services.trips import TIPS, to_summary

MediaUrl = Callable[[str | None], str | None]


class TripNotFound(Exception):
    pass


def can_see(owner_id: str | None, user: User | None) -> bool:
    return owner_id is None or (user is not None and user.user_id == owner_id)


async def list_trips(
    repo: InMemoryTripRepository, recorder: TripRecorder, user: User | None, driver_id: str | None
) -> list[TripSummary]:
    """Oldest first. Logged in: your trips. Not logged in: trips started without login (by driver_id)."""
    owner_id = user.user_id if user else None
    try:
        rows = await recorder.trip_rows(owner_id, None if user else driver_id)
    except RecordingUnavailable:  # Postgres down or recording off: what this process remembers
        return [to_summary(t) for t in repo.list(None if user else driver_id) if t.user_id == owner_id]
    summaries = []
    for row in rows:
        live = repo.get(row["id"])
        summaries.append(to_summary(live) if live is not None else summary_from_row(row))
    return summaries


async def summary(trip_id: str, repo: InMemoryTripRepository, recorder: TripRecorder, user: User | None) -> TripSummary:
    live = repo.get(trip_id)
    if live is not None:
        if not can_see(live.user_id, user):
            raise TripNotFound(trip_id)
        return to_summary(live)
    try:
        stored = await recorder.read_trip(trip_id, samples=False, events=False)
    except RecordingUnavailable:
        stored = None
    if stored is None or not can_see(stored.trip["user_id"], user):
        raise TripNotFound(trip_id)
    return summary_from_row(stored.trip)


async def report(
    trip_id: str,
    repo: InMemoryTripRepository,
    recorder: TripRecorder,
    auth: AuthService,
    user: User | None,
    media_url: MediaUrl,
) -> TripReport:
    """Everything about one drive. Raises RecordingUnavailable (503) or TripNotFound (404)."""
    stored = await recorder.read_trip(trip_id)
    owner_id = stored.trip["user_id"] if stored else None
    if stored is None or not can_see(owner_id, user):
        raise TripNotFound(trip_id)
    live = repo.get(trip_id)
    owner = None
    if owner_id is not None:
        owner = user if user is not None and user.user_id == owner_id else await auth.user_by_id(owner_id)
    return TripReport(
        trip=to_summary(live) if live is not None else summary_from_row(stored.trip),
        user=owner,
        window_s=recorder.cfg.sample_window_s,
        samples=[TripSample.model_validate(row) for row in stored.samples],
        events=[to_event(row, media_url) for row in stored.events],
    )


def summary_from_row(row: dict[str, Any]) -> TripSummary:
    """TripSummary from a `trips` row (the running summary; final once `ended_at` is set)."""
    final = row["final_score"] if row["final_score"] is not None else 100.0
    behaviors = []
    for item in row["behaviors"] or []:
        try:
            behavior = Behavior(item["behavior"])
        except ValueError:  # a label that no longer exists
            continue
        behaviors.append(BehaviorSummary(
            behavior=behavior,
            occurrences=item["occurrences"],
            total_seconds=item["total_seconds"],
            tip=TIPS[behavior],
        ))
    return TripSummary(
        trip_id=row["id"],
        driver_id=row["driver_id"],
        status=TripStatus.ENDED if row["ended_at"] else TripStatus.ACTIVE,
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        duration_s=row["duration_s"] or 0.0,
        final_score=final,
        average_score=row["average_score"] if row["average_score"] is not None else final,
        min_score=row["min_score"] if row["min_score"] is not None else final,
        level=SafetyLevel(row["level"]) if row["level"] else level_for(final),
        emergency_alert_sent=bool(row["emergency_alert_sent"]),
        behaviors=behaviors,
    )


def to_event(row: dict[str, Any], media_url: MediaUrl) -> RiskEvent:
    return RiskEvent.model_validate({
        **row,
        "event_id": row["id"],
        "video_url": media_url(row["video_key"]),
        "thumbnail_url": media_url(row["thumbnail_key"]),
    })
