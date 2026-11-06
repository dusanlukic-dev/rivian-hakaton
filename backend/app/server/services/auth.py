"""Driver accounts: register, log in with a password, bearer tokens.

Passwords: scrypt (Python's standard library), hashed in a worker thread so a login never stalls the
live scoring. Tokens: 32 random bytes, not JWT. The database keeps only their SHA-256, so a leaked
table can't log anyone in, and logging out really ends the session. A token lives 30 days.
"""

import asyncio
import base64
import hashlib
import hmac
import secrets
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from functools import cache
from typing import Any

from app.server.repositories.database import get_database
from app.server.repositories.users import UsernameTaken, UserRepository
from app.schemas.auth import AuthOut, RegisterIn, User, UserUpdate
from app.schemas.trip import EmergencyContactIn

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1  # ~16 MB and ~50 ms per hash
TOKEN_TTL = timedelta(days=30)

__all__ = ["AuthError", "AuthService", "AuthUnavailable", "UsernameTaken", "get_auth_service"]


class AuthError(Exception):
    """Wrong username or password."""


class AuthUnavailable(Exception):
    """Accounts live in Postgres, and it can't be reached."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = _unb64(digest)
        actual = hashlib.scrypt(
            password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


@cache
def _dummy_hash() -> str:
    return hash_password("not the password")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def to_user(row: dict[str, Any]) -> User:
    contact = row.get("emergency_contact")
    return User(
        user_id=row["id"],
        username=row["username"],
        display_name=row["display_name"],
        emergency_contact=EmergencyContactIn(**contact) if contact else None,
        created_at=row["created_at"],
    )


class AuthService:
    def __init__(
        self, users: UserRepository, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    ) -> None:
        self.users = users
        self._now = now

    async def register(self, data: RegisterIn) -> AuthOut:
        password_hash = await asyncio.to_thread(hash_password, data.password)
        row = {
            "id": uuid.uuid4().hex,
            "username": data.username,
            "password_hash": password_hash,
            "display_name": (data.display_name or "").strip() or data.username,
            "emergency_contact": data.emergency_contact.model_dump() if data.emergency_contact else None,
            "created_at": self._now(),
        }
        await self._db(self.users.create(row))  # UsernameTaken if it exists
        return await self._new_session(row)

    async def login(self, username: str, password: str) -> AuthOut:
        row = await self._db(self.users.by_username(username))
        # Hash even for an unknown user, so the response time doesn't reveal which usernames exist.
        stored = row["password_hash"] if row else _dummy_hash()
        if not await asyncio.to_thread(verify_password, password, stored) or row is None:
            raise AuthError
        return await self._new_session(row)

    async def logout(self, token: str) -> None:
        await self._db(self.users.delete_session(token_hash(token)))

    async def user_for_token(self, token: str) -> User | None:
        row = await self._db(self.users.user_for_token(token_hash(token), self._now()))
        return to_user(row) if row else None

    async def user_by_id(self, user_id: str) -> User | None:
        row = await self._db(self.users.by_id(user_id))
        return to_user(row) if row else None

    async def update(self, user: User, data: UserUpdate) -> User:
        values: dict[str, Any] = {}
        if "display_name" in data.model_fields_set and data.display_name is not None:
            values["display_name"] = data.display_name.strip()
        if "emergency_contact" in data.model_fields_set:
            contact = data.emergency_contact
            values["emergency_contact"] = contact.model_dump() if contact else None
        row = await self._db(self.users.update(user.user_id, values))
        return to_user(row) if row else user

    async def _new_session(self, user_row: dict[str, Any]) -> AuthOut:
        token = secrets.token_urlsafe(32)
        now = self._now()
        expires_at = now + TOKEN_TTL
        await self._db(self.users.add_session({
            "token_hash": token_hash(token),
            "user_id": user_row["id"],
            "created_at": now,
            "expires_at": expires_at,
        }))
        return AuthOut(token=token, expires_at=expires_at, user=to_user(user_row))

    @staticmethod
    async def _db(call):
        """Run a repository call. Postgres being down becomes AuthUnavailable (HTTP 503)."""
        try:
            return await call
        except UsernameTaken:
            raise
        except Exception as e:
            raise AuthUnavailable(f"Accounts need Postgres, which is unreachable ({type(e).__name__})") from e


_auth_service: AuthService | None = None


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService(UserRepository(get_database()))
    return _auth_service
