"""Delivery of the coordinator's summaries to the server, in order, retried while the server is down.

    trip started ──► trip(meta)          ┐
    section closed ─► section(trip, s)   ├─► per-trip queue ──► one background task ──► POST /internal/trips/{id}/sync
    every section ──► summary(trip, ...) ┘    (memory, capped)     (batches of 40, the trip's meta with every call)

The live path never waits for the server: these calls only touch memory. One task delivers, one request at a
time, so a trip's sections reach the server in order. The sync call is idempotent, so a batch that timed out is
simply sent again. While the server (or its database) is down, everything waits here: up to `max_sections` per
trip and `max_image_mb` of images; past that the oldest sections go first and new images are dropped (the
section itself is still delivered). One warning when the server goes away, one line when it is back.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from dataclasses import dataclass, field
from itertools import islice

from app.coordinator.services.server_client import ServerClient, ServerRejected, ServerUnavailable
from app.schemas.report import SectionIn
from app.schemas.sync import RunningSummary, TripMeta, TripSync

logger = logging.getLogger(__name__)

BATCH = 40


@dataclass
class _TripQueue:
    meta: TripMeta
    sections: deque[SectionIn] = field(default_factory=deque)
    summary: RunningSummary | None = None
    summary_version: int = 0
    sent_version: int = 0
    ended: bool = False

    @property
    def pending(self) -> bool:
        return bool(self.sections) or self.summary_version != self.sent_version


class ServerOutbox:
    def __init__(self, interval_s: float = 1.0, max_sections: int = 10_000, max_image_mb: int = 300) -> None:
        self.interval_s = interval_s
        self.max_sections = max_sections
        self.max_image_bytes = max_image_mb * 1024 * 1024
        self._client: ServerClient | None = None
        self._trips: dict[str, _TripQueue] = {}
        self._close_keep: list[str] | None = None
        self._wake = asyncio.Event()
        self._idle = asyncio.Event()
        self._idle.set()
        self._task: asyncio.Task | None = None
        self._image_bytes = 0
        self._down = False
        self._dropping_images = False
        self.last_error: str | None = None
        self.delivered_sections = 0
        self.delivered_images = 0

    # ---- lifecycle ----

    def start(self, client: ServerClient) -> None:
        self._client = client
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="coordinator-outbox")

    async def stop(self, timeout: float = 5.0) -> None:
        await self.flush(timeout)
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self.pending:
            logger.warning("Stopping with %d undelivered section(s): the server never got them", self.pending_sections)

    # ---- enqueue (memory only, never awaits) ----

    def trip(self, meta: TripMeta) -> None:
        self._trips[meta.trip_id] = _TripQueue(meta)
        self._kick()

    def section(self, trip_id: str, section: SectionIn) -> None:
        queue = self._trips.get(trip_id)
        if queue is None:
            return
        if section.image_jpeg is not None:
            if self._image_bytes + len(section.image_jpeg) > self.max_image_bytes:
                if not self._dropping_images:
                    self._dropping_images = True
                    logger.warning("Server unreachable for too long: new section images are dropped")
                section = section.model_copy(update={"image_jpeg": None})
            else:
                self._image_bytes += len(section.image_jpeg)
        queue.sections.append(section)
        while len(queue.sections) > self.max_sections:
            self._forget_images([queue.sections.popleft()])
        self._kick()

    def summary(self, trip_id: str, summary: RunningSummary, ended: bool = False) -> None:
        queue = self._trips.get(trip_id)
        if queue is None:
            return
        queue.summary = summary
        queue.summary_version += 1
        queue.ended = queue.ended or ended
        self._kick()

    def close_interrupted(self, keep: list[str]) -> None:
        """Tell the server to close trips a crash left open (once, after the coordinator starts)."""
        self._close_keep = list(keep)
        self._kick()

    # ---- state ----

    @property
    def pending(self) -> bool:
        return self._close_keep is not None or any(q.pending for q in self._trips.values())

    @property
    def pending_sections(self) -> int:
        return sum(len(q.sections) for q in self._trips.values())

    @property
    def server_ok(self) -> bool:
        return not self._down

    async def flush(self, timeout: float) -> bool:
        """Wait (at most `timeout`) until everything queued so far reached the server."""
        if not self.pending:
            return True
        if self._task is None:
            return False
        self._wake.set()
        try:
            await asyncio.wait_for(self._idle.wait(), timeout)
        except TimeoutError:
            return False
        return True

    # ---- delivery ----

    def _kick(self) -> None:
        self._idle.clear()
        self._wake.set()

    async def _run(self) -> None:
        delay = self.interval_s
        while True:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=delay)
            except TimeoutError:
                pass
            self._wake.clear()
            try:
                ok = await self._deliver()
            except Exception:
                logger.exception("Outbox delivery failed; retrying")
                ok = False
            delay = self.interval_s if ok else min(delay * 2, 10.0)
            if not self.pending:
                self._idle.set()

    async def _deliver(self) -> bool:
        client = self._client
        if client is None:
            return False
        if self._close_keep is not None:
            try:
                closed = await client.close_interrupted(self._close_keep)
            except ServerUnavailable as e:
                self._went_down(e)
                return False
            except ServerRejected as e:
                logger.warning("Server refused to close interrupted trips: %s", e)
                closed = 0
            self._close_keep = None
            if closed:
                logger.info("Server closed %d trip(s) interrupted by the last shutdown", closed)
        for trip_id, queue in list(self._trips.items()):
            while queue.pending:
                batch = list(islice(queue.sections, BATCH))
                version = queue.summary_version
                body = TripSync(trip=queue.meta, sections=batch, summary=queue.summary)
                try:
                    result = await client.sync(trip_id, body)
                except ServerUnavailable as e:
                    self._went_down(e)
                    return False
                except ServerRejected as e:
                    logger.warning("Server rejected %d section(s) of trip %s: %s (dropped)", len(batch), trip_id, e)
                    result = None
                for item in batch:  # by identity: the size cap may have trimmed the queue meanwhile
                    if queue.sections and queue.sections[0] is item:
                        queue.sections.popleft()
                self._forget_images(batch)
                queue.sent_version = max(queue.sent_version, version)
                if result is not None:
                    self.delivered_sections += len(batch)
                    self.delivered_images += result.images
            if queue.ended and not queue.pending:
                self._trips.pop(trip_id, None)
        if self._down:
            self._down = False
            self.last_error = None
            logger.info("Server %s is back: the summaries were delivered", client.description)
        return True

    def _forget_images(self, sections: list[SectionIn]) -> None:
        for section in sections:
            if section.image_jpeg is not None:
                self._image_bytes -= len(section.image_jpeg)
        if self._image_bytes < self.max_image_bytes // 2:
            self._dropping_images = False

    def _went_down(self, error: Exception) -> None:
        self.last_error = str(error)[:300]
        if not self._down:
            self._down = True
            client = self._client.description if self._client else "?"
            logger.warning(
                "Server %s unreachable (%s): section summaries wait in the coordinator until it is back",
                client, self.last_error,
            )
