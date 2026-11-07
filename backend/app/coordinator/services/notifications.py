import logging

from app.domain.trip import Trip

logger = logging.getLogger(__name__)


def notify_emergency_contact(trip: Trip) -> bool:
    """Only logs: the phone texts the contact itself on the `emergency` event (D54, alerts/sms.ts in the app).

    Plug a server-side SMS / push (e.g. Twilio) in here if the car should text without the phone. Returns whether a
    contact exists to notify.
    """
    contact = trip.emergency_contact
    if contact is None:
        logger.warning("Trip %s hit EMERGENCY but has no emergency contact", trip.id)
        return False
    logger.warning(
        "EMERGENCY: notifying %s (%s) - driver %s, trip %s, score %.1f",
        contact.name, contact.phone, trip.driver_id, trip.id, trip.score,
    )
    return True
