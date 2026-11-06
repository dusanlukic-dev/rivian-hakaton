from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.schemas.auth import User
from app.server.services.auth import AuthService, AuthUnavailable, get_auth_service
from app.server.services.storage import TripStore, get_trip_store

Auth = Annotated[AuthService, Depends(get_auth_service)]
Store = Annotated[TripStore, Depends(get_trip_store)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

bearer = HTTPBearer(auto_error=False, description="Token from POST /auth/login or /auth/register")
BearerToken = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]

_WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}


async def get_optional_user(auth: Auth, credentials: BearerToken) -> User | None:
    """The logged-in user, or None without an Authorization header. A bad or expired token is a 401."""
    if credentials is None:
        return None
    try:
        user = await auth.user_for_token(credentials.credentials)
    except AuthUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token - log in again", _WWW_AUTHENTICATE)
    return user


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


async def get_current_user(user: OptionalUser) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Log in first (Authorization: Bearer <token>)", _WWW_AUTHENTICATE)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_internal_token(
    settings: SettingsDep, x_internal_token: Annotated[str | None, Header()] = None
) -> None:
    """/internal/* is for the coordinator only: it sends the shared INTERNAL_TOKEN."""
    if x_internal_token != settings.internal_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Internal route: X-Internal-Token missing or wrong")
