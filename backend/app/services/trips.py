import uuid
from datetime import datetime, timezone

from app.domain.enums import Behavior, SafetyLevel
from app.domain.trip import EmergencyContact, Trip
from app.repositories.trips import InMemoryTripRepository
from app.schemas.trip import BehaviorSummary, TelemetryTick, TripCreate, TripState, TripSummary
from app.services.alerts import evaluate_response, level_for
from app.services.camera import behaviors_from_frame, to_view
from app.services.notifications import notify_emergency_contact
from app.services.scoring import apply_tick

TIPS: dict[Behavior, str] = {
    Behavior.LOOKING_AT_PHONE: "Put your phone in a holder or turn on Do Not Disturb while driving.",
    Behavior.LOOKING_BEHIND: "Use your mirrors instead of looking back; pull over if something in the back seat needs attention.",
    Behavior.TURNING_AROUND: "Stay facing the road - turning in your seat takes your eyes and hands away from driving.",
    Behavior.HANDS_OFF_WHEEL: "Keep both hands on the wheel - it's your fastest way to react.",
    Behavior.DROWSY: "You showed signs of drowsiness - take a break at least every 2 hours and don't drive tired.",
    Behavior.EYES_OFF_ROAD: "Keep your eyes on the road - a glance away should never last longer than 2 seconds.",
}


def start_trip(repo: InMemoryTripRepository, data: TripCreate) -> tuple[Trip, Trip | None]:
    """Start a new trip. A trip still in progress is ended first and returned as the second item."""
    previous = repo.active()
    if previous is not None:
        end_trip(previous)

    contact = data.emergency_contact
    trip = Trip(
        id=uuid.uuid4().hex,
        driver_id=data.driver_id,
        started_at=datetime.now(timezone.utc),
        emergency_contact=EmergencyContact(contact.name, contact.phone) if contact else None,
    )
    trip.response = evaluate_response(trip, speed_kmh=0.0)
    repo.add(trip)
    return trip, previous


def process_tick(trip: Trip, tick: TelemetryTick) -> bool:
    """Apply one telemetry tick. Returns True if this tick triggered the emergency alert."""
    behaviors = set(tick.behaviors)
    trip.camera = None
    if tick.frame is not None:
        behaviors |= behaviors_from_frame(tick.frame)
        trip.camera = to_view(tick.frame)
    apply_tick(trip, tick.timestamp, tick.speed_kmh, behaviors)
    trip.response = evaluate_response(trip, tick.speed_kmh)
    if level_for(trip.score) is SafetyLevel.EMERGENCY and not trip.emergency_alert_sent:
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
        emergency_alert_sent=trip.emergency_alert_sent,
    )


def to_summary(trip: Trip) -> TripSummary:
    behaviors = sorted(trip.stats.items(), key=lambda item: item[1].total_seconds, reverse=True)
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
        level=level_for(trip.score),
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
