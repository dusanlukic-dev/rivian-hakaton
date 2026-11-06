"""Stored trip data: the whole report of one drive, its raw timeline, risky moments and their clips.

These read Postgres (not the in-memory trips), so they keep working after a backend restart.
A trip started while logged in is visible only with that account's token (see services/history.py).
"""

import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.deps import Auth, OptionalUser, Recorder, TripRepo
from app.schemas.auth import User
from app.schemas.recording import RiskEvent, TripReport, TripSample, TripTimeline
from app.services import history
from app.services.auth import AuthUnavailable
from app.services.recording import RecordingUnavailable, StoredTrip, TripRecorder

router = APIRouter(tags=["recording"])

_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


def _unavailable(error: Exception) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error))


def _not_recorded(trip_id: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"Trip {trip_id} has no recording")


def _media_url(request: Request) -> history.MediaUrl:
    def media_url(key: str | None) -> str | None:
        return str(request.url_for("get_media", key=key)) if key else None

    return media_url


async def _stored(
    recorder: TripRecorder, trip_id: str, user: User | None, samples: bool, events: bool
) -> StoredTrip:
    try:
        stored = await recorder.read_trip(trip_id, samples=samples, events=events)
    except RecordingUnavailable as e:
        raise _unavailable(e) from e
    if stored is None or not history.can_see(stored.trip["user_id"], user):
        raise _not_recorded(trip_id)
    return stored


@router.get("/trips/{trip_id}/report")
async def trip_report(
    trip_id: str, request: Request, repo: TripRepo, recorder: Recorder, auth: Auth, user: OptionalUser
) -> TripReport:
    """One drive in one call: the summary, who drove, the raw per-second recording for the app's
    charts, and the risky moments with their images and clips."""
    try:
        return await history.report(trip_id, repo, recorder, auth, user, _media_url(request))
    except (RecordingUnavailable, AuthUnavailable) as e:
        raise _unavailable(e) from e
    except history.TripNotFound:
        raise _not_recorded(trip_id) from None


@router.get("/trips/{trip_id}/timeline")
async def trip_timeline(trip_id: str, recorder: Recorder, user: OptionalUser) -> TripTimeline:
    """Only the raw recording of the drive, one sample per second (the `samples` of the report)."""
    stored = await _stored(recorder, trip_id, user, samples=True, events=False)
    return TripTimeline(
        trip_id=trip_id,
        window_s=recorder.cfg.sample_window_s,
        samples=[TripSample.model_validate(row) for row in stored.samples],
    )


@router.get("/trips/{trip_id}/events")
async def trip_events(
    trip_id: str,
    request: Request,
    recorder: Recorder,
    user: OptionalUser,
    order: Literal["time", "worst"] = "time",
) -> list[RiskEvent]:
    """The risky moments of a trip, with a video clip and a thumbnail when video was streamed.

    `order=worst` puts the most costly moments first (biggest score drop, then model risk, then length).
    """
    stored = await _stored(recorder, trip_id, user, samples=False, events=True)
    rows = stored.events
    if order == "worst":
        rows.sort(key=lambda r: (r["score_drop"], r["peak_risk"] or 0.0, r["duration_s"]), reverse=True)
    media_url = _media_url(request)
    return [history.to_event(row, media_url) for row in rows]


@router.get(
    "/media/{key:path}",
    name="get_media",
    response_class=Response,
    responses={200: {"content": {"video/mp4": {}, "image/jpeg": {}}}, 206: {"description": "Partial content"}},
)
async def get_media(key: str, request: Request, recorder: Recorder) -> Response:
    """A stored clip or thumbnail, streamed from S3 (supports Range, so video players can seek).

    Not behind login: the keys are random ids, known only to whoever may read the trip's report.
    """
    try:
        obj = await recorder.media_object(key)
    except RecordingUnavailable as e:
        raise _unavailable(e) from e
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No media at {key}")
    data, content_type = obj
    return _ranged(data, content_type, request.headers.get("range"))


def _ranged(data: bytes, content_type: str, range_header: str | None) -> Response:
    size = len(data)
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=31536000, immutable"}
    match = _RANGE.fullmatch(range_header.strip()) if range_header else None
    if match is None or not any(match.groups()):  # no range, or one we don't handle: send it all
        return Response(data, media_type=content_type, headers=headers)
    first, last = match.groups()
    if first:
        start, end = int(first), min(int(last), size - 1) if last else size - 1
    else:  # "bytes=-500": the last 500 bytes
        start, end = max(size - int(last), 0), size - 1
    if start > end:
        return Response(status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE, headers={"Content-Range": f"bytes */{size}"})
    headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return Response(data[start : end + 1], status_code=status.HTTP_206_PARTIAL_CONTENT, media_type=content_type, headers=headers)
