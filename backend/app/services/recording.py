"""Records every trip in the background, next to the live path, for the driver's report.

    telemetry tick ─┬─► sample window (1 s) ──────────────────────► trip_samples
                    └─► risky moment ─────────────────────────────► risk_events
    JPEG frame ─────► frame buffer (a few s) ─► clip per moment ──► S3 clips/<trip>/<event>.mp4 + .jpg

The routes call `trip_started`, `on_tick`, `on_video_frame` and `trip_ended`. Those only touch
memory, so a slow or dead database never delays the car's reactions. A background task writes to
Postgres every couple of seconds. If Postgres is down, the rows wait in memory (capped) and go out
once it is back. Clips are encoded to MP4 in a worker thread and uploaded to S3.

A risky moment: the car is moving and a scored behavior is visible, or the camera model raised a
red alert. Detections less than `event_merge_gap_s` apart belong to the same moment.
"""

import asyncio
import contextlib
import logging
import math
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.exc import DataError, IntegrityError, ProgrammingError

from app.core.config import Settings, get_settings
from app.domain.enums import Behavior, DashboardLight, SoundLevel, SpeedSource
from app.domain.trip import CameraCategory, Trip
from app.repositories.media import MediaStore, S3MediaStore
from app.repositories.recordings import EVENT, SAMPLE, TRIP_END, TRIP_START, RecordingDatabase
from app.services.alerts import level_for
from app.services.scoring import DEFAULT_CONFIG as SCORING
from app.services.speed import SpeedReading
from app.services.video import clip_fps, encode_mp4

logger = logging.getLogger(__name__)

_LIGHT_RANK = {DashboardLight.GREEN: 0, DashboardLight.GREEN_YELLOW: 1, DashboardLight.YELLOW: 2, DashboardLight.RED: 3}
_SOUND_RANK = {SoundLevel.NONE: 0, SoundLevel.LOW: 1, SoundLevel.HIGH: 2}
_ALERT_RANK = {"green": 0, "yellow": 1, "red": 2}
_REFUSED = (IntegrityError, DataError, ProgrammingError)  # Postgres answered and said no


@dataclass
class RecordingConfig:
    sample_window_s: float = 1.0  # ticks come ~2/s; maxima are kept too, so short spikes survive
    flush_interval_s: float = 2.0
    max_pending_writes: int = 20_000  # ~5 h of samples while Postgres is down; the oldest go first
    event_merge_gap_s: float = 2.0  # risky again within this gap = the same moment (model flicker)
    event_max_s: float = 30.0  # longer moments are split, so the clips stay short
    clip_pre_roll_s: float = 3.0  # video kept from before the moment...
    clip_post_roll_s: float = 2.0  # ...and after it (<= event_merge_gap_s: already buffered at close)
    clip_min_event_s: float = 1.0  # shorter moments get a row but no clip, unless the model alert was red
    max_clips_per_trip: int = 50
    max_buffered_frames: int = 600  # hard cap on frames held in memory (~1 min at 10 fps)


class RecordingUnavailable(Exception):
    """Recording is off, or its storage can't be reached right now."""


def _max(a: float | None, b: float | None) -> float | None:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def _to_utc(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)  # a naive timestamp counts as the laptop's local time


def _reason(error: BaseException) -> str:
    text = f"{type(error).__name__}: {error}".splitlines()[0]
    return text[:200]


def _alert_rank(alert: str | None) -> int:
    return _ALERT_RANK.get(alert, -1) if alert else -1


@dataclass
class _CategoryAgg:
    p_sum: float = 0.0
    p_n: int = 0
    p_max: float | None = None
    active: bool = False
    r_max: float | None = None
    run_s_max: float | None = None

    def add(self, category: CameraCategory) -> None:
        if category.p is not None:
            self.p_sum += category.p
            self.p_n += 1
        self.p_max = _max(self.p_max, category.p)
        self.active = self.active or category.active
        self.r_max = _max(self.r_max, category.r)
        self.run_s_max = _max(self.run_s_max, category.run_s)

    def out(self) -> dict[str, Any]:
        p = round(self.p_sum / self.p_n, 3) if self.p_n else None
        return {"p": p, "p_max": self.p_max, "active": self.active, "r": self.r_max, "run_s": self.run_s_max}


@dataclass
class _Window:
    """Ticks of one sample window, folded into one trip_samples row."""

    index: int
    start: datetime
    t: float
    ticks: int = 0
    speed_sum: float = 0.0
    speed_max: float = 0.0
    speed_source: SpeedSource = SpeedSource.MOCK
    score: float = 0.0
    score_min: float = math.inf
    behaviors: set[Behavior] = field(default_factory=set)
    risk_sum: float = 0.0
    risk_n: int = 0
    risk_max: float | None = None
    alert: str | None = None
    rules: set[str] = field(default_factory=set)
    categories: dict[str, _CategoryAgg] = field(default_factory=dict)
    groups: dict[str, float | None] = field(default_factory=dict)
    light: DashboardLight = DashboardLight.GREEN
    vibrate: bool = False
    sound: SoundLevel = SoundLevel.NONE
    lat: float | None = None
    lon: float | None = None

    def add(self, trip: Trip, speed: SpeedReading) -> None:
        self.ticks += 1
        self.speed_sum += speed.speed_kmh
        self.speed_max = max(self.speed_max, speed.speed_kmh)
        self.speed_source = speed.source
        self.score = trip.score
        self.score_min = min(self.score_min, trip.score)
        self.behaviors.update(trip.active)

        response = trip.response
        if _LIGHT_RANK.get(response.dashboard_light, 0) > _LIGHT_RANK[self.light]:
            self.light = response.dashboard_light
        if _SOUND_RANK.get(response.sound, 0) > _SOUND_RANK[self.sound]:
            self.sound = response.sound
        self.vibrate = self.vibrate or response.vibrate_seat

        camera = trip.camera
        if camera is not None:
            if camera.risk is not None:
                self.risk_sum += camera.risk
                self.risk_n += 1
            self.risk_max = _max(self.risk_max, camera.risk)
            if _alert_rank(camera.alert) > _alert_rank(self.alert):
                self.alert = camera.alert
            self.rules.update(camera.rules_triggered)
            for name, category in camera.categories.items():
                self.categories.setdefault(name, _CategoryAgg()).add(category)
            for name, value in camera.groups.items():
                self.groups[name] = _max(self.groups.get(name), value)
        if speed.lat is not None:
            self.lat, self.lon = speed.lat, speed.lon

    def row(self, trip_id: str) -> dict[str, Any]:
        return {
            "trip_id": trip_id,
            "ts": self.start,
            "t": round(self.t, 3),
            "ticks": self.ticks,
            "speed_kmh": round(self.speed_sum / self.ticks, 1),
            "speed_max_kmh": round(self.speed_max, 1),
            "speed_source": self.speed_source.value,
            "score": round(self.score, 1),
            "score_min": round(self.score_min, 1),
            "level": level_for(self.score).value,
            "behaviors": sorted(b.value for b in self.behaviors),
            "risk": round(self.risk_sum / self.risk_n, 3) if self.risk_n else None,
            "risk_max": self.risk_max,
            "alert": self.alert,
            "rules_triggered": sorted(self.rules),
            "categories": {name: agg.out() for name, agg in sorted(self.categories.items())},
            "groups": dict(sorted(self.groups.items())),
            "dashboard_light": self.light.value,
            "vibrate_seat": self.vibrate,
            "sound": self.sound.value,
            "lat": self.lat,
            "lon": self.lon,
        }


@dataclass
class _Event:
    """A risky moment in progress."""

    id: str
    started_at: datetime
    t_start: float
    wall_start: float  # monotonic clock: cuts the clip out of the frame buffer
    score_start: float  # score just before the moment
    last_risky_at: datetime | None = None
    wall_last_risky: float = 0.0
    duration_s: float = 0.0
    behavior_seconds: dict[Behavior, float] = field(default_factory=dict)
    categories: dict[str, float] = field(default_factory=dict)  # active model category -> peak p
    rules: set[str] = field(default_factory=set)
    alert: str | None = None
    peak_risk: float | None = None
    peak: tuple[float, float] | None = None  # (model risk, score lost on that tick): the thumbnail frame
    wall_peak: float = 0.0
    score_min: float = math.inf
    score_end: float = 0.0
    speed_sum: float = 0.0
    speed_n: int = 0
    speed_max: float = 0.0
    lat: float | None = None
    lon: float | None = None

    def add(self, trip: Trip, ts: datetime, wall: float, dt: float, speed: SpeedReading, score_before: float) -> None:
        self.last_risky_at, self.wall_last_risky = ts, wall
        self.duration_s += dt
        for behavior in trip.active:
            self.behavior_seconds[behavior] = self.behavior_seconds.get(behavior, 0.0) + dt

        risk = None
        camera = trip.camera
        if camera is not None:
            risk = camera.risk
            self.peak_risk = _max(self.peak_risk, risk)
            if _alert_rank(camera.alert) > _alert_rank(self.alert):
                self.alert = camera.alert
            self.rules.update(camera.rules_triggered)
            for name, category in camera.categories.items():
                if category.active:
                    self.categories[name] = max(self.categories.get(name, 0.0), category.p or 0.0)

        severity = (risk if risk is not None else -1.0, score_before - trip.score)
        if self.peak is None or severity > self.peak:
            self.peak, self.wall_peak = severity, wall
            if speed.lat is not None:
                self.lat, self.lon = speed.lat, speed.lon
        self.score_min = min(self.score_min, trip.score)
        self.score_end = trip.score
        self.speed_sum += speed.speed_kmh
        self.speed_n += 1
        self.speed_max = max(self.speed_max, speed.speed_kmh)

    def row(self, trip_id: str) -> dict[str, Any]:
        by_time = sorted(self.behavior_seconds.items(), key=lambda item: item[1], reverse=True)
        by_p = sorted(self.categories.items(), key=lambda item: item[1], reverse=True)
        return {
            "id": self.id,
            "trip_id": trip_id,
            "started_at": self.started_at,
            "ended_at": self.last_risky_at,
            "t_start": round(self.t_start, 3),
            "duration_s": round(self.duration_s, 1),
            "behaviors": [behavior.value for behavior, _ in by_time],
            "behavior_seconds": {behavior.value: round(seconds, 1) for behavior, seconds in by_time},
            "categories": {name: round(p, 3) for name, p in by_p},
            "rules_triggered": sorted(self.rules),
            "alert": self.alert,
            "peak_risk": self.peak_risk,
            "score_start": round(self.score_start, 1),
            "score_end": round(self.score_end, 1),
            "score_min": round(self.score_min, 1),
            "score_drop": round(max(self.score_start - self.score_min, 0.0), 1),
            "level": level_for(self.score_min).value,
            "speed_avg_kmh": round(self.speed_sum / self.speed_n, 1) if self.speed_n else 0.0,
            "speed_max_kmh": round(self.speed_max, 1),
            "lat": self.lat,
            "lon": self.lon,
            "video_key": None,
            "thumbnail_key": None,
            "clip_duration_s": None,
        }


@dataclass
class _TripRecording:
    trip_id: str
    last_score: float
    t0: datetime | None = None  # the first tick: t = 0 on the report's time axis
    last_tick_at: datetime | None = None
    wall_last_tick: float = 0.0
    window: _Window | None = None
    event: _Event | None = None
    clips: int = 0


class TripRecorder:
    def __init__(
        self,
        db: RecordingDatabase | None,
        media: MediaStore | None,
        cfg: RecordingConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
        encoder: Callable[[list[bytes], float], bytes] = encode_mp4,
    ) -> None:
        self.db, self.media = db, media
        self.cfg = cfg or RecordingConfig()
        self._clock = clock
        self._encoder = encoder
        self._trips: dict[str, _TripRecording] = {}
        self._frames: deque[tuple[float, bytes]] = deque()
        self._pending: list[tuple[str, dict[str, Any]]] = []
        self._tasks: set[asyncio.Task] = set()
        # One database user at a time: no CREATE TABLE races between the startup check and the first
        # request, and the tests' in-memory SQLite (a single shared connection) stays consistent.
        self._db_lock = asyncio.Lock()
        self._bucket_lock = asyncio.Lock()
        self._wake = asyncio.Event()
        self._runner: asyncio.Task | None = None
        self._schema_ready = False
        self._bucket_ready = False
        self._db_down = False
        self._overflowing = False

    @property
    def enabled(self) -> bool:
        return self.db is not None

    # ---- lifecycle (FastAPI lifespan) ----

    async def start(self) -> None:
        if self.db is None:
            logger.info("Trip recording is off (RECORDING_ENABLED=false)")
            return
        self._runner = asyncio.create_task(self._run(), name="trip-recorder")

    async def stop(self) -> None:
        if self.db is None:
            return
        if self._runner is not None:
            self._runner.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._runner
            self._runner = None
        # Keep what was recorded so far (also on a uvicorn reload). The trip rows stay without
        # `ended_at`: those trips were interrupted, not ended.
        for rec in self._trips.values():
            self._close_open(rec)
        self._trips.clear()
        await self._wait_for_clips(timeout=30)
        await self.flush()
        await self.db.close()

    # ---- hooks for the live path: memory only, never await storage ----

    def trip_started(self, trip: Trip, speed_scenario: str | None = None) -> None:
        if self.db is None:
            return
        self._trips[trip.id] = _TripRecording(trip.id, last_score=trip.score)
        self._frames.clear()  # video from before this trip doesn't belong to it
        contact = trip.emergency_contact
        self._enqueue(TRIP_START, {
            "id": trip.id,
            "driver_id": trip.driver_id,
            "started_at": _to_utc(trip.started_at),
            "emergency_contact": {"name": contact.name, "phone": contact.phone} if contact else None,
            "speed_scenario": speed_scenario,
        })

    def on_tick(self, trip: Trip, timestamp: datetime, speed: SpeedReading) -> None:
        """Call after the tick was scored, so trip.score / active / camera / response are current."""
        if self.db is None:
            return
        rec = self._trips.get(trip.id)
        if rec is None:  # the trip started before this recorder did
            self.trip_started(trip)
            rec = self._trips[trip.id]

        ts, now = _to_utc(timestamp), self._clock()
        if rec.t0 is None:
            rec.t0 = ts
        dt = 0.0
        if rec.last_tick_at is not None:
            dt = min(max((ts - rec.last_tick_at).total_seconds(), 0.0), SCORING.max_tick_gap_s)
        if rec.last_tick_at is None or ts > rec.last_tick_at:
            rec.last_tick_at = ts
        rec.wall_last_tick = now
        t = max((ts - rec.t0).total_seconds(), 0.0)

        self._add_to_window(rec, trip, t, speed)
        self._track_event(rec, trip, ts, t, now, dt, speed)
        rec.last_score = trip.score

    def on_video_frame(self, jpeg: bytes) -> None:
        """One camera frame. Only a few seconds are kept, unless a risky moment is in progress."""
        if self.db is None or self.media is None:
            return
        now = self._clock()
        self._frames.append((now, jpeg))
        keep_from = now - self.cfg.clip_pre_roll_s
        for rec in self._trips.values():
            if rec.event is not None:
                keep_from = min(keep_from, rec.event.wall_start - self.cfg.clip_pre_roll_s)
        frames = self._frames
        while frames and (frames[0][0] < keep_from or len(frames) > self.cfg.max_buffered_frames):
            frames.popleft()

    def trip_ended(self, trip: Trip) -> None:
        if self.db is None:
            return
        rec = self._trips.pop(trip.id, None)
        if rec is not None:
            self._close_open(rec)
        self._frames.clear()
        stats = sorted(trip.stats.items(), key=lambda item: item[1].total_seconds, reverse=True)
        self._enqueue(TRIP_END, {
            "id": trip.id,
            "ended_at": _to_utc(trip.ended_at) if trip.ended_at else None,
            "duration_s": round(trip.elapsed_s, 1),
            "final_score": round(trip.score, 1),
            "average_score": round(trip.average_score, 1),
            "min_score": round(trip.min_score, 1),
            "level": level_for(trip.score).value,
            "emergency_alert_sent": trip.emergency_alert_sent,
            "behaviors": [
                {"behavior": b.value, "occurrences": s.occurrences, "total_seconds": round(s.total_seconds, 1)}
                for b, s in stats
            ],
        })
        self._wake.set()

    # ---- reads for the report endpoints ----

    async def timeline(self, trip_id: str) -> list[dict[str, Any]] | None:
        """Sample rows, oldest first. None if the trip was never recorded."""
        return await self._read(trip_id, RecordingDatabase.samples)

    async def events(self, trip_id: str) -> list[dict[str, Any]] | None:
        """Risky-moment rows, oldest first. None if the trip was never recorded."""
        return await self._read(trip_id, RecordingDatabase.events)

    async def media_object(self, key: str) -> tuple[bytes, str] | None:
        if self.media is None:
            raise RecordingUnavailable("Clip storage is off (RECORDING_ENABLED=false)")
        try:
            return await asyncio.to_thread(self.media.get, key)
        except Exception as e:
            raise RecordingUnavailable(f"Clip storage is unreachable ({_reason(e)})") from e

    # ---- writing ----

    async def flush(self) -> bool:
        """Write everything queued so far. Returns False if Postgres is unreachable (rows stay queued)."""
        if self.db is None:
            return False
        async with self._db_lock:
            if not self._pending:
                return True
            batch, self._pending = self._pending, []
            try:
                await self._ensure_schema()
                await self.db.write(batch)
            except _REFUSED as e:
                await self._write_one_by_one(batch, e)
            except Exception as e:
                self._requeue(batch)
                if not self._db_down:
                    self._db_down = True
                    logger.warning(
                        "Postgres %s unreachable (%s): the recording waits in memory until it is back",
                        self.db.description, _reason(e),
                    )
                return False
            if self._db_down:
                self._db_down = False
                logger.info("Postgres is back: the recording was written")
            return True

    async def _write_one_by_one(self, batch: list[tuple[str, dict[str, Any]]], error: Exception) -> None:
        logger.warning("Postgres refused part of the recording (%s); writing row by row", _reason(error))
        for i, op in enumerate(batch):
            try:
                await self.db.write([op])
            except _REFUSED as e:
                logger.warning("Dropped a %s row: %s", op[0], _reason(e))
            except Exception:
                self._requeue(batch[i:])
                return

    def _enqueue(self, kind: str, row: dict[str, Any]) -> None:
        self._pending.append((kind, row))
        self._cap_pending()

    def _requeue(self, batch: list[tuple[str, dict[str, Any]]]) -> None:
        self._pending[:0] = batch  # rows queued meanwhile stay after them
        self._cap_pending()

    def _cap_pending(self) -> None:
        overflow = len(self._pending) - self.cfg.max_pending_writes
        if overflow <= 0:
            self._overflowing = False
            return
        del self._pending[:overflow]
        if not self._overflowing:
            self._overflowing = True
            logger.warning("Postgres has been down too long: dropping the oldest recorded rows")

    async def _run(self) -> None:
        await self._check_storage()
        while True:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.cfg.flush_interval_s)
            except TimeoutError:
                pass
            self._wake.clear()
            try:
                self._sweep()
                await self.flush()
            except Exception:
                logger.exception("Trip recorder loop failed; retrying")

    async def _check_storage(self) -> None:
        """Say in the server log right away whether Postgres and S3 are up."""
        try:
            async with self._db_lock:
                await self._ensure_schema()
            logger.info("Recording trips to Postgres %s", self.db.description)
        except Exception as e:
            self._db_down = True
            logger.warning(
                "Postgres %s unreachable (%s): the recording waits in memory until it is up",
                self.db.description, _reason(e),
            )
        if self.media is None:
            return
        try:
            await self._ensure_bucket()
            logger.info("Risky-moment clips go to %s", self.media.description)
        except Exception as e:
            logger.warning(
                "Object storage %s unreachable (%s): risky moments are stored without clips until it is up",
                self.media.description, _reason(e),
            )

    async def _ensure_schema(self) -> None:
        """Create the tables once. The caller holds `_db_lock`."""
        if not self._schema_ready:
            await self.db.create_schema()
            self._schema_ready = True

    async def _ensure_bucket(self) -> None:
        async with self._bucket_lock:  # clips finishing together must not all create the bucket
            if not self._bucket_ready:
                await asyncio.to_thread(self.media.ensure_bucket)
                self._bucket_ready = True

    async def _read(
        self, trip_id: str, query: Callable[[RecordingDatabase, str], Awaitable[list[dict[str, Any]]]]
    ) -> list[dict[str, Any]] | None:
        if self.db is None:
            raise RecordingUnavailable("Trip recording is off (RECORDING_ENABLED=false)")
        await self._wait_for_clips(timeout=20)  # read your own writes: finished moments, then...
        if not await self.flush():  # ...everything queued so far
            raise RecordingUnavailable("Postgres is unreachable; the recording waits in memory")
        async with self._db_lock:
            try:
                await self._ensure_schema()
                if await self.db.trip(trip_id) is None:
                    return None
                return await query(self.db, trip_id)
            except Exception as e:
                raise self._read_failed(e) from e

    def _read_failed(self, error: Exception) -> RecordingUnavailable:
        logger.warning("Reading the recording failed", exc_info=error)
        return RecordingUnavailable(f"Postgres is unreachable ({_reason(error)})")

    # ---- samples, events and clips ----

    def _add_to_window(self, rec: _TripRecording, trip: Trip, t: float, speed: SpeedReading) -> None:
        width = self.cfg.sample_window_s
        index = int(t // width)
        if rec.window is not None and rec.window.index != index:
            self._enqueue(SAMPLE, rec.window.row(rec.trip_id))
            rec.window = None
        if rec.window is None:
            rec.window = _Window(index, rec.t0 + timedelta(seconds=index * width), index * width)
        rec.window.add(trip, speed)

    def _track_event(
        self, rec: _TripRecording, trip: Trip, ts: datetime, t: float, now: float, dt: float, speed: SpeedReading
    ) -> None:
        cfg = self.cfg
        moving = speed.speed_kmh >= SCORING.stationary_speed_kmh
        alarm = trip.camera is not None and trip.camera.alarm
        risky = moving and (bool(trip.active) or alarm)

        event = rec.event
        if event is not None:
            quiet_for = (ts - event.last_risky_at).total_seconds()
            too_long = (ts - event.started_at).total_seconds() >= cfg.event_max_s
            if (not risky and quiet_for >= cfg.event_merge_gap_s) or (risky and too_long):
                self._close_event(rec)
                event = None
        if not risky:
            return
        if event is None:
            event = rec.event = _Event(uuid.uuid4().hex, ts, t, now, rec.last_score)
        event.add(trip, ts, now, dt, speed, score_before=rec.last_score)

    def _sweep(self) -> None:
        """Close moments whose ticks stopped coming (camera side stopped, trip left running)."""
        now = self._clock()
        for rec in self._trips.values():
            if rec.event is not None and now - rec.wall_last_tick >= self.cfg.event_merge_gap_s:
                self._close_event(rec)

    def _close_open(self, rec: _TripRecording) -> None:
        if rec.event is not None:
            self._close_event(rec)
        if rec.window is not None:
            self._enqueue(SAMPLE, rec.window.row(rec.trip_id))
            rec.window = None

    def _close_event(self, rec: _TripRecording) -> None:
        event, rec.event = rec.event, None
        row = event.row(rec.trip_id)
        cfg = self.cfg
        frames: list[tuple[float, bytes]] = []
        wants_clip = event.duration_s >= cfg.clip_min_event_s or event.alert == "red"
        if self.media is not None and wants_clip and rec.clips < cfg.max_clips_per_trip:
            start = event.wall_start - cfg.clip_pre_roll_s
            end = event.wall_last_risky + cfg.clip_post_roll_s
            frames = [frame for frame in self._frames if start <= frame[0] <= end]
        if not frames:
            self._enqueue(EVENT, row)
            return
        rec.clips += 1
        self._spawn(self._store_clip(row, frames, event.wall_peak))

    async def _store_clip(self, row: dict[str, Any], frames: list[tuple[float, bytes]], wall_peak: float) -> None:
        key = f"clips/{row['trip_id']}/{row['id']}"
        try:
            await self._ensure_bucket()
            thumbnail = min(frames, key=lambda frame: abs(frame[0] - wall_peak))[1]
            await asyncio.to_thread(self.media.put, f"{key}.jpg", thumbnail, "image/jpeg")
            row["thumbnail_key"] = f"{key}.jpg"
            if len(frames) >= 2:
                fps = clip_fps([frame[0] for frame in frames])
                video = await asyncio.to_thread(self._encoder, [frame[1] for frame in frames], fps)
                await asyncio.to_thread(self.media.put, f"{key}.mp4", video, "video/mp4")
                row["video_key"] = f"{key}.mp4"
                row["clip_duration_s"] = round(len(frames) / fps, 1)
        except Exception as e:
            self._bucket_ready = False  # check the bucket again next time
            logger.warning("Clip for risky moment %s not stored (%s)", row["id"], _reason(e))
        finally:
            self._enqueue(EVENT, row)
            self._wake.set()

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _wait_for_clips(self, timeout: float) -> None:
        if self._tasks:
            await asyncio.wait(set(self._tasks), timeout=timeout)


def build_recorder(settings: Settings) -> TripRecorder:
    if not settings.recording_enabled:
        return TripRecorder(db=None, media=None)
    db = RecordingDatabase(settings.database_url)
    media = S3MediaStore(
        settings.s3_endpoint_url,
        settings.s3_access_key,
        settings.s3_secret_key,
        settings.s3_bucket,
        settings.s3_region,
        public_read=settings.s3_public_read,
    )
    return TripRecorder(db, media)


_recorder: TripRecorder | None = None


def get_recorder() -> TripRecorder:
    global _recorder
    if _recorder is None:
        _recorder = build_recorder(get_settings())
    return _recorder
