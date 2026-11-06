"""Stored trip data for the driver's report: the timeline, the risky moments and their clips.

These read Postgres (not the in-memory trips), so they keep working after a backend restart.
"""

import re
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.deps import Recorder
from app.schemas.recording import RiskEvent, TripSample, TripTimeline
from app.services.recording import RecordingUnavailable

router = APIRouter(tags=["recording"])

_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


def _unavailable(error: RecordingUnavailable) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error))


def _not_recorded(trip_id: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"Trip {trip_id} has no recording")


@router.get("/trips/{trip_id}/timeline")
async def trip_timeline(trip_id: str, recorder: Recorder) -> TripTimeline:
    """Everything recorded during the drive, one sample per window (charts: score, speed, model risk)."""
    try:
        rows = await recorder.timeline(trip_id)
    except RecordingUnavailable as e:
        raise _unavailable(e) from e
    if rows is None:
        raise _not_recorded(trip_id)
    return TripTimeline(
        trip_id=trip_id,
        window_s=recorder.cfg.sample_window_s,
        samples=[TripSample.model_validate(row) for row in rows],
    )


@router.get("/trips/{trip_id}/events")
async def trip_events(
    trip_id: str, request: Request, recorder: Recorder, order: Literal["time", "worst"] = "time"
) -> list[RiskEvent]:
    """The risky moments of a trip, with a video clip and a thumbnail when video was streamed.

    `order=worst` puts the most costly moments first (biggest score drop, then model risk, then length).
    """
    try:
        rows = await recorder.events(trip_id)
    except RecordingUnavailable as e:
        raise _unavailable(e) from e
    if rows is None:
        raise _not_recorded(trip_id)
    if order == "worst":
        rows.sort(key=lambda r: (r["score_drop"], r["peak_risk"] or 0.0, r["duration_s"]), reverse=True)

    def media_url(key: str | None) -> str | None:
        return str(request.url_for("get_media", key=key)) if key else None

    return [_event(row, media_url) for row in rows]


def _event(row: dict[str, Any], media_url) -> RiskEvent:
    return RiskEvent.model_validate({
        **row,
        "event_id": row["id"],
        "video_url": media_url(row["video_key"]),
        "thumbnail_url": media_url(row["thumbnail_key"]),
    })


@router.get(
    "/media/{key:path}",
    name="get_media",
    response_class=Response,
    responses={200: {"content": {"video/mp4": {}, "image/jpeg": {}}}, 206: {"description": "Partial content"}},
)
async def get_media(key: str, request: Request, recorder: Recorder) -> Response:
    """A stored clip or thumbnail, streamed from S3 (supports Range, so video players can seek)."""
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
