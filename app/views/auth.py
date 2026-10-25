from datetime import UTC, datetime

from flask import make_response, request
from sqlalchemy import select

from app.errors import ApiError
from app.models.user import User
from app.schemas.auth import LoginRequest, UserRead
from app.settings.config import get_settings
from app.settings.security import RateLimiter, create_session, verify_password
from app.views.base import WatchlyView, load_json

login_limit = RateLimiter(limit=10, window_seconds=300, scope="login")


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
        settings = get_settings()
        token, _ = create_session(self.session, user, settings, request.headers.get("user-agent"))
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
