"""Trip tables (Postgres; SQLite in tests).

    trips          one row per trip: who and when, then the running summary (with every section and at the end)
    trip_sections  one row per section (2 s) the coordinator posted: score, speed, behaviors, the model's
                   numbers, danger, and the S3 key of the riskiest frame's image for dangerous sections

Diagram and review: docs/DATABASE.md. No migrations yet: after changing a table, `scripts/services.ps1 reset`
(or `docker compose down -v`) gives an empty database that the server recreates on start.
"""

from collections.abc import Collection
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Float, ForeignKey, Index, Integer, String, func, insert, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Mapped, mapped_column

from app.server.repositories import users  # noqa: F401  (trips.user_id references users.id)
from app.server.repositories.database import Base, Database, JsonType, Timestamp, utc_row


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
    section_s: Mapped[float | None] = mapped_column(Float)
    # Running summary, the same numbers as TripSummary: updated with every section and at the end.
    duration_s: Mapped[float | None] = mapped_column(Float)
    final_score: Mapped[float | None] = mapped_column(Float)
    average_score: Mapped[float | None] = mapped_column(Float)
    min_score: Mapped[float | None] = mapped_column(Float)
    level: Mapped[str | None] = mapped_column(String(16))
    emergency_alert_sent: Mapped[bool | None]
    behaviors: Mapped[list | None] = mapped_column(JsonType)  # [{behavior, occurrences, total_seconds}]


class SectionRow(Base):
    __tablename__ = "trip_sections"
    __table_args__ = (Index("ix_trip_sections_trip_seq", "trip_id", "seq"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # made by the coordinator: retries are no-ops
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    t_start: Mapped[float] = mapped_column(Float)
    t_end: Mapped[float] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(Timestamp)
    ended_at: Mapped[datetime] = mapped_column(Timestamp)
    ticks: Mapped[int]
    score_start: Mapped[float] = mapped_column(Float)
    score_end: Mapped[float] = mapped_column(Float)
    score_min: Mapped[float] = mapped_column(Float)
    level: Mapped[str] = mapped_column(String(16))
    danger: Mapped[str] = mapped_column(String(16))
    behaviors: Mapped[dict] = mapped_column(JsonType)  # {behavior: seconds}
    speed_kmh: Mapped[float] = mapped_column(Float)
    speed_max_kmh: Mapped[float] = mapped_column(Float)
    speed_source: Mapped[str | None] = mapped_column(String(16))
    risk: Mapped[float | None] = mapped_column(Float)
    risk_max: Mapped[float | None] = mapped_column(Float)
    alert: Mapped[str | None] = mapped_column(String(8))
    rules_triggered: Mapped[list] = mapped_column(JsonType)
    categories: Mapped[dict] = mapped_column(JsonType)
    groups: Mapped[dict] = mapped_column(JsonType)
    dashboard_light: Mapped[str] = mapped_column(String(16))
    vibrate_seat: Mapped[bool]
    sound: Mapped[str] = mapped_column(String(8))
    emergency: Mapped[bool]
    image_key: Mapped[str | None] = mapped_column(String(256))  # S3 key of the riskiest frame (JPEG)
    image_t: Mapped[float | None] = mapped_column(Float)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)


class RecordingRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @property
    def description(self) -> str:
        return self.db.description

    async def sync(self, trip: dict[str, Any], sections: list[dict[str, Any]], summary: dict[str, Any] | None) -> None:
        """One coordinator delivery, in one transaction. Rows already there are skipped, so retries are harmless."""
        async with self.db.begin() as conn:
            await conn.execute(self._insert_ignore(TripRow), [trip])
            if sections:
                await conn.execute(self._insert_ignore(SectionRow), sections)
            if summary:
                values = {**summary, "updated_at": datetime.now(timezone.utc)}
                if values.get("ended_at") is None:
                    values.pop("ended_at", None)  # never reopen an ended trip
                await conn.execute(update(TripRow).where(TripRow.id == trip["id"]).values(**values))

    async def close_interrupted(self, keep: Collection[str] = ()) -> int:
        """Trips left without `ended_at` by a crash or restart end at their last summary write.

        `keep`: trips the coordinator is driving right now.
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

    async def all_trips(self) -> list[dict[str, Any]]:
        table = TripRow.__table__
        return await self._all(select(table).order_by(table.c.started_at))

    async def sections(self, trip_id: str, after_seq: int | None = None) -> list[dict[str, Any]]:
        table = SectionRow.__table__
        query = select(table).where(table.c.trip_id == trip_id)
        if after_seq is not None:
            query = query.where(table.c.seq > after_seq)
        return await self._all(query.order_by(table.c.seq, table.c.started_at))

    async def _all(self, query) -> list[dict[str, Any]]:
        async with self.db.connect() as conn:
            result = await conn.execute(query)
            return [utc_row(dict(row._mapping)) for row in result]

    def _insert_ignore(self, model: type[Base]):
        """INSERT that skips rows already there, so retrying a delivery after a timeout is harmless."""
        dialect = self.db.engine.dialect.name
        if dialect == "postgresql":
            return postgresql.insert(model).on_conflict_do_nothing()
        if dialect == "sqlite":
            return sqlite.insert(model).on_conflict_do_nothing()
        return insert(model)
