from app.config import get_settings
from app.errors import ApiError

# Schemas
from app.schemas.auth.google_login_request import GoogleLoginRequestSchema

# Services
from app.services.auth import login_limit, session_response
from app.services.google_auth import (
    GoogleIdentityConflict,
    GoogleIdentityUnavailable,
    InvalidGoogleCredential,
    resolve_google_user,
    verify_google_credential,
)

# Views
from app.views.base import WatchlyView, load_json


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
        body = load_json(GoogleLoginRequestSchema())
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
        return session_response(self.session, user)
