import logging

from app.domain.trip import Trip

logger = logging.getLogger(__name__)


def notify_emergency_contact(trip: Trip) -> bool:
    """Stub: plug in SMS / push (e.g. Twilio, Expo push) here. Returns whether a message went out."""
    contact = trip.emergency_contact
    if contact is None:
        logger.warning("Trip %s hit EMERGENCY but has no emergency contact", trip.id)
        return False
    logger.warning(
        "EMERGENCY: notifying %s (%s) - driver %s, trip %s, score %.1f",
        contact.name, contact.phone, trip.driver_id, trip.id, trip.score,
    )
    return True
