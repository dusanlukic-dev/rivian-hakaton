"""Driver accounts and their login sessions.

    users          one row per driver: username (unique), scrypt password hash, name, emergency contact
    user_sessions  one row per login: SHA-256 of the bearer token (never the token itself), expiry
"""

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, delete, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from app.server.repositories.database import Base, Database, JsonType, Timestamp, utc_row


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)  # lowercase; also the trips' driver_id
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(128))
    emergency_contact: Mapped[dict | None] = mapped_column(JsonType)  # {"name", "phone"}
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class SessionRow(Base):
    __tablename__ = "user_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    expires_at: Mapped[datetime] = mapped_column(Timestamp)


class UsernameTaken(Exception):
    pass


class UserRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(self, row: dict[str, Any]) -> None:
        try:
            async with self.db.begin() as conn:
                await conn.execute(insert(UserRow), row)
        except IntegrityError as e:
            raise UsernameTaken(row["username"]) from e

    async def by_username(self, username: str) -> dict[str, Any] | None:
        return await self._first(select(UserRow.__table__).where(UserRow.username == username))

    async def by_id(self, user_id: str) -> dict[str, Any] | None:
        return await self._first(select(UserRow.__table__).where(UserRow.id == user_id))

    async def update(self, user_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        if values:
            async with self.db.begin() as conn:
                await conn.execute(update(UserRow).where(UserRow.id == user_id).values(**values))
        return await self.by_id(user_id)

    async def add_session(self, row: dict[str, Any]) -> None:
        async with self.db.begin() as conn:
            await conn.execute(insert(SessionRow), row)

    async def user_for_token(self, token_hash: str, now: datetime) -> dict[str, Any] | None:
        users, sessions = UserRow.__table__, SessionRow.__table__
        query = (
            select(users)
            .join(sessions, sessions.c.user_id == users.c.id)
            .where(sessions.c.token_hash == token_hash, sessions.c.expires_at > now)
        )
        return await self._first(query)

    async def delete_session(self, token_hash: str) -> None:
        async with self.db.begin() as conn:
            await conn.execute(delete(SessionRow).where(SessionRow.token_hash == token_hash))

    async def _first(self, query) -> dict[str, Any] | None:
        async with self.db.connect() as conn:
            row = (await conn.execute(query)).first()
        return utc_row(dict(row._mapping)) if row else None
