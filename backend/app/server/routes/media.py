"""Stored images (server), streamed from S3 through the API port (8000 is reachable over the hotspot; 9000 isn't)."""

import re

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.server.deps import Store
from app.server.services.storage import StorageUnavailable

router = APIRouter(tags=["media (server)"])

_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


@router.get(
    "/media/{key:path}",
    name="get_media",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}, "video/mp4": {}}}, 206: {"description": "Partial content"}},
)
async def get_media(key: str, request: Request, store: Store) -> Response:
    """A stored image (or a future clip). Supports Range, so video players can seek.

    Not behind login: the keys are random ids, known only to whoever may read the trip's report.
    """
    try:
        obj = await store.media_object(key)
    except StorageUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
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
