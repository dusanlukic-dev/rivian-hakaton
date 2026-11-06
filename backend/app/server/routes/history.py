"""Stored trips (server): history, one trip's summary, its sections and the drive report.

These read Postgres (what the coordinator delivered), so they work after any restart. A trip started while
logged in is visible only with that account's token (app/domain/access.py).
"""

from fastapi import APIRouter, HTTPException, Request, status

from app.schemas.report import TripReport, TripSection
from app.schemas.trip import TripSummary
from app.server.deps import Auth, OptionalUser, Store
from app.server.services import history
from app.server.services.auth import AuthUnavailable
from app.server.services.storage import StorageUnavailable

router = APIRouter(prefix="/trips", tags=["trips (server)"])


def _unavailable(error: Exception) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error))


def _not_found(trip_id: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"Trip {trip_id} not found")


def media_url(request: Request) -> history.MediaUrl:
    """Absolute URL of a stored image, through this API (works over the hotspot, unlike S3's own port)."""

    def url(key: str | None) -> str | None:
        return str(request.url_for("get_media", key=key)) if key else None

    return url


@router.get("")
async def list_trips(store: Store, user: OptionalUser, driver_id: str | None = None) -> list[TripSummary]:
    """History, oldest first. Logged in: your trips (`driver_id` is ignored). Not logged in: trips started
    without login, optionally only one `driver_id`'s. A running trip shows its running summary."""
    try:
        return await history.list_trips(store, user, driver_id)
    except StorageUnavailable as e:
        raise _unavailable(e) from e


@router.get("/{trip_id}/summary")
async def get_trip_summary(trip_id: str, store: Store, user: OptionalUser) -> TripSummary:
    try:
        return await history.summary(store, trip_id, user)
    except StorageUnavailable as e:
        raise _unavailable(e) from e
    except history.TripNotFound:
        raise _not_found(trip_id) from None


@router.get("/{trip_id}/report")
async def trip_report(
    trip_id: str, request: Request, store: Store, auth: Auth, user: OptionalUser
) -> TripReport:
    """The drive in one call: summary, driver, every 2 s section (the chart) and the dangerous moments with
    the image of their riskiest frame."""
    try:
        return await history.report(store, auth, trip_id, user, media_url(request))
    except (StorageUnavailable, AuthUnavailable) as e:
        raise _unavailable(e) from e
    except history.TripNotFound:
        raise _not_found(trip_id) from None


@router.get("/{trip_id}/sections")
async def trip_sections(
    trip_id: str, request: Request, store: Store, user: OptionalUser, after_seq: int | None = None
) -> list[TripSection]:
    """Only the sections, oldest first. `after_seq=N` returns the ones after section N (polling a live trip)."""
    try:
        return await history.sections(store, trip_id, user, media_url(request), after_seq)
    except StorageUnavailable as e:
        raise _unavailable(e) from e
    except history.TripNotFound:
        raise _not_found(trip_id) from None
