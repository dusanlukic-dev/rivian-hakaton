"""The one Postgres database (in-memory SQLite in tests): engine, schema and turn-taking.

The tables live next to their queries: `users.py` (accounts, logins) and `recordings.py` (trips,
per-second samples, risky moments). Diagram and review: docs/DATABASE.md.

`create_all` creates missing tables on first use. There are no migrations yet: if the code has a
column the database lacks, the log says so and the dev database needs `scripts/services.ps1 reset`.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, inspect, make_url
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

logger = logging.getLogger(__name__)

JsonType = JSON().with_variant(postgresql.JSONB(), "postgresql")
Timestamp = DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


def utc_row(row: dict[str, Any]) -> dict[str, Any]:
    """SQLite hands timestamps back without a zone; everything is stored in UTC."""
    return {
        key: value.replace(tzinfo=timezone.utc) if isinstance(value, datetime) and value.tzinfo is None else value
        for key, value in row.items()
    }


class Database:
    def __init__(self, url: str) -> None:
        parsed = make_url(url)
        kwargs: dict[str, Any] = {"pool_pre_ping": True}
        is_sqlite = parsed.get_backend_name() == "sqlite"
        if parsed.get_driver_name() == "asyncpg":
            # Fail fast when Postgres is down instead of hanging for asyncpg's default 60 s.
            kwargs["connect_args"] = {"timeout": 3, "command_timeout": 15}
        elif is_sqlite and parsed.database in (None, "", ":memory:"):
            kwargs["poolclass"] = StaticPool  # tests: one shared in-memory database
        self.engine = create_async_engine(parsed, **kwargs)
        self.description = parsed.render_as_string(hide_password=True)
        # SQLite is one shared connection, so its users take turns. Postgres has a connection pool.
        self._turns = asyncio.Lock() if is_sqlite else None
        self._schema_lock = asyncio.Lock()
        self._schema_ready = False

    async def ensure_schema(self) -> None:
        """Create missing tables once (the startup check and the first request may race for it)."""
        if self._schema_ready:
            return
        async with self._schema_lock:
            if self._schema_ready:
                return
            async with self._turn(), self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                missing = await conn.run_sync(_missing_columns)
            if missing:
                logger.warning(
                    "The database is older than the code (missing columns %s). Reset the dev database: "
                    "scripts/services.ps1 reset",
                    ", ".join(missing),
                )
            self._schema_ready = True

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[AsyncConnection]:
        """A connection for reads."""
        await self.ensure_schema()
        async with self._turn(), self.engine.connect() as conn:
            yield conn

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[AsyncConnection]:
        """A connection inside one transaction, committed when the block ends without an error."""
        await self.ensure_schema()
        async with self._turn(), self.engine.begin() as conn:
            yield conn

    async def close(self) -> None:
        await self.engine.dispose()

    @asynccontextmanager
    async def _turn(self) -> AsyncIterator[None]:
        if self._turns is None:
            yield
        else:
            async with self._turns:
                yield


_database: Database | None = None


def get_database() -> Database:
    """The app's database (DATABASE_URL). Creating it doesn't connect yet."""
    global _database
    if _database is None:
        _database = Database(get_settings().database_url)
    return _database


def _missing_columns(sync_conn) -> list[str]:
    inspector = inspect(sync_conn)
    missing = []
    for table in Base.metadata.sorted_tables:
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        missing += [f"{table.name}.{column.name}" for column in table.columns if column.name not in existing]
    return missing
