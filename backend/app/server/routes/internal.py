"""Coordinator -> server (`X-Internal-Token`). Contract: app/schemas/sync.py, docs/ARCHITECTURE.md."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.sync import CloseInterruptedIn, CloseInterruptedOut, SyncResult, TripMeta, TripSync
from app.server.deps import Auth, Store, require_internal_token
from app.server.services.auth import AuthUnavailable
from app.server.services.storage import StorageUnavailable

router = APIRouter(prefix="/internal", tags=["internal (coordinator -> server)"], dependencies=[Depends(require_internal_token)])
logger = logging.getLogger(__name__)
_warned_owner: set[str] = set()


@router.post("/trips/close-interrupted")
async def close_interrupted(body: CloseInterruptedIn, store: Store) -> CloseInterruptedOut:
    """The coordinator just started: trips it left open (crash, restart) end at their last summary."""
    try:
        return CloseInterruptedOut(closed=await store.close_interrupted(body.keep))
    except StorageUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e


@router.post("/trips/{trip_id}/sync")
async def sync_trip(trip_id: str, body: TripSync, store: Store, auth: Auth) -> SyncResult:
    """Everything new about a trip: its meta (stored once), new sections (+ images) and the running summary.
    Idempotent. 503 while Postgres is down: the coordinator keeps the data and retries."""
    if body.trip.trip_id != trip_id or any(s.trip_id != trip_id for s in body.sections):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "trip_id in the body doesn't match the URL")
    if body.trip.owner_token is not None:
        body = body.model_copy(update={"trip": await _resolve_owner(body.trip, auth)})
    try:
        return await store.sync(trip_id, body)
    except StorageUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e


async def _resolve_owner(meta: TripMeta, auth: Auth) -> TripMeta:
    """A trip the coordinator started while it couldn't reach us: put it on the token's account (the token itself
    is never stored). A wrong or expired token leaves the trip without an account, like a trip without login."""
    update: dict = {"owner_token": None}
    if meta.user_id is None:
        try:
            user = await auth.user_for_token(meta.owner_token or "")
        except AuthUnavailable as e:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
        if user is not None:
            update.update(user_id=user.user_id, driver_id=user.username)
        elif meta.trip_id not in _warned_owner:
            _warned_owner.add(meta.trip_id)
            logger.warning("Trip %s: the login the coordinator couldn't check is invalid; stored without an account",
                           meta.trip_id)
    return meta.model_copy(update=update)
