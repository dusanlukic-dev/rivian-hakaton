"""The server's storage: what the coordinator delivers goes to Postgres (rows) and S3 (images).

    POST /internal/trips/{id}/sync ──► TripStore.sync
        trip meta        ──► trips (insert once)
        section images   ──► S3 sections/<trip>/<section>.jpg  (best effort: without S3 the row is stored without it)
        sections         ──► trip_sections (one row each, already stored ones skipped)
        running summary  ──► trips (the TripSummary numbers; ended_at once the trip is over)

    history, report, analytics, media ──► reads below

If Postgres is down, `sync` raises StorageUnavailable (HTTP 503): the coordinator keeps the data and retries.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from typing import Any

from app.core.config import Settings, get_settings
from app.schemas.sync import SyncResult, TripSync
from app.server.repositories.database import Database, get_database
from app.server.repositories.media import MediaStore, S3MediaStore
from app.server.repositories.recordings import RecordingRepository

logger = logging.getLogger(__name__)


class StorageUnavailable(Exception):
    """Recording is off, or Postgres / S3 can't be reached right now."""


def _reason(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}".splitlines()[0][:200]


def image_key(trip_id: str, section_id: str) -> str:
    return f"sections/{trip_id}/{section_id}.jpg"


class TripStore:
    def __init__(self, repo: RecordingRepository | None, media: MediaStore | None) -> None:
        self.repo, self.media = repo, media
        self._bucket_ready = False
        self._bucket_lock = asyncio.Lock()
        self._s3_down = False

    @property
    def enabled(self) -> bool:
        return self.repo is not None

    # ---- lifecycle ----

    async def start(self) -> None:
        """Say in the server log right away whether Postgres and S3 are up."""
        if self.repo is None:
            logger.info("Trip storage is off (RECORDING_ENABLED=false): no history, reports or logins")
            return
        try:
            await self.repo.db.ensure_schema()
            logger.info("Server stores trips in Postgres %s", self.repo.description)
        except Exception as e:
            logger.warning(
                "Postgres %s unreachable (%s): the coordinator keeps its summaries until it is up",
                self.repo.description, _reason(e),
            )
        if self.media is None:
            return
        try:
            await self._ensure_bucket()
            logger.info("Dangerous-moment images go to %s", self.media.description)
        except Exception as e:
            logger.warning("Object storage %s unreachable (%s): sections are stored without images",
                           self.media.description, _reason(e))

    # ---- writes (from the coordinator) ----

    async def sync(self, trip_id: str, body: TripSync) -> SyncResult:
        repo = self._repo()
        keys: dict[str, str] = {}
        for section in body.sections:
            if section.image_jpeg:
                key = await self._put_image(image_key(trip_id, section.section_id), section.image_jpeg)
                if key is not None:
                    keys[section.section_id] = key
        meta = body.trip
        trip_row = {
            "id": trip_id,
            "user_id": meta.user_id,
            "driver_id": meta.driver_id,
            "started_at": meta.started_at,
            "emergency_contact": meta.emergency_contact.model_dump() if meta.emergency_contact else None,
            "speed_scenario": meta.speed_scenario,
            "section_s": meta.section_s,
        }
        rows = [self._section_row(trip_id, section, keys.get(section.section_id)) for section in body.sections]
        summary = body.summary.model_dump(mode="python") if body.summary else None
        try:
            await repo.sync(trip_row, rows, summary)
        except Exception as e:
            raise self._failed(e) from e
        return SyncResult(sections=len(rows), images=len(keys))

    async def close_interrupted(self, keep: Iterable[str]) -> int:
        try:
            return await self._repo().close_interrupted(set(keep))
        except StorageUnavailable:
            raise
        except Exception as e:
            raise self._failed(e) from e

    @staticmethod
    def _section_row(trip_id: str, section, key: str | None) -> dict[str, Any]:
        row = section.model_dump(mode="python", exclude={"image_jpeg", "section_id", "trip_id"})
        row.update(id=section.section_id, trip_id=trip_id, image_key=key)
        if key is None:
            row["image_t"] = None
        return row

    async def _put_image(self, key: str, jpeg: bytes) -> str | None:
        if self.media is None:
            return None
        try:
            await self._ensure_bucket()
            await asyncio.to_thread(self.media.put, key, jpeg, "image/jpeg")
        except Exception as e:
            self._bucket_ready = False  # check the bucket again next time
            if not self._s3_down:
                self._s3_down = True
                logger.warning("Object storage %s unreachable (%s): sections are stored without images",
                               self.media.description, _reason(e))
            return None
        if self._s3_down:
            self._s3_down = False
            logger.info("Object storage %s is back: images are stored again", self.media.description)
        return key

    async def _ensure_bucket(self) -> None:
        async with self._bucket_lock:  # images of one batch must not all create the bucket
            if not self._bucket_ready:
                await asyncio.to_thread(self.media.ensure_bucket)
                self._bucket_ready = True

    # ---- reads (history, report, analytics, media) ----

    async def trip(self, trip_id: str) -> dict[str, Any] | None:
        return await self._read(self._repo().trip(trip_id))

    async def trips(self, user_id: str | None = None, driver_id: str | None = None) -> list[dict[str, Any]]:
        return await self._read(self._repo().trips(user_id, driver_id))

    async def all_trips(self) -> list[dict[str, Any]]:
        return await self._read(self._repo().all_trips())

    async def sections(self, trip_id: str, after_seq: int | None = None) -> list[dict[str, Any]]:
        return await self._read(self._repo().sections(trip_id, after_seq))

    async def media_object(self, key: str) -> tuple[bytes, str] | None:
        if self.media is None:
            raise StorageUnavailable("Image storage is off (RECORDING_ENABLED=false)")
        try:
            return await asyncio.to_thread(self.media.get, key)
        except Exception as e:
            raise StorageUnavailable(f"Image storage is unreachable ({_reason(e)})") from e

    # ---- helpers ----

    def _repo(self) -> RecordingRepository:
        if self.repo is None:
            raise StorageUnavailable("Trip storage is off (RECORDING_ENABLED=false)")
        return self.repo

    async def _read(self, call):
        try:
            return await call
        except Exception as e:
            raise self._failed(e) from e

    def _failed(self, error: Exception) -> StorageUnavailable:
        logger.warning("Postgres %s failed (%s)", self.repo.description if self.repo else "-", _reason(error))
        return StorageUnavailable(f"Postgres is unreachable ({_reason(error)})")


def build_store(settings: Settings, db: Database) -> TripStore:
    if not settings.recording_enabled:
        return TripStore(repo=None, media=None)
    media = S3MediaStore(
        settings.s3_endpoint_url,
        settings.s3_access_key,
        settings.s3_secret_key,
        settings.s3_bucket,
        settings.s3_region,
        public_read=settings.s3_public_read,
    )
    return TripStore(RecordingRepository(db), media)


_store: TripStore | None = None


def get_trip_store() -> TripStore:
    global _store
    if _store is None:
        _store = build_store(get_settings(), get_database())
    return _store
