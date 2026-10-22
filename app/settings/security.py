import hashlib
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models.auth_session import AuthSession
from app.models.session import get_db
from app.models.user import User
from app.settings.config import Settings, get_settings

_hasher = PasswordHasher()
# Hash fittizio: il login a tempo costante non rivela se l'utente esiste.
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
    db: Session, user: User, settings: Settings, user_agent: str | None
) -> tuple[str, AuthSession]:
    token = secrets.token_urlsafe(32)
    session = AuthSession(
        user_id=user.id,
        token_hash=hash_token(token),
        user_agent=(user_agent or "")[:300] or None,
        expires_at=datetime.now(UTC) + timedelta(days=settings.session_ttl_days),
    )
    db.add(session)
    db.commit()
    return token, session


def _resolve(db: Session, token: str | None) -> tuple[User, AuthSession] | None:
    if not token:
        return None
    row = db.execute(
        select(User, AuthSession)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(AuthSession.token_hash == hash_token(token))
    ).first()
    if row is None:
        return None
    user, auth = row
    if auth.revoked_at is not None or auth.expires_at <= datetime.now(UTC) or not user.is_active:
        return None
    return user, auth


def get_auth(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> tuple[User, AuthSession]:
    resolved = _resolve(db, request.cookies.get(settings.session_cookie_name))
    if resolved is None:
        raise ApiError(401, "unauthorized", "Autenticazione richiesta")
    return resolved


def get_current_user(auth: Annotated[tuple[User, AuthSession], Depends(get_auth)]) -> User:
    return auth[0]


CurrentUser = Annotated[User, Depends(get_current_user)]
Db = Annotated[Session, Depends(get_db)]


class RateLimiter:
    """Finestra scorrevole in memoria, per processo. Sufficiente per un singolo container API;
    con più repliche va sostituito con un contatore condiviso (Redis)."""

    def __init__(self, limit: int, window_seconds: int, scope: str) -> None:
        self.limit, self.window, self.scope = limit, window_seconds, scope
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def __call__(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        user = request.cookies.get(get_settings().session_cookie_name)
        if user:
            key = hash_token(user)[:16]
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
