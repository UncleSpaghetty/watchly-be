# Third-party
from sqlalchemy import select

from app.errors import ApiError

# Models
from app.models.user import User

# Schemas
from app.schemas.auth.login_request import LoginRequestSchema

# Services
from app.services.auth import login_limit, session_response

# Config
from app.settings.security import verify_password

# Views
from app.views.base import WatchlyView, load_json


class LoginView(WatchlyView):
    accepted_methods = ["POST"]
    authentication_required = False
    rate_limiter = login_limit

    def post(self):
        body = load_json(LoginRequestSchema())
        email = body["email"].strip().lower()
        user = self.session.scalar(select(User).where(User.email == email))
        valid = verify_password(user.password_hash if user else None, body["password"])
        if user is None or not valid or not user.is_active:
            raise ApiError(401, "invalid_credentials", "Credenziali non valide")
        return session_response(self.session, user)
