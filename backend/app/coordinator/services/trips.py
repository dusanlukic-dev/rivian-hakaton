import uuid
from datetime import datetime, timezone

from app.coordinator.repositories.trips import InMemoryTripRepository
from app.coordinator.services.alerts import evaluate_response, level_for
from app.coordinator.services.camera import behaviors_from_frame, to_view
from app.coordinator.services.notifications import notify_emergency_contact
from app.coordinator.services.scoring import DEFAULT_CONFIG as SCORING
from app.coordinator.services.scoring import apply_tick
from app.domain.enums import SpeedSource
from app.domain.tips import TIPS
from app.domain.trip import EmergencyContact, Trip
from app.schemas.auth import User
from app.schemas.trip import BehaviorSummary, TelemetryTick, TripCreate, TripState, TripSummary

__all__ = [
    "TIPS", "UNVERIFIED_DRIVER", "MissingDriver", "end_trip", "process_tick", "start_trip", "to_state", "to_summary",
]



class MissingDriver(ValueError):
    """No login and no driver_id: nobody to put the trip on."""


UNVERIFIED_DRIVER = "unverified-login"  # driver_id until the server resolves a login it couldn't check


def start_trip(
    repo: InMemoryTripRepository, data: TripCreate, user: User | None = None, *, unverified_login: bool = False
) -> tuple[Trip, Trip | None]:
    """Start a new trip. A trip still in progress is ended first and returned as the second item.

    With a logged-in `user` the trip belongs to that account: its username becomes the driver_id
    and its saved emergency contact is used unless the request brings one. `unverified_login`: the phone
    sent a token the server couldn't check (unreachable); the trip starts anyway and the server puts it on
    the account when it gets the trip (TripMeta.owner_token).
    """
    driver_id = user.username if user else data.driver_id
    if not driver_id and unverified_login:
        driver_id = UNVERIFIED_DRIVER
    if not driver_id:
        raise MissingDriver
    previous = repo.active()
    if previous is not None:
        end_trip(previous)

    contact = data.emergency_contact or (user.emergency_contact if user else None)
    trip = Trip(
        id=uuid.uuid4().hex,
        driver_id=driver_id,
        started_at=datetime.now(timezone.utc),
        emergency_contact=EmergencyContact(contact.name, contact.phone) if contact else None,
        user_id=user.user_id if user else None,
    )
    trip.response = evaluate_response(trip, speed_kmh=0.0)
    repo.add(trip)
    return trip, previous


def process_tick(trip: Trip, tick: TelemetryTick, speed_kmh: float, speed_source: SpeedSource) -> bool:
    """Apply one telemetry tick at the given speed (see services/speed.py for where it comes from).

    Returns True if this tick triggered the emergency alert.
    """
    behaviors = set(tick.behaviors)
    trip.camera = None
    if tick.frame is not None:
        behaviors |= behaviors_from_frame(tick.frame)
        trip.camera = to_view(tick.frame)
    trip.speed_kmh, trip.speed_source = speed_kmh, speed_source
    model_risk = trip.camera.risk if trip.camera is not None else None
    apply_tick(trip, tick.timestamp, speed_kmh, behaviors, model_risk)
    trip.response = evaluate_response(trip, speed_kmh)
    if trip.emergency_streak_s >= SCORING.emergency_hold_s and not trip.emergency_alert_sent:
        notify_emergency_contact(trip)
        trip.emergency_alert_sent = True
        return True
    return False


def end_trip(trip: Trip) -> bool:
    """End the trip. Returns False if it had already ended."""
    if trip.ended_at is not None:
        return False
    trip.ended_at = datetime.now(timezone.utc)
    return True


def to_state(trip: Trip) -> TripState:
    return TripState(
        trip_id=trip.id,
        driver_id=trip.driver_id,
        status=trip.status,
        score=round(trip.score, 1),
        level=level_for(trip.score),
        active_behaviors={b: round(s, 1) for b, s in trip.active.items()},
        response=trip.response,
        camera=trip.camera,
        speed_kmh=trip.speed_kmh,
        speed_source=trip.speed_source,
        emergency_alert_sent=trip.emergency_alert_sent,
    )


def to_summary(trip: Trip) -> TripSummary:
    # Worst first; ties by name, so the order is the same on every run.
    behaviors = sorted(trip.stats.items(), key=lambda item: (-item[1].total_seconds, item[0]))
    return TripSummary(
        trip_id=trip.id,
        driver_id=trip.driver_id,
        status=trip.status,
        started_at=trip.started_at,
        ended_at=trip.ended_at,
        duration_s=round(trip.elapsed_s, 1),
        final_score=round(trip.score, 1),
        average_score=round(trip.average_score, 1),
        min_score=round(trip.min_score, 1),
        level=level_for(trip.average_score),  # how the drive went; the live score is ~100 once parked
        emergency_alert_sent=trip.emergency_alert_sent,
        behaviors=[
            BehaviorSummary(
                behavior=behavior,
                occurrences=stat.occurrences,
                total_seconds=round(stat.total_seconds, 1),
                tip=TIPS[behavior],
            )
            for behavior, stat in behaviors
        ],
    )
