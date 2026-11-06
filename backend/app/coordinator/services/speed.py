"""Car speed for the score. The camera doesn't know it, so the backend provides it.

Precedence on every telemetry tick:

1. the phone's GPS (``POST /speed``), only with ``PHONE_SPEED_ENABLED=true`` and a fresh reading;
2. ``speed_kmh`` sent in the tick itself (the simulator, tests, a car that knows its own speed);
3. a mocked drive: a speed scenario picked per trip and played along the trip's tick clock.

A scenario is a list of keyframes ``(second, km/h)``. Between two keyframes the speed follows a
cubic Bezier curve with flat handles (ease in / ease out), so the car speeds up and brakes smoothly
and really stops at 0 km/h. That also exercises the "no penalty below 5 km/h" rule.
"""

import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import pairwise

from app.core.config import get_settings
from app.domain.enums import SpeedSource
from app.domain.trip import Trip
from app.schemas.speed import SpeedStatus

RANDOM = "random"
PHONE_MAX_AGE_S = 5.0  # an older phone reading is ignored (GPS lost, app in the background)


def bezier(p0: float, p1: float, p2: float, p3: float, u: float) -> float:
    """Cubic Bezier curve at u in [0, 1]."""
    m = 1.0 - u
    return m * m * m * p0 + 3 * m * m * u * p1 + 3 * m * u * u * p2 + u * u * u * p3


def ease(v0: float, v1: float, u: float) -> float:
    """From v0 to v1 with flat handles: no sudden change in acceleration at the keyframes.

    Handles at 1/3 and 2/3 of the way would make this a straight line instead.
    """
    return bezier(v0, v0, v1, v1, u)


@dataclass(frozen=True)
class SpeedScenario:
    name: str
    description: str
    keyframes: tuple[tuple[float, float], ...]  # (second, km/h), strictly increasing seconds
    # After the last keyframe the drive repeats from this second. The speed there must equal the
    # speed at the last keyframe, so the loop has no jump.
    loop_from_s: float = 0.0

    @property
    def duration_s(self) -> float:
        return self.keyframes[-1][0]

    def speed_at(self, t: float) -> float:
        t = max(t, 0.0)
        end = self.duration_s
        if t > end:
            span = end - self.loop_from_s
            t = self.loop_from_s + (t - end) % span if span > 0 else end
        for (t0, v0), (t1, v1) in pairwise(self.keyframes):
            if t <= t1:
                return ease(v0, v1, (t - t0) / (t1 - t0))
        return self.keyframes[-1][1]


def _scenario(name: str, description: str, *keyframes: tuple[float, float], loop_from_s: float = 0.0):
    return SpeedScenario(name, description, keyframes, loop_from_s)


SCENARIOS: dict[str, SpeedScenario] = {
    s.name: s
    for s in (
        _scenario(
            "city", "City streets at 30-50 km/h with three stops at traffic lights (4 min loop)",
            (0, 0), (6, 0), (16, 45), (40, 50), (48, 30), (58, 30), (66, 50), (90, 48),
            (100, 0), (118, 0),  # red light
            (130, 40), (150, 52), (170, 45),
            (182, 0), (192, 0),  # stop sign
            (204, 35), (220, 40), (232, 0), (240, 0),
        ),
        _scenario(
            "highway", "Out of town onto the highway at 120-130 km/h, a slowdown, then off again",
            (0, 0), (5, 0), (15, 50), (30, 60), (40, 60),
            (55, 100), (70, 125), (110, 130),  # on-ramp, cruise
            (125, 95), (140, 90),  # traffic
            (155, 125), (195, 130),
            (210, 80), (225, 50), (235, 50), (245, 0), (255, 0),  # exit
        ),
        _scenario(
            "stop_and_go", "Traffic jam: crawling at 10-30 km/h with long standstills (2 min loop)",
            (0, 0), (8, 0), (14, 15), (18, 12), (22, 0), (32, 0),
            (38, 20), (44, 18), (48, 0), (55, 0),
            (60, 10), (66, 25), (72, 8), (76, 0), (90, 0),
            (98, 30), (106, 22), (112, 0), (120, 0),
        ),
        _scenario(
            "country_road", "Open road at 60-90 km/h with a bend and a village",
            (0, 0), (5, 0), (15, 50), (30, 70), (60, 85), (80, 80),
            (90, 60), (100, 60),  # bend
            (115, 85), (150, 88),
            (165, 50), (185, 50),  # village
            (200, 0), (210, 0),
        ),
        _scenario(
            "cruise", "Steady 50-62 km/h and never stops: predictable for a stage demo",
            (0, 0), (8, 50), (40, 60), (80, 55), (120, 62), (160, 50),
            loop_from_s=8,
        ),
        _scenario(
            "parked", "Standing still the whole time: no penalties and no warnings, ever",
            (0, 0), (60, 0),
        ),
    )
}

# "random" picks one of these per trip. "cruise" and "parked" only when asked for by name.
RANDOM_POOL = ("city", "highway", "stop_and_go", "country_road")


@dataclass
class _MockDrive:
    scenario: SpeedScenario
    phases: tuple[float, float]  # small per-trip wobble, so no two drives look identical
    t0: datetime | None = None  # the trip's first tick

    def speed_at(self, timestamp: datetime) -> float:
        ts = timestamp.astimezone(timezone.utc)  # a naive timestamp counts as local time
        if self.t0 is None:
            self.t0 = ts
        t = (ts - self.t0).total_seconds()
        v = self.scenario.speed_at(t)
        # +-2 km/h of wobble while really driving; it fades out below 20 km/h so stops stay at 0.
        wobble = 1.5 * math.sin(2 * math.pi * t / 9.0 + self.phases[0])
        wobble += 0.8 * math.sin(2 * math.pi * t / 3.7 + self.phases[1])
        v += wobble * min(max((v - 10.0) / 10.0, 0.0), 1.0)
        return round(max(v, 0.0), 1)


@dataclass(frozen=True)
class SpeedReading:
    speed_kmh: float
    source: SpeedSource
    lat: float | None = None
    lon: float | None = None


@dataclass(frozen=True)
class _PhoneFix:
    speed_kmh: float
    lat: float | None
    lon: float | None
    received_at: float  # monotonic seconds


class PhoneSpeedDisabled(Exception):
    """POST /speed while PHONE_SPEED_ENABLED is false."""


@dataclass
class SpeedService:
    scenario: str = RANDOM
    phone_enabled: bool = False
    phone_max_age_s: float = PHONE_MAX_AGE_S
    clock: Callable[[], float] = time.monotonic
    _drives: dict[str, _MockDrive] = field(default_factory=dict, init=False, repr=False)
    _phone: _PhoneFix | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.scenario != RANDOM and self.scenario not in SCENARIOS:
            raise ValueError(
                f"Unknown SPEED_SCENARIO {self.scenario!r}; use {RANDOM!r} or one of {sorted(SCENARIOS)}"
            )

    def scenario_for(self, trip_id: str) -> SpeedScenario:
        return self._drive(trip_id).scenario

    def resolve(self, trip_id: str, timestamp: datetime, tick_speed_kmh: float | None) -> SpeedReading:
        """The speed to score this tick with, and where it came from."""
        mock_kmh = self._drive(trip_id).speed_at(timestamp)  # always, so the mock clock starts at tick one
        phone = self._fresh_phone()
        if phone is not None:
            return SpeedReading(phone.speed_kmh, SpeedSource.PHONE, phone.lat, phone.lon)
        if tick_speed_kmh is not None:
            return SpeedReading(tick_speed_kmh, SpeedSource.TELEMETRY)
        return SpeedReading(mock_kmh, SpeedSource.MOCK)

    def report_phone(self, speed_kmh: float, lat: float | None = None, lon: float | None = None) -> None:
        if not self.phone_enabled:
            raise PhoneSpeedDisabled
        self._phone = _PhoneFix(speed_kmh, lat, lon, self.clock())

    def end_trip(self, trip_id: str) -> None:
        self._drives.pop(trip_id, None)

    def status(self, trip: Trip | None) -> SpeedStatus:
        phone_age = None if self._phone is None else round(self.clock() - self._phone.received_at, 1)
        return SpeedStatus(
            source=trip.speed_source if trip else None,
            speed_kmh=trip.speed_kmh if trip and trip.speed_source else None,
            scenario=self.scenario_for(trip.id).name if trip else self.scenario,
            scenarios=sorted(SCENARIOS),
            phone_enabled=self.phone_enabled,
            phone_age_s=phone_age,
        )

    def _drive(self, trip_id: str) -> _MockDrive:
        drive = self._drives.get(trip_id)
        if drive is None:
            rng = random.Random(trip_id)  # the same trip always gets the same drive
            name = rng.choice(RANDOM_POOL) if self.scenario == RANDOM else self.scenario
            drive = _MockDrive(SCENARIOS[name], (rng.uniform(0, 2 * math.pi), rng.uniform(0, 2 * math.pi)))
            self._drives[trip_id] = drive
        return drive

    def _fresh_phone(self) -> _PhoneFix | None:
        if not self.phone_enabled or self._phone is None:
            return None
        if self.clock() - self._phone.received_at > self.phone_max_age_s:
            return None
        return self._phone


_speed_service: SpeedService | None = None


def get_speed_service() -> SpeedService:
    global _speed_service
    if _speed_service is None:
        settings = get_settings()
        _speed_service = SpeedService(settings.speed_scenario, settings.phone_speed_enabled)
    return _speed_service
