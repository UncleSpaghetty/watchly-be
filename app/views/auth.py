from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select

from app.errors import ApiError
from app.models.auth_session import AuthSession
from app.models.user import User
from app.schemas.auth import LoginRequest, UserRead
from app.settings.config import Settings, get_settings
from app.settings.security import (
    CurrentUser,
    Db,
    RateLimiter,
    create_session,
    get_auth,
    verify_password,
)

router = APIRouter(tags=["auth"])
login_limit = RateLimiter(limit=10, window_seconds=300, scope="login")


def _set_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,  # type: ignore[arg-type]
        domain=settings.session_cookie_domain,
        path="/",
    )


@router.post("/auth/login", response_model=UserRead, dependencies=[Depends(login_limit)])
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    valid = verify_password(user.password_hash if user else None, body.password)
    if user is None or not valid or not user.is_active:
        raise ApiError(401, "invalid_credentials", "Credenziali non valide")
    token, _ = create_session(db, user, settings, request.headers.get("user-agent"))
    _set_cookie(response, token, settings)
    return user


@router.post("/auth/logout", status_code=204)
def logout(
    response: Response,
    db: Db,
    auth: Annotated[tuple[User, AuthSession], Depends(get_auth)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    auth[1].revoked_at = datetime.now(UTC)
    db.commit()
    response.delete_cookie(
        settings.session_cookie_name, path="/", domain=settings.session_cookie_domain
    )


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> User:
    return user


@router.delete("/me", status_code=204)
def delete_account(user: CurrentUser, db: Db, response: Response) -> None:
    """Elimina utente e dati collegati (sessioni, follow, visti, push) tramite cascade DB."""
    db.delete(user)
    db.commit()
