"""Section summaries: the coordinator's in-memory cache of the drive, folded every `section_s` (2 s).

    scored tick (model detection or telemetry) ──► open section: score, speed, behaviors (seconds), model
                                                   categories, car response, danger, riskiest frame so far
    first tick of the next section / trip end / ticks stop ──► ClosedSection
        └─► coordinator: image of the riskiest frame (video cache) ─► WS `section` + outbox ─► server

Why 2 s: the model scores 5-10 frames a second, so a section still averages 10-20 detections (stable "what
was detected"), a 30 min drive is 900 chart points, and a dangerous moment reaches the server and the phone
within ~2 s. `SECTION_S` changes it.

Danger of a section (only while moving, >= 5 km/h, like every penalty):
  critical   the model's red alert, the car's loud alarm (`sound: high`) or the emergency: "ultra dangerous"
  dangerous  a scored behavior was visible, the model's yellow alert, or the seat vibrated
  none       anything else
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.coordinator.services.alerts import level_for
from app.coordinator.services.scoring import DEFAULT_CONFIG as SCORING
from app.coordinator.services.speed import SpeedReading
from app.domain.enums import Behavior, DangerLevel, DashboardLight, SoundLevel, SpeedSource
from app.domain.trip import CameraCategory, Trip

_LIGHT_RANK = {DashboardLight.GREEN: 0, DashboardLight.GREEN_YELLOW: 1, DashboardLight.YELLOW: 2, DashboardLight.RED: 3}
_SOUND_RANK = {SoundLevel.NONE: 0, SoundLevel.LOW: 1, SoundLevel.HIGH: 2}
_ALERT_RANK = {"green": 0, "yellow": 1, "red": 2}
_DANGER = (DangerLevel.NONE, DangerLevel.DANGEROUS, DangerLevel.CRITICAL)


def _max(a: float | None, b: float | None) -> float | None:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def _alert_rank(alert: str | None) -> int:
    return _ALERT_RANK.get(alert, -1) if alert else -1


def _utc(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)  # a naive timestamp counts as the laptop's local time


def tick_danger(trip: Trip, speed_kmh: float, emergency: bool) -> int:
    """0 none, 1 dangerous, 2 critical, for one tick (after it was scored)."""
    if speed_kmh < SCORING.stationary_speed_kmh:
        return 0
    camera = trip.camera
    if emergency or (camera is not None and camera.alarm) or trip.response.sound == SoundLevel.HIGH:
        return 2
    if trip.active or trip.response.vibrate_seat or (camera is not None and camera.alert == "yellow"):
        return 1
    return 0


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
class _Section:
    seq: int
    t_start: float
    score_start: float
    ticks: int = 0
    score_end: float = 0.0
    score_min: float = math.inf
    emergency: bool = False
    danger: int = 0
    behaviors: dict[Behavior, float] = field(default_factory=dict)
    speed_sum: float = 0.0
    speed_max: float = 0.0
    speed_source: SpeedSource | None = None
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
    # The riskiest tick: (danger, model risk, score it cost) -> its frame becomes the section's image.
    peak_rank: tuple[int, float, float] | None = None
    peak_t: float | None = None
    peak_wall: float | None = None
    peak_frame_id: int | None = None
    last_wall: float = 0.0

    def add(
        self, trip: Trip, t: float, dt: float, speed: SpeedReading, score_before: float, emergency: bool,
        wall: float, frame_id: int | None,
    ) -> None:
        self.ticks += 1
        self.last_wall = wall
        self.score_end = trip.score
        self.score_min = min(self.score_min, trip.score)
        self.emergency = self.emergency or emergency
        for behavior in trip.active:
            self.behaviors[behavior] = self.behaviors.get(behavior, 0.0) + dt
        self.speed_sum += speed.speed_kmh
        self.speed_max = max(self.speed_max, speed.speed_kmh)
        self.speed_source = speed.source
        if speed.lat is not None:
            self.lat, self.lon = speed.lat, speed.lon

        response = trip.response
        if _LIGHT_RANK.get(response.dashboard_light, 0) > _LIGHT_RANK[self.light]:
            self.light = response.dashboard_light
        if _SOUND_RANK.get(response.sound, 0) > _SOUND_RANK[self.sound]:
            self.sound = response.sound
        self.vibrate = self.vibrate or response.vibrate_seat

        risk = None
        camera = trip.camera
        if camera is not None:
            risk = camera.risk
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

        danger = tick_danger(trip, speed.speed_kmh, emergency)
        self.danger = max(self.danger, danger)
        rank = (danger, risk if risk is not None else -1.0, score_before - trip.score)
        if self.peak_rank is None or rank > self.peak_rank:
            self.peak_rank, self.peak_t, self.peak_wall, self.peak_frame_id = rank, t, wall, frame_id


@dataclass
class ClosedSection:
    """A finished section, ready to become a SectionBase (`fields`) once the coordinator adds the image."""

    fields: dict[str, Any]
    danger: DangerLevel
    peak_t: float | None
    peak_wall: float | None
    peak_frame_id: int | None


@dataclass
class _TripSections:
    trip_id: str
    t0: datetime | None = None  # the first tick: t = 0 on the drive chart
    last_ts: datetime | None = None
    score: float = 100.0
    open: _Section | None = None


class SectionRecorder:
    def __init__(self, section_s: float = 2.0, max_tick_gap_s: float = SCORING.max_tick_gap_s) -> None:
        self.section_s = section_s
        self.max_tick_gap_s = max_tick_gap_s
        self._trips: dict[str, _TripSections] = {}

    def start(self, trip: Trip) -> None:
        self._trips[trip.id] = _TripSections(trip.id, score=trip.score)

    def forget(self, trip_id: str) -> None:
        self._trips.pop(trip_id, None)

    def on_tick(
        self,
        trip: Trip,
        timestamp: datetime,
        speed: SpeedReading,
        score_before: float,
        *,
        wall: float,
        frame_id: int | None = None,
        emergency: bool = False,
    ) -> ClosedSection | None:
        """Call after the tick was scored. Returns the section this tick closed, if any."""
        rec = self._trips.get(trip.id)
        if rec is None:  # the trip started before this recorder did
            self.start(trip)
            rec = self._trips[trip.id]
        ts = _utc(timestamp)
        if rec.t0 is None:
            rec.t0 = ts
        dt = 0.0
        if rec.last_ts is not None:
            dt = min(max((ts - rec.last_ts).total_seconds(), 0.0), self.max_tick_gap_s)
        if rec.last_ts is None or ts > rec.last_ts:
            rec.last_ts = ts
        t = max((ts - rec.t0).total_seconds(), 0.0)

        seq = int(t // self.section_s)
        closed = None
        if rec.open is not None and rec.open.seq != seq:
            closed = self._close(rec)
        if rec.open is None:
            rec.open = _Section(seq=seq, t_start=seq * self.section_s, score_start=score_before)
        rec.open.add(trip, t, dt, speed, score_before, emergency, wall, frame_id)
        rec.score = trip.score
        return closed

    def close(self, trip_id: str) -> ClosedSection | None:
        """Trip over: the open section closes as it is."""
        rec = self._trips.get(trip_id)
        return self._close(rec) if rec is not None and rec.open is not None else None

    def sweep(self, now_wall: float) -> list[tuple[str, ClosedSection]]:
        """Close sections whose ticks stopped coming (camera side stopped, trip left running)."""
        out = []
        for rec in self._trips.values():
            if rec.open is not None and now_wall - rec.open.last_wall >= self.section_s + 1.0:
                out.append((rec.trip_id, self._close(rec)))
        return out

    def _close(self, rec: _TripSections) -> ClosedSection:
        section, rec.open = rec.open, None
        t_end = section.t_start + self.section_s
        by_time = sorted(section.behaviors.items(), key=lambda item: (-item[1], item[0]))
        fields = {
            "section_id": uuid.uuid4().hex,
            "trip_id": rec.trip_id,
            "seq": section.seq,
            "t_start": round(section.t_start, 3),
            "t_end": round(t_end, 3),
            "started_at": rec.t0 + timedelta(seconds=section.t_start),
            "ended_at": rec.t0 + timedelta(seconds=t_end),
            "ticks": section.ticks,
            "score_start": round(section.score_start, 1),
            "score_end": round(section.score_end, 1),
            "score_min": round(section.score_min, 1),
            "level": level_for(section.score_end),
            "danger": _DANGER[section.danger],
            "behaviors": {behavior: round(seconds, 1) for behavior, seconds in by_time},
            "speed_kmh": round(section.speed_sum / section.ticks, 1) if section.ticks else 0.0,
            "speed_max_kmh": round(section.speed_max, 1),
            "speed_source": section.speed_source,
            "risk": round(section.risk_sum / section.risk_n, 3) if section.risk_n else None,
            "risk_max": section.risk_max,
            "alert": section.alert,
            "rules_triggered": sorted(section.rules),
            "categories": {name: agg.out() for name, agg in sorted(section.categories.items())},
            "groups": dict(sorted(section.groups.items())),
            "dashboard_light": section.light,
            "vibrate_seat": section.vibrate,
            "sound": section.sound,
            "emergency": section.emergency,
            "image_t": None,
            "lat": section.lat,
            "lon": section.lon,
        }
        return ClosedSection(
            fields=fields,
            danger=_DANGER[section.danger],
            peak_t=section.peak_t,
            peak_wall=section.peak_wall,
            peak_frame_id=section.peak_frame_id,
        )
