"""Trip recording tables (Postgres; SQLite in tests).

    trips          one row per trip: who and when, then a running summary (every ~10 s and at the end),
                   including the camera model's own trip report (JSON)
    trip_samples   one row per second of driving: score, speed, labels, the camera model's numbers
    risk_events    one row per risky moment, with the S3 keys of its clip and thumbnail

Diagram and review: docs/DATABASE.md.
"""

from collections.abc import Collection
from datetime import datetime
from itertools import groupby
from typing import Any

from sqlalchemy import BigInteger, Float, ForeignKey, Index, Integer, String, func, insert, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories import users  # noqa: F401  (trips.user_id references users.id)
from app.repositories.database import Base, Database, JsonType, Timestamp, utc_row


class TripRow(Base):
    __tablename__ = "trips"
    __table_args__ = (Index("ix_trips_user_started", "user_id", "started_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))  # null = no login
    driver_id: Mapped[str] = mapped_column(String(128), index=True)
    started_at: Mapped[datetime] = mapped_column(Timestamp)
    ended_at: Mapped[datetime | None] = mapped_column(Timestamp)  # null while driving
    updated_at: Mapped[datetime | None] = mapped_column(Timestamp)  # last summary write
    emergency_contact: Mapped[dict | None] = mapped_column(JsonType)
    speed_scenario: Mapped[str | None] = mapped_column(String(32))
    # Running summary, the same numbers as TripSummary: written every ~10 s while driving and at the end.
    duration_s: Mapped[float | None] = mapped_column(Float)
    final_score: Mapped[float | None] = mapped_column(Float)
    average_score: Mapped[float | None] = mapped_column(Float)
    min_score: Mapped[float | None] = mapped_column(Float)
    level: Mapped[str | None] = mapped_column(String(16))
    emergency_alert_sent: Mapped[bool | None]
    behaviors: Mapped[list | None] = mapped_column(JsonType)  # [{behavior, occurrences, total_seconds}]
    # The camera model's own trip report (services/model_report.py), null if no model frames came.
    model_report: Mapped[dict | None] = mapped_column(JsonType)


class SampleRow(Base):
    __tablename__ = "trip_samples"
    __table_args__ = (Index("ix_trip_samples_trip_t", "trip_id", "t"),)

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(Timestamp)
    t: Mapped[float] = mapped_column(Float)
    ticks: Mapped[int]
    speed_kmh: Mapped[float] = mapped_column(Float)
    speed_max_kmh: Mapped[float] = mapped_column(Float)
    speed_source: Mapped[str] = mapped_column(String(16))
    score: Mapped[float] = mapped_column(Float)
    score_min: Mapped[float] = mapped_column(Float)
    level: Mapped[str] = mapped_column(String(16))
    behaviors: Mapped[list] = mapped_column(JsonType)
    risk: Mapped[float | None] = mapped_column(Float)
    risk_max: Mapped[float | None] = mapped_column(Float)
    alert: Mapped[str | None] = mapped_column(String(8))
    rules_triggered: Mapped[list] = mapped_column(JsonType)
    categories: Mapped[dict] = mapped_column(JsonType)
    groups: Mapped[dict] = mapped_column(JsonType)
    dashboard_light: Mapped[str] = mapped_column(String(16))
    vibrate_seat: Mapped[bool]
    sound: Mapped[str] = mapped_column(String(8))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)


class EventRow(Base):
    __tablename__ = "risk_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(Timestamp)
    ended_at: Mapped[datetime] = mapped_column(Timestamp)
    t_start: Mapped[float] = mapped_column(Float)
    duration_s: Mapped[float] = mapped_column(Float)
    behaviors: Mapped[list] = mapped_column(JsonType)
    behavior_seconds: Mapped[dict] = mapped_column(JsonType)
    categories: Mapped[dict] = mapped_column(JsonType)
    rules_triggered: Mapped[list] = mapped_column(JsonType)
    alert: Mapped[str | None] = mapped_column(String(8))
    peak_risk: Mapped[float | None] = mapped_column(Float)
    score_start: Mapped[float] = mapped_column(Float)
    score_end: Mapped[float] = mapped_column(Float)
    score_min: Mapped[float] = mapped_column(Float)
    score_drop: Mapped[float] = mapped_column(Float)
    level: Mapped[str] = mapped_column(String(16))
    speed_avg_kmh: Mapped[float] = mapped_column(Float)
    speed_max_kmh: Mapped[float] = mapped_column(Float)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    video_key: Mapped[str | None] = mapped_column(String(256))
    thumbnail_key: Mapped[str | None] = mapped_column(String(256))
    clip_duration_s: Mapped[float | None] = mapped_column(Float)


# Kinds of queued writes, see RecordingRepository.write().
TRIP_START, TRIP_UPDATE, SAMPLE, EVENT = "trip_start", "trip_update", "sample", "event"


class RecordingRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @property
    def description(self) -> str:
        return self.db.description

    async def write(self, ops: list[tuple[str, dict[str, Any]]]) -> None:
        """Apply queued writes in order, in one transaction. Consecutive rows of a kind go in one batch."""
        async with self.db.begin() as conn:
            for kind, group in groupby(ops, key=lambda op: op[0]):
                rows = [row for _, row in group]
                if kind == TRIP_START:
                    await conn.execute(self._insert_ignore(TripRow), rows)
                elif kind == TRIP_UPDATE:
                    for row in rows:
                        values = {key: value for key, value in row.items() if key != "id"}
                        await conn.execute(update(TripRow).where(TripRow.id == row["id"]).values(**values))
                elif kind == SAMPLE:
                    await conn.execute(insert(SampleRow), rows)
                elif kind == EVENT:
                    await conn.execute(self._insert_ignore(EventRow), rows)
                else:
                    raise ValueError(f"Unknown write kind {kind!r}")

    async def close_interrupted(self, keep: Collection[str] = ()) -> int:
        """Trips left without `ended_at` by a crash or restart end at their last summary write.

        `keep`: trips this process is driving right now.
        """
        query = update(TripRow).where(TripRow.ended_at.is_(None))
        if keep:
            query = query.where(TripRow.id.not_in(list(keep)))
        async with self.db.begin() as conn:
            result = await conn.execute(query.values(ended_at=func.coalesce(TripRow.updated_at, TripRow.started_at)))
            return result.rowcount or 0

    async def trip(self, trip_id: str) -> dict[str, Any] | None:
        rows = await self._all(select(TripRow.__table__).where(TripRow.id == trip_id))
        return rows[0] if rows else None

    async def trips(self, user_id: str | None = None, driver_id: str | None = None) -> list[dict[str, Any]]:
        """Oldest first. With a user: that account's trips. Without: trips started without login."""
        table = TripRow.__table__
        query = select(table).order_by(table.c.started_at)
        if user_id is not None:
            query = query.where(table.c.user_id == user_id)
        else:
            query = query.where(table.c.user_id.is_(None))
            if driver_id is not None:
                query = query.where(table.c.driver_id == driver_id)
        return await self._all(query)

    async def samples(self, trip_id: str) -> list[dict[str, Any]]:
        table = SampleRow.__table__
        return await self._all(select(table).where(table.c.trip_id == trip_id).order_by(table.c.t, table.c.id))

    async def events(self, trip_id: str) -> list[dict[str, Any]]:
        table = EventRow.__table__
        return await self._all(select(table).where(table.c.trip_id == trip_id).order_by(table.c.started_at))

    async def _all(self, query) -> list[dict[str, Any]]:
        async with self.db.connect() as conn:
            result = await conn.execute(query)
            return [utc_row(dict(row._mapping)) for row in result]

    def _insert_ignore(self, model: type[Base]):
        """INSERT that skips rows already there, so retrying a write after a timeout is harmless."""
        dialect = self.db.engine.dialect.name
        if dialect == "postgresql":
            return postgresql.insert(model).on_conflict_do_nothing()
        if dialect == "sqlite":
            return sqlite.insert(model).on_conflict_do_nothing()
        return insert(model)
