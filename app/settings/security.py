import hashlib
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from typing import cast

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from flask import g, request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.errors import ApiError
from app.models.auth_session import AuthSession
from app.models.user import User

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("watchly-dummy-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(
    session: Session, user: User, settings: Settings, user_agent: str | None
) -> tuple[str, AuthSession]:
    token = secrets.token_urlsafe(32)
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=hash_token(token),
        user_agent=(user_agent or "")[:300] or None,
        expires_at=datetime.now(UTC) + timedelta(days=settings.session_ttl_days),
    )
    session.add(auth_session)
    session.commit()
    return token, auth_session


def resolve_auth(session: Session, token: str | None) -> tuple[User, AuthSession] | None:
    if not token:
        return None
    row = session.execute(
        select(User, AuthSession)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(AuthSession.token_hash == hash_token(token))
    ).first()
    if row is None:
        return None
    user, auth_session = row
    if (
        auth_session.revoked_at is not None
        or auth_session.expires_at <= datetime.now(UTC)
        or not user.is_active
    ):
        return None
    return user, auth_session


def require_auth(session: Session) -> tuple[User, AuthSession]:
    cached = getattr(g, "auth", None)
    if cached is not None:
        return cast(tuple[User, AuthSession], cached)
    settings = get_settings()
    resolved = resolve_auth(session, request.cookies.get(settings.session_cookie_name))
    if resolved is None:
        raise ApiError(401, "unauthorized", "Autenticazione richiesta")
    g.auth = resolved
    return resolved


def current_user(session: Session) -> User:
    return require_auth(session)[0]


class RateLimiter:
    """Finestra scorrevole in memoria, per processo."""

    def __init__(self, limit: int, window_seconds: int, scope: str) -> None:
        self.limit, self.window, self.scope = limit, window_seconds, scope
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self) -> None:
        key = request.remote_addr or "unknown"
        token = request.cookies.get(get_settings().session_cookie_name)
        if token:
            key = hash_token(token)[:16]
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                retry = int(self.window - (now - hits[0])) + 1
                raise ApiError(
                    429,
                    "rate_limited",
                    "Troppe richieste, riprova più tardi",
                    {"scope": self.scope, "retry_after": retry},
                    headers={"Retry-After": str(retry)},
                )
            hits.append(now)


def new_request_id() -> str:
    return uuid.uuid4().hex
