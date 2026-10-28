# Flask
from flask import make_response, request
from flask.wrappers import Response

# Third-party
from sqlalchemy.orm import Session

# Config
from app.config import get_settings

# Models
from app.models.user import User

# Schemas
from app.schemas.auth.user_read import UserReadSchema
from app.settings.security import RateLimiter, create_session

login_limit = RateLimiter(limit=10, window_seconds=300, scope="login")


def session_response(session: Session, user: User) -> Response:
    settings = get_settings()
    token, _ = create_session(
        session,
        user,
        settings,
        request.headers.get("user-agent"),
    )
    response = make_response(UserReadSchema().dump(user), 200)  # type: ignore[no-untyped-call]
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.session_cookie_domain,
        path="/",
    )
    return response
