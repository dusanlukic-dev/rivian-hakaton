"""The coordinator: the in-car half of the backend. Everything live goes through here.

    camera ──JPEG──► on_video_frame ─┬─► VideoCache (5 min)
                                     └─► ModelLink ──► model worker ──evidence──► on_detection
                                                                                     │ RiskEngine (CV team's math)
    simulator ──POST /telemetry──────────────────────────────────────────────────────┤
                                                                                     ▼
                                speed (mock / phone) ──► on_tick: score + car response (scoring.py, alerts.py)
                                                           ├─► WS `state` (~2/s) / `emergency` ──► phone, dashboard
                                                           └─► SectionRecorder (2 s) ──► closed section
                                                                 ├─► image of the riskiest frame (VideoCache)
                                                                 ├─► WS `section` ──► phone (live detail)
                                                                 └─► ServerOutbox ──► server (Postgres + S3)

The coordinator never touches the database or S3: trips, sections, images and the running summary reach the
server through `ServerOutbox` / `ServerClient` (HTTP; in-process when both run in one process). Logins are
checked by asking the server (`GET /auth/me`).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from app.coordinator.repositories.trips import InMemoryTripRepository, get_trip_repository
from app.coordinator.services import trips as trip_service
from app.coordinator.services.live import LiveHub, get_live_hub
from app.coordinator.services.model_link import Detection, Frame, ModelLink
from app.coordinator.services.outbox import ServerOutbox
from app.coordinator.services.risk_engine import RiskEngine, load_risk_config
from app.coordinator.services.sections import ClosedSection, SectionRecorder
from app.coordinator.services.server_client import ServerClient
from app.coordinator.services.speed import SpeedService, get_speed_service
from app.coordinator.services.video import shrink_jpeg
from app.coordinator.services.video_cache import VideoCache
from app.core.config import Settings, get_settings
from app.domain.enums import DangerLevel, LiveEvent
from app.domain.levels import level_for
from app.domain.trip import Trip
from app.schemas.auth import User
from app.schemas.camera import ModelFrame
from app.schemas.report import SectionIn, TripSection
from app.schemas.sync import BehaviorTotal, RunningSummary, TripMeta
from app.schemas.trip import TelemetryTick, TripCreate, TripState, TripSummary

logger = logging.getLogger(__name__)

IMAGE_MAX_GAP_S = 1.5  # nearest cached frame to the riskiest tick, if the exact frame isn't cached


def running_summary(trip: Trip) -> RunningSummary:
    stats = sorted(trip.stats.items(), key=lambda item: (-item[1].total_seconds, item[0]))
    return RunningSummary(
        duration_s=round(trip.elapsed_s, 1),
        final_score=round(trip.score, 1),
        average_score=round(trip.average_score, 1),
        min_score=round(trip.min_score, 1),
        level=level_for(trip.score),
        emergency_alert_sent=trip.emergency_alert_sent,
        behaviors=[
            BehaviorTotal(behavior=b, occurrences=s.occurrences, total_seconds=round(s.total_seconds, 1))
            for b, s in stats
        ],
        ended_at=trip.ended_at,
    )


def _signature(state: TripState) -> tuple:
    """What the phone reacts to: a change goes out at once, even between throttled `state` messages."""
    r = state.response
    camera_alert = state.camera.alert if state.camera else None
    return (state.level, r.dashboard_light, r.vibrate_seat, r.sound, frozenset(state.active_behaviors), camera_alert)


class _Rate:
    """Events per second over the last few seconds (camera fps for the status endpoint)."""

    def __init__(self, window_s: float = 3.0) -> None:
        self.window_s = window_s
        self._times: deque[float] = deque()

    def add(self, now: float) -> None:
        self._times.append(now)
        while self._times and self._times[0] < now - self.window_s:
            self._times.popleft()

    def per_second(self, now: float) -> float:
        while self._times and self._times[0] < now - self.window_s:
            self._times.popleft()
        return round(len(self._times) / self.window_s, 1)

    @property
    def last(self) -> float | None:
        return self._times[-1] if self._times else None


class Coordinator:
    def __init__(
        self,
        repo: InMemoryTripRepository,
        hub: LiveHub,
        speed: SpeedService,
        settings: Settings,
        *,
        clock: Callable[[], float] = time.monotonic,
        video: VideoCache | None = None,
        outbox: ServerOutbox | None = None,
        risk_config: dict | None = None,
        housekeeping_s: float = 0.5,
    ) -> None:
        self.repo, self.hub, self.speed, self.cfg = repo, hub, speed, settings
        self.clock = clock
        self.video = video or VideoCache(
            mode=settings.video_cache,
            path=settings.video_cache_path,
            retention_s=settings.video_cache_s,
            max_fps=settings.video_cache_fps,
            max_mb=settings.video_cache_max_mb,
            clock=clock,
        )
        self.sections = SectionRecorder(settings.section_s)
        self.outbox = outbox or ServerOutbox()
        self.model = ModelLink(clock=clock)
        self.model.on_detection = self._on_detection
        self.model.on_frame_sent = self._keep_analysed_frame
        self.server: ServerClient | None = None
        self.housekeeping_s = housekeeping_s
        self._risk_config = risk_config
        self._risk_error: str | None = None
        self._engines: dict[str, RiskEngine] = {}
        self._trip_wall0: dict[str, float] = {}
        self._last_state_at = float("-inf")
        self._last_signature: tuple | None = None
        self._camera = _Rate()
        self._camera_clients = 0
        self._housekeeper: asyncio.Task | None = None
        # monotonic clock -> local wall time, for the timestamps of model ticks (local: night penalties)
        self._ref = (datetime.now().astimezone(), clock())

    # ---------------- lifecycle ----------------

    async def start(self, server: ServerClient) -> None:
        self.server = server
        self.video.open()
        if self._risk_config is None:
            try:
                self._risk_config = load_risk_config(self.cfg.risk_config_file)
                logger.info("Risk engine (CV team's model) uses %s", self.cfg.risk_config_file)
            except Exception as e:
                self._risk_error = f"{type(e).__name__}: {e}"
                logger.warning(
                    "Can't load the risk config %s (%s): model detections won't be scored. Set RISK_CONFIG_PATH.",
                    self.cfg.risk_config_file, self._risk_error,
                )
        self.outbox.start(server)
        self.outbox.close_interrupted(keep=[t.id for t in self.repo.list() if t.ended_at is None])
        if self.housekeeping_s > 0:
            self._housekeeper = asyncio.create_task(self._housekeeping(), name="coordinator-housekeeping")
        logger.info("Coordinator ready: sections of %.1f s, server %s", self.cfg.section_s, server.description)

    async def stop(self) -> None:
        if self._housekeeper is not None:
            self._housekeeper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._housekeeper
            self._housekeeper = None
        # Trips still running stay open on the server; the next start asks it to close them.
        for trip in self.repo.list():
            if trip.ended_at is None:
                closed = self.sections.close(trip.id)
                if closed is not None:
                    await self._emit_section(trip, closed)
        await self.outbox.stop(timeout=5.0)
        self.video.close()

    # ---------------- trips ----------------

    async def start_trip(self, body: TripCreate, user: User | None) -> TripState:
        """Raises trip_service.MissingDriver without login and driver_id."""
        trip, previous = trip_service.start_trip(self.repo, body, user)
        if previous is not None:
            await self._finish(previous, wait=False)
        wall = self.clock()
        self._trip_wall0[trip.id] = wall
        self.sections.start(trip)
        if self._risk_config is not None:
            self._engines[trip.id] = RiskEngine(self._risk_config)
        contact = trip.emergency_contact
        self.outbox.trip(TripMeta(
            trip_id=trip.id,
            driver_id=trip.driver_id,
            user_id=trip.user_id,
            started_at=trip.started_at,
            emergency_contact={"name": contact.name, "phone": contact.phone} if contact else None,
            speed_scenario=self.speed.scenario_for(trip.id).name,
            section_s=self.cfg.section_s,
        ))
        self.outbox.summary(trip.id, running_summary(trip))
        await self.model.trip_started(trip.id, wall)
        self._last_signature = None
        state = trip_service.to_state(trip)
        await self.hub.broadcast(LiveEvent.TRIP_STARTED, state)
        return state

    async def end_trip(self, trip: Trip) -> TripSummary:
        if trip_service.end_trip(trip):
            await self._finish(trip, wait=True)
        return trip_service.to_summary(trip)

    async def _finish(self, trip: Trip, wait: bool) -> None:
        """The trip has its ended_at: close its last section, tell the server and the phone."""
        closed = self.sections.close(trip.id)
        if closed is not None:
            await self._emit_section(trip, closed)
        self.sections.forget(trip.id)
        self.outbox.summary(trip.id, running_summary(trip), ended=True)
        self.speed.end_trip(trip.id)
        self._engines.pop(trip.id, None)
        self._trip_wall0.pop(trip.id, None)
        await self.model.trip_ended(trip.id)
        await self.hub.broadcast(LiveEvent.TRIP_ENDED, trip_service.to_summary(trip))
        if wait and self.outbox.server_ok:
            # Read your own writes: the report the app opens right after "End" has the whole trip.
            await self.outbox.flush(timeout=3.0)

    # ---------------- ticks ----------------

    async def on_tick(
        self,
        trip: Trip,
        tick: TelemetryTick,
        *,
        frame_wall: float | None = None,
        frame_id: int | None = None,
        throttle: bool = False,
    ) -> TripState:
        """Score one tick and push it out. `throttle`: model detections (5-10/s) reach the phone ~2/s."""
        now = self.clock()
        reading = self.speed.resolve(trip.id, tick.timestamp, tick.speed_kmh)
        score_before = trip.score
        emergency = trip_service.process_tick(trip, tick, reading.speed_kmh, reading.source)
        closed = self.sections.on_tick(
            trip, tick.timestamp, reading, score_before,
            wall=frame_wall if frame_wall is not None else now, frame_id=frame_id, emergency=emergency,
        )
        state = trip_service.to_state(trip)
        signature = _signature(state)
        due = now - self._last_state_at >= self.cfg.live_state_interval_s
        if not throttle or emergency or due or signature != self._last_signature:
            self._last_state_at, self._last_signature = now, signature
            await self.hub.broadcast(LiveEvent.STATE, state)
        if emergency:
            await self.hub.broadcast(LiveEvent.EMERGENCY, state)
        if closed is not None:
            await self._emit_section(trip, closed)
        return state

    async def _emit_section(self, trip: Trip, closed: ClosedSection) -> None:
        image = None
        if closed.danger is not DangerLevel.NONE:
            image = await self._section_image(closed)
        fields = dict(closed.fields)
        if image is not None:
            fields["image_t"] = closed.peak_t
        await self.hub.broadcast(LiveEvent.SECTION, TripSection(**fields, has_image=image is not None, image_url=None))
        self.outbox.section(trip.id, SectionIn(**fields, image_jpeg=image))
        self.outbox.summary(trip.id, running_summary(trip), ended=trip.ended_at is not None)

    async def _section_image(self, closed: ClosedSection) -> bytes | None:
        jpeg = None
        if closed.peak_frame_id is not None:
            jpeg = self.video.get(closed.peak_frame_id)
        if jpeg is None and closed.peak_wall is not None:
            hit = self.video.nearest(closed.peak_wall, IMAGE_MAX_GAP_S)
            if hit is not None:
                jpeg = self.video.get(hit[0])
        if jpeg is None:
            return None
        try:
            return await asyncio.to_thread(shrink_jpeg, jpeg, self.cfg.section_image_width)
        except Exception as e:  # not decodable: send the frame as it came
            logger.debug("Couldn't scale a section image (%s)", e)
            return jpeg

    # ---------------- camera + model ----------------

    def camera_connected(self, delta: int) -> None:
        self._camera_clients = max(self._camera_clients + delta, 0)

    def on_video_frame(self, jpeg: bytes) -> bool:
        """One camera JPEG. False if no trip is active (the frame is dropped)."""
        if self.repo.active() is None:
            return False
        now = self.clock()
        self._camera.add(now)
        frame = Frame(self.video.new_frame_id(), now, jpeg)
        if self.video.wants(now):
            self.video.add(frame.frame_id, now, jpeg)
        self.model.submit(frame)
        return True

    def _keep_analysed_frame(self, frame: Frame) -> None:
        self.video.add(frame.frame_id, frame.wall, frame.jpeg)  # no-op if it is cached already

    async def _on_detection(self, detection: Detection) -> None:
        trip = self.repo.active()
        if trip is None or trip.id != detection.trip_id:
            return
        engine = self._engines.get(trip.id)
        if engine is None:
            return  # no risk config: logged at start
        t = detection.wall - self._trip_wall0.get(trip.id, detection.wall)
        record, _events = engine.step(t, detection.evidence)
        frame = ModelFrame.model_validate({**record, "frame": detection.frame_id})
        tick = TelemetryTick(timestamp=self._local_time(detection.wall), frame=frame)
        await self.on_tick(trip, tick, frame_wall=detection.wall, frame_id=detection.frame_id, throttle=True)

    def _local_time(self, wall: float) -> datetime:
        ref_time, ref_wall = self._ref
        return ref_time + timedelta(seconds=wall - ref_wall)

    # ---------------- housekeeping ----------------

    async def housekeeping_once(self) -> None:
        now = self.clock()
        self.model.check_timeouts(now)
        for trip_id, closed in self.sections.sweep(now):
            trip = self.repo.get(trip_id)
            if trip is not None:
                await self._emit_section(trip, closed)

    async def _housekeeping(self) -> None:
        while True:
            await asyncio.sleep(self.housekeeping_s)
            try:
                await self.housekeeping_once()
            except Exception:
                logger.exception("Coordinator housekeeping failed; continuing")

    def status(self) -> dict:
        now = self.clock()
        trip = self.repo.active()
        last_frame = self._camera.last
        return {
            "trip_id": trip.id if trip else None,
            "section_s": self.cfg.section_s,
            "camera": {
                "stream_clients": self._camera_clients,
                "fps": self._camera.per_second(now),
                "last_frame_age_s": round(now - last_frame, 1) if last_frame is not None else None,
            },
            "model": self.model.status(),
            "risk_engine": {
                "config": str(self.cfg.risk_config_file),
                "loaded": self._risk_config is not None,
                "error": self._risk_error,
            },
            "video_cache": self.video.stats(),
            "server": {
                "target": self.server.description if self.server else None,
                "reachable": self.outbox.server_ok,
                "pending_sections": self.outbox.pending_sections,
                "delivered_sections": self.outbox.delivered_sections,
                "delivered_images": self.outbox.delivered_images,
                "last_error": self.outbox.last_error,
            },
            "time": datetime.now(timezone.utc),
        }


_coordinator: Coordinator | None = None


def get_coordinator() -> Coordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = Coordinator(get_trip_repository(), get_live_hub(), get_speed_service(), get_settings())
    return _coordinator
