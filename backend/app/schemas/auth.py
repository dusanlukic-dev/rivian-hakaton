from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.trip import EmergencyContactIn

USERNAME_PATTERN = r"^[a-z0-9][a-z0-9._-]{2,31}$"


def _normalize_username(value: str) -> str:
    return value.strip().lower()


class User(BaseModel):
    """A driver's account. Never contains the password (only its hash is stored)."""

    user_id: str
    username: str = Field(description="Login name, lowercase. Also the `driver_id` of this driver's trips.")
    display_name: str
    emergency_contact: EmergencyContactIn | None
    created_at: datetime


class RegisterIn(BaseModel):
    username: str = Field(
        description="3-32 characters: a-z, 0-9, '.', '_', '-' (lowercased). Must be unique.",
    )
    password: str = Field(min_length=6, max_length=128)
    display_name: str | None = Field(default=None, max_length=128, description="Defaults to the username.")
    emergency_contact: EmergencyContactIn | None = Field(
        default=None, description="Used for trips started without their own contact."
    )

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        import re

        value = _normalize_username(value)
        if not re.fullmatch(USERNAME_PATTERN, value):
            raise ValueError("3-32 characters: letters, digits, '.', '_' or '-'")
        return value


class LoginIn(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        return _normalize_username(value)


class AuthOut(BaseModel):
    """Send `token` as `Authorization: Bearer <token>` on later requests."""

    token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: User


class UserUpdate(BaseModel):
    """Only the fields sent are changed. `emergency_contact: null` removes the contact."""

    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    emergency_contact: EmergencyContactIn | None = None
