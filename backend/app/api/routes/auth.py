"""Driver accounts: register, log in, who am I. Send the token as `Authorization: Bearer <token>`."""

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import Auth, BearerToken, CurrentUser
from app.schemas.auth import AuthOut, LoginIn, RegisterIn, User, UserUpdate
from app.services.auth import AuthError, AuthUnavailable, UsernameTaken

router = APIRouter(prefix="/auth", tags=["auth"])


def _unavailable(error: AuthUnavailable) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error))


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, auth: Auth) -> AuthOut:
    """New account; you are logged in right away."""
    try:
        return await auth.register(body)
    except UsernameTaken:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Username {body.username} is taken") from None
    except AuthUnavailable as e:
        raise _unavailable(e) from e


@router.post("/login")
async def login(body: LoginIn, auth: Auth) -> AuthOut:
    try:
        return await auth.login(body.username, body.password)
    except AuthError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Wrong username or password", {"WWW-Authenticate": "Bearer"}
        ) from None
    except AuthUnavailable as e:
        raise _unavailable(e) from e


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def logout(user: CurrentUser, credentials: BearerToken, auth: Auth) -> Response:
    """Ends this token's session (other devices stay logged in)."""
    try:
        await auth.logout(credentials.credentials)
    except AuthUnavailable as e:
        raise _unavailable(e) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me")
async def me(user: CurrentUser) -> User:
    return user


@router.patch("/me")
async def update_me(body: UserUpdate, user: CurrentUser, auth: Auth) -> User:
    """Change the display name or the emergency contact (the app's profile screen)."""
    try:
        return await auth.update(user, body)
    except AuthUnavailable as e:
        raise _unavailable(e) from e
