"""Postgres tables for the trip recording (SQLite in tests).

    trips          one row per trip: start, then the summary at the end
    trip_samples   one row per window (default 1 s): score, speed, labels, the camera model's numbers
    risk_events    one row per risky moment, with the S3 keys of its clip and thumbnail

The tables are created on startup (`create_all`). There are no migrations yet: after changing a
model, drop the tables (or the database) in dev.
"""

from datetime import datetime, timezone
from itertools import groupby
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    insert,
    make_url,
    select,
    update,
)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

JsonType = JSON().with_variant(postgresql.JSONB(), "postgresql")
Timestamp = DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


class TripRow(Base):
    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    driver_id: Mapped[str] = mapped_column(String(128), index=True)
    started_at: Mapped[datetime] = mapped_column(Timestamp)
    ended_at: Mapped[datetime | None] = mapped_column(Timestamp)
    emergency_contact: Mapped[dict | None] = mapped_column(JsonType)
    speed_scenario: Mapped[str | None] = mapped_column(String(32))
    # Filled in when the trip ends (same numbers as TripSummary).
    duration_s: Mapped[float | None] = mapped_column(Float)
    final_score: Mapped[float | None] = mapped_column(Float)
    average_score: Mapped[float | None] = mapped_column(Float)
    min_score: Mapped[float | None] = mapped_column(Float)
    level: Mapped[str | None] = mapped_column(String(16))
    emergency_alert_sent: Mapped[bool | None]
    behaviors: Mapped[list | None] = mapped_column(JsonType)  # [{behavior, occurrences, total_seconds}]


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


# Kinds of queued writes, see RecordingDatabase.write().
TRIP_START, TRIP_END, SAMPLE, EVENT = "trip_start", "trip_end", "sample", "event"


def _utc(row: dict[str, Any]) -> dict[str, Any]:
    """SQLite hands timestamps back without a zone; everything is stored in UTC."""
    return {
        key: value.replace(tzinfo=timezone.utc) if isinstance(value, datetime) and value.tzinfo is None else value
        for key, value in row.items()
    }


class RecordingDatabase:
    def __init__(self, url: str) -> None:
        parsed = make_url(url)
        kwargs: dict[str, Any] = {"pool_pre_ping": True}
        if parsed.get_driver_name() == "asyncpg":
            # Fail fast when Postgres is down instead of hanging a flush for asyncpg's default 60 s.
            kwargs["connect_args"] = {"timeout": 3, "command_timeout": 15}
        elif parsed.get_backend_name() == "sqlite" and parsed.database in (None, "", ":memory:"):
            kwargs["poolclass"] = StaticPool  # tests: one shared in-memory database
        self.engine = create_async_engine(parsed, **kwargs)

    @property
    def description(self) -> str:
        return self.engine.url.render_as_string(hide_password=True)

    async def create_schema(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()

    async def write(self, ops: list[tuple[str, dict[str, Any]]]) -> None:
        """Apply queued writes in order, in one transaction. Consecutive rows of a kind go in one batch."""
        async with self.engine.begin() as conn:
            for kind, group in groupby(ops, key=lambda op: op[0]):
                rows = [row for _, row in group]
                if kind == TRIP_START:
                    await conn.execute(self._insert_ignore(TripRow), rows)
                elif kind == TRIP_END:
                    for row in rows:
                        values = {key: value for key, value in row.items() if key != "id"}
                        await conn.execute(update(TripRow).where(TripRow.id == row["id"]).values(**values))
                elif kind == SAMPLE:
                    await conn.execute(insert(SampleRow), rows)
                elif kind == EVENT:
                    await conn.execute(self._insert_ignore(EventRow), rows)
                else:
                    raise ValueError(f"Unknown write kind {kind!r}")

    async def trip(self, trip_id: str) -> dict[str, Any] | None:
        return await self._first(select(TripRow.__table__).where(TripRow.id == trip_id))

    async def samples(self, trip_id: str) -> list[dict[str, Any]]:
        table = SampleRow.__table__
        return await self._all(select(table).where(table.c.trip_id == trip_id).order_by(table.c.t, table.c.id))

    async def events(self, trip_id: str) -> list[dict[str, Any]]:
        table = EventRow.__table__
        return await self._all(select(table).where(table.c.trip_id == trip_id).order_by(table.c.started_at))

    async def _first(self, query) -> dict[str, Any] | None:
        rows = await self._all(query)
        return rows[0] if rows else None

    async def _all(self, query) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            result = await conn.execute(query)
            return [_utc(dict(row._mapping)) for row in result]

    def _insert_ignore(self, model: type[Base]):
        """INSERT that skips rows already there, so retrying a write after a timeout is harmless."""
        dialect = self.engine.dialect.name
        if dialect == "postgresql":
            return postgresql.insert(model).on_conflict_do_nothing()
        if dialect == "sqlite":
            return sqlite.insert(model).on_conflict_do_nothing()
        return insert(model)
