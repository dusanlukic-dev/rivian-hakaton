"""Trip history and the drive report, all from what the coordinator delivered (Postgres + S3).

Visibility (`app/domain/access.py`): a trip started while logged in belongs to that account and only its
token can read it (anyone else gets 404, as if it didn't exist). A trip started without login is readable by
anyone. A trip that is still running shows its running summary (at most one section, ~2 s, behind).

Moments: back-to-back dangerous sections are one moment (a gap of one quiet section is bridged, so a glance
back at the road in the middle of texting doesn't split it). The moment's node goes where its image was taken.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.domain.access import can_see
from app.domain.enums import Behavior, DangerLevel, SafetyLevel, TripStatus
from app.domain.levels import level_for
from app.domain.tips import TIPS
from app.schemas.auth import User
from app.schemas.report import DangerMoment, TripReport, TripSection
from app.schemas.trip import BehaviorSummary, TripSummary
from app.server.services.auth import AuthService
from app.server.services.storage import TripStore

MediaUrl = Callable[[str | None], str | None]

_DANGER_RANK = {DangerLevel.NONE: 0, DangerLevel.DANGEROUS: 1, DangerLevel.CRITICAL: 2}
_ALERT_RANK = {"green": 0, "yellow": 1, "red": 2}
MOMENT_BRIDGE_SECTIONS = 1  # quiet sections allowed inside one moment


class TripNotFound(Exception):
    pass


async def visible_trip(store: TripStore, trip_id: str, user: User | None) -> dict[str, Any]:
    row = await store.trip(trip_id)
    if row is None or not can_see(row["user_id"], user):
        raise TripNotFound(trip_id)
    return row


async def list_trips(store: TripStore, user: User | None, driver_id: str | None) -> list[TripSummary]:
    """Oldest first. Logged in: your trips. Not logged in: trips started without login (by driver_id)."""
    rows = await store.trips(user.user_id if user else None, None if user else driver_id)
    return [summary_from_row(row) for row in rows]


async def summary(store: TripStore, trip_id: str, user: User | None) -> TripSummary:
    return summary_from_row(await visible_trip(store, trip_id, user))


async def sections(
    store: TripStore, trip_id: str, user: User | None, media_url: MediaUrl, after_seq: int | None = None
) -> list[TripSection]:
    await visible_trip(store, trip_id, user)
    return [to_section(row, media_url) for row in await store.sections(trip_id, after_seq)]


async def report(
    store: TripStore, auth: AuthService, trip_id: str, user: User | None, media_url: MediaUrl
) -> TripReport:
    """Everything about one drive. Raises StorageUnavailable (503) or TripNotFound (404)."""
    row = await visible_trip(store, trip_id, user)
    owner_id = row["user_id"]
    owner = None
    if owner_id is not None:
        owner = user if user is not None and user.user_id == owner_id else await auth.user_by_id(owner_id)
    stored = [to_section(s, media_url) for s in await store.sections(trip_id)]
    return TripReport(
        trip=summary_from_row(row),
        user=owner,
        section_s=row["section_s"] or 2.0,
        sections=stored,
        moments=build_moments(stored),
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


def to_section(row: dict[str, Any], media_url: MediaUrl) -> TripSection:
    behaviors = {}
    for name, seconds in (row["behaviors"] or {}).items():
        try:
            behaviors[Behavior(name)] = seconds
        except ValueError:  # a label that no longer exists
            continue
    return TripSection.model_validate({
        **row,
        "section_id": row["id"],
        "behaviors": behaviors,
        "has_image": row["image_key"] is not None,
        "image_url": media_url(row["image_key"]),
    })


def build_moments(stored: list[TripSection]) -> list[DangerMoment]:
    """Back-to-back dangerous sections -> moments, oldest first."""
    groups: list[list[TripSection]] = []
    for section in stored:
        if section.danger is DangerLevel.NONE:
            continue
        if groups and section.seq - groups[-1][-1].seq <= 1 + MOMENT_BRIDGE_SECTIONS:
            groups[-1].append(section)
        else:
            groups.append([section])
    return [_moment(group) for group in groups]


def _moment(group: list[TripSection]) -> DangerMoment:
    def severity(s: TripSection) -> tuple:
        return (_DANGER_RANK[s.danger], s.image_url is not None, s.risk_max or -1.0, s.score_start - s.score_min)

    peak = max(group, key=severity)
    with_image = [s for s in group if s.image_url]
    image_section = peak if peak.image_url else (max(with_image, key=severity) if with_image else None)
    behaviors: dict[Behavior, float] = {}
    categories: dict[str, float] = {}
    rules: set[str] = set()
    alert = None
    for s in group:
        for behavior, seconds in s.behaviors.items():
            behaviors[behavior] = behaviors.get(behavior, 0.0) + seconds
        for name, category in s.categories.items():
            if category.active:
                categories[name] = max(categories.get(name, 0.0), category.p_max or 0.0)
        rules.update(s.rules_triggered)
        if s.alert and _ALERT_RANK[s.alert] > _ALERT_RANK.get(alert or "", -1):
            alert = s.alert
    first, last = group[0], group[-1]
    score_min = min(s.score_min for s in group)
    risks = [s.risk_max for s in group if s.risk_max is not None]
    node = image_section or peak
    return DangerMoment(
        moment_id=first.section_id,
        t_start=first.t_start,
        t_end=last.t_end,
        duration_s=round(last.t_end - first.t_start, 1),
        danger=peak.danger,
        peak_t=node.image_t if node.image_t is not None else round((node.t_start + node.t_end) / 2, 3),
        peak_score=node.score_end,
        behaviors={b: round(s, 1) for b, s in sorted(behaviors.items(), key=lambda kv: (-kv[1], kv[0]))},
        categories={n: round(p, 3) for n, p in sorted(categories.items(), key=lambda kv: (-kv[1], kv[0]))},
        rules_triggered=sorted(rules),
        alert=alert,
        peak_risk=max(risks) if risks else None,
        score_start=first.score_start,
        score_end=last.score_end,
        score_min=score_min,
        score_drop=round(max(first.score_start - score_min, 0.0), 1),
        level=level_for(score_min),
        speed_avg_kmh=round(sum(s.speed_kmh for s in group) / len(group), 1),
        speed_max_kmh=max(s.speed_max_kmh for s in group),
        image_url=image_section.image_url if image_section else None,
        section_ids=[s.section_id for s in group],
    )
