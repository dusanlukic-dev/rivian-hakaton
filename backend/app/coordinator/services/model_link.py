"""Live link between the coordinator and the model worker (`model/worker.py`, its own process / container).

The worker connects to the coordinator: `ws://<coordinator>:8000/api/v1/model/ws`. Dialing in means no extra
port or firewall rule on the model's side, and either side can restart; the worker reconnects on its own.

    coordinator -> worker   binary: uint32 LE header length | JSON header | JPEG
                                    header = {"type": "frame", "id": 41, "t": 12.375, "trip_id": "..."}
                            text:   {"type": "reset", "trip_id": "..."}   new trip: start the detectors fresh
                                    {"type": "idle"}                      no trip: stop sending
    worker -> coordinator   text:   {"type": "hello", "worker": "cv-pipeline", "version": "...", "categories": [...]}
                                    {"type": "detection", "id": 41, "t": 12.375, "trip_id": "...",
                                     "evidence": {"phone_use": 0.82, "eyes_off_road": 0.9, ...},
                                     "perception": {...}, "ms": 84.2}
                                    {"type": "error", "id": 41, "message": "..."}

`t` = seconds since the trip started (the worker's detectors use it as their clock). Evidence is the raw p_i per
category, what the CV team's FeatureExtractor outputs; everything after that (smoothing, durations, risk, alert,
our score) is computed by the coordinator.

Flow control: one frame in flight. New camera frames replace the waiting one (the newest frame wins), so a slow
model never builds a queue and its detections are never older than one frame. A frame without an answer for
`timeout_s` counts as lost. Only one worker is active: a new connection replaces the old one (a restarted worker
whose old socket hasn't timed out yet).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import struct
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

_HEADER = struct.Struct("<I")


def pack_frame(header: dict, jpeg: bytes) -> bytes:
    raw = json.dumps(header, separators=(",", ":")).encode()
    return _HEADER.pack(len(raw)) + raw + jpeg


def unpack_frame(data: bytes) -> tuple[dict, bytes]:
    (size,) = _HEADER.unpack_from(data)
    start = _HEADER.size
    return json.loads(data[start : start + size]), data[start + size :]


@dataclass
class Frame:
    frame_id: int
    wall: float  # coordinator's monotonic clock when the frame arrived
    jpeg: bytes


@dataclass
class Detection:
    trip_id: str
    frame_id: int
    wall: float
    evidence: dict[str, float]
    perception: dict | None
    worker_ms: float | None


@dataclass
class _Worker:
    ws: WebSocket
    connected_at: float
    name: str = "?"
    info: dict = field(default_factory=dict)
    inflight: Frame | None = None
    inflight_trip: str | None = None
    sent_at: float = 0.0


class ModelLink:
    def __init__(self, clock: Callable[[], float] = time.monotonic, timeout_s: float = 5.0) -> None:
        self._clock = clock
        self.timeout_s = timeout_s
        self.on_detection: Callable[[Detection], Awaitable[None]] | None = None
        self.on_frame_sent: Callable[[Frame], None] | None = None
        self._worker: _Worker | None = None
        self._pending: Frame | None = None
        self._work = asyncio.Event()
        self._trip_id: str | None = None
        self._t0 = 0.0
        # stats for GET /coordinator/status
        self.frames_sent = 0
        self.detections = 0
        self.replaced = 0  # frames that waited and were replaced by a newer one
        self.lost = 0
        self.latency_ms: float | None = None
        self.worker_ms: float | None = None
        self.last_detection_at: float | None = None

    # ---- state ----

    @property
    def connected(self) -> bool:
        return self._worker is not None

    @property
    def wants_frames(self) -> bool:
        return self._worker is not None and self._trip_id is not None

    def status(self) -> dict:
        worker = self._worker
        now = self._clock()
        return {
            "connected": worker is not None,
            "worker": worker.name if worker else None,
            "version": worker.info.get("version") if worker else None,
            "frames_sent": self.frames_sent,
            "detections": self.detections,
            "replaced_frames": self.replaced,
            "lost_frames": self.lost,
            "latency_ms": round(self.latency_ms, 1) if self.latency_ms is not None else None,
            "worker_ms": round(self.worker_ms, 1) if self.worker_ms is not None else None,
            "last_detection_age_s": round(now - self.last_detection_at, 1) if self.last_detection_at else None,
        }

    # ---- trips ----

    async def trip_started(self, trip_id: str, wall: float) -> None:
        self._trip_id, self._t0 = trip_id, wall
        self._pending = None
        worker = self._worker
        if worker is not None:
            worker.inflight = None  # an answer for the previous trip is ignored
            await self._send_json(worker, {"type": "reset", "trip_id": trip_id})

    async def trip_ended(self, trip_id: str) -> None:
        if self._trip_id != trip_id:
            return
        self._trip_id = None
        self._pending = None
        worker = self._worker
        if worker is not None:
            worker.inflight = None
            await self._send_json(worker, {"type": "idle"})

    # ---- frames ----

    def submit(self, frame: Frame) -> None:
        """A camera frame for the model. Replaces the frame still waiting, if any."""
        if not self.wants_frames:
            return
        if self._pending is not None:
            self.replaced += 1
        self._pending = frame
        if self._worker is not None and self._worker.inflight is None:
            self._work.set()

    def check_timeouts(self, now: float) -> None:
        worker = self._worker
        if worker is not None and worker.inflight is not None and now - worker.sent_at > self.timeout_s:
            self.lost += 1
            if self.lost == 1 or self.lost % 50 == 0:
                logger.warning("Model worker %s didn't answer within %.0f s (%d frame(s) lost so far)",
                               worker.name, self.timeout_s, self.lost)
            worker.inflight = None
            self._work.set()

    # ---- the connection (WS /model/ws) ----

    async def serve(self, ws: WebSocket) -> None:
        await ws.accept()
        worker = _Worker(ws, connected_at=self._clock())
        old, self._worker = self._worker, worker
        if old is not None:
            logger.info("A new model worker connected; closing the previous connection")
            with contextlib.suppress(Exception):
                await old.ws.close(code=4000, reason="replaced by a newer worker connection")
        pump = asyncio.create_task(self._pump(worker), name="model-link-pump")
        try:
            if self._trip_id is not None:
                await self._send_json(worker, {"type": "reset", "trip_id": self._trip_id})
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                text = message.get("text")
                if text is None:
                    continue
                try:
                    data = json.loads(text)
                except ValueError:
                    continue
                kind = data.get("type")
                if kind == "hello":
                    worker.name = str(data.get("worker") or "model")
                    worker.info = data
                    logger.info("Model worker connected: %s %s", worker.name, data.get("version") or "")
                elif kind == "detection":
                    await self._detected(worker, data)
                elif kind == "error":
                    logger.warning("Model worker %s: %s", worker.name, data.get("message"))
                    if worker.inflight is not None and data.get("id") == worker.inflight.frame_id:
                        worker.inflight = None
                        self._work.set()
        except WebSocketDisconnect:
            pass
        finally:
            pump.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pump
            if self._worker is worker:
                self._worker = None
                logger.info("Model worker %s disconnected", worker.name)

    async def _pump(self, worker: _Worker) -> None:
        while True:
            await self._work.wait()
            self._work.clear()
            if worker is not self._worker or worker.inflight is not None:
                continue
            frame, self._pending = self._pending, None
            trip_id = self._trip_id
            if frame is None or trip_id is None:
                continue
            worker.inflight, worker.inflight_trip, worker.sent_at = frame, trip_id, self._clock()
            if self.on_frame_sent is not None:
                self.on_frame_sent(frame)  # the analysed frame may become a section's image: keep it
            header = {"type": "frame", "id": frame.frame_id, "t": round(frame.wall - self._t0, 3), "trip_id": trip_id}
            try:
                await worker.ws.send_bytes(pack_frame(header, frame.jpeg))
            except Exception:
                worker.inflight = None
                return  # the receive loop sees the disconnect
            self.frames_sent += 1

    async def _detected(self, worker: _Worker, data: dict) -> None:
        frame, trip_id = worker.inflight, worker.inflight_trip
        if frame is None or data.get("id") != frame.frame_id:
            return  # an answer that came after its timeout, or for another trip
        now = self._clock()
        worker.inflight = None
        self.detections += 1
        self.last_detection_at = now
        latency = (now - worker.sent_at) * 1000
        self.latency_ms = latency if self.latency_ms is None else 0.8 * self.latency_ms + 0.2 * latency
        if isinstance(data.get("ms"), (int, float)):
            ms = float(data["ms"])
            self.worker_ms = ms if self.worker_ms is None else 0.8 * self.worker_ms + 0.2 * ms
        if self._pending is not None:
            self._work.set()
        if trip_id != self._trip_id or self.on_detection is None:
            return
        evidence = {
            str(name): float(p)
            for name, p in (data.get("evidence") or {}).items()
            if isinstance(p, (int, float)) and p == p  # drop NaN
        }
        perception = data.get("perception") if isinstance(data.get("perception"), dict) else None
        await self.on_detection(Detection(trip_id, frame.frame_id, frame.wall, evidence, perception, data.get("ms")))

    async def _send_json(self, worker: _Worker, payload: dict) -> None:
        with contextlib.suppress(Exception):
            await worker.ws.send_json(payload)
