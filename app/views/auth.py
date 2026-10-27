from datetime import UTC, datetime

from flask import make_response, request
from flask.wrappers import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models.user import User
from app.schemas.auth import GoogleLoginRequest, LoginRequest, UserRead
from app.services.google_auth import (
    GoogleIdentityConflict,
    GoogleIdentityUnavailable,
    InvalidGoogleCredential,
    resolve_google_user,
    verify_google_credential,
)
from app.settings.config import get_settings
from app.settings.security import RateLimiter, create_session, verify_password
from app.views.base import WatchlyView, load_json

login_limit = RateLimiter(limit=10, window_seconds=300, scope="login")


def _session_response(session: Session, user: User) -> Response:
    settings = get_settings()
    token, _ = create_session(
        session,
        user,
        settings,
        request.headers.get("user-agent"),
    )
    response = make_response(UserRead().dump(user), 200)
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


class LoginView(WatchlyView):
    accepted_methods = ["POST"]
    authentication_required = False
    rate_limiter = login_limit

    def post(self):
        body = load_json(LoginRequest())
        email = body["email"].strip().lower()
        user = self.session.scalar(select(User).where(User.email == email))
        valid = verify_password(user.password_hash if user else None, body["password"])
        if user is None or not valid or not user.is_active:
            raise ApiError(401, "invalid_credentials", "Credenziali non valide")
        return _session_response(self.session, user)


class GoogleLoginView(WatchlyView):
    accepted_methods = ["POST"]
    authentication_required = False
    rate_limiter = login_limit

    def post(self):
        settings = get_settings()
        if not settings.google_client_id:
            raise ApiError(
                503,
                "auth_provider_unavailable",
                "Accesso con Google non configurato",
            )
        body = load_json(GoogleLoginRequest())
        try:
            claims = verify_google_credential(body["credential"], settings.google_client_id)
        except InvalidGoogleCredential as exc:
            raise ApiError(
                401,
                "invalid_google_credential",
                "Credenziale Google non valida",
            ) from exc
        except GoogleIdentityUnavailable as exc:
            raise ApiError(
                503,
                "auth_provider_unavailable",
                "Verifica Google temporaneamente non disponibile",
            ) from exc

        try:
            user = resolve_google_user(self.session, claims)
        except GoogleIdentityConflict as exc:
            raise ApiError(
                409,
                "identity_conflict",
                "Questo account Watchly è già collegato a un altro account Google",
            ) from exc
        if not user.is_active:
            raise ApiError(401, "invalid_google_credential", "Credenziale Google non valida")
        return _session_response(self.session, user)


class LogoutView(WatchlyView):
    accepted_methods = ["POST"]

    def post(self):
        settings = get_settings()
        self.session_auth.revoked_at = datetime.now(UTC)
        self.session.commit()
        response = make_response("", 204)
        response.delete_cookie(
            settings.session_cookie_name, path="/", domain=settings.session_cookie_domain
        )
        return response

    @property
    def session_auth(self):
        from flask import g

        return g.auth[1]


class MeView(WatchlyView):
    accepted_methods = ["GET", "DELETE"]

    def get(self):
        return UserRead().dump(self.user), 200

    def delete(self):
        self.session.delete(self.user)
        self.session.commit()
        return "", 204
