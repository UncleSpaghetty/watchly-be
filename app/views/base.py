from datetime import date
from typing import Any, cast

from dflango.views import BaseView
from flask import g, request
from marshmallow import Schema
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models.session import get_session
from app.models.user import User
from app.settings.security import RateLimiter, require_auth


class WatchlyView(BaseView):
    """Base dflango con autenticazione a sessione opaca propria di Watchly."""

    authentication_required = True
    rate_limiter: RateLimiter | None = None

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.methods = set(cls.accepted_methods)

    def _check_endpoint_permissions(self):
        # Watchly usa ownership per risorsa e cookie opachi, non i JWT/ruoli di dflango.
        return None

    def _requires_authentication(self) -> bool:
        return False

    def _check_user_roles(self) -> bool:
        return True

    @property
    def session(self) -> Session:
        return get_session()

    @property
    def user(self) -> User:
        return cast(User, g.auth[0])

    def dispatch_request(self, *args: object, **kwargs: object) -> Any:
        if self.rate_limiter is not None:
            self.rate_limiter.check()
        if self.authentication_required:
            require_auth(self.session)
        return super().dispatch_request(*args, **kwargs)


def load_json(schema: Schema, *, partial: bool = False) -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if payload is None:
        raise ApiError(400, "invalid_json", "Corpo JSON richiesto")
    if not isinstance(payload, dict):
        raise ApiError(422, "validation_error", "Il corpo deve essere un oggetto JSON")
    return schema.load(payload, partial=partial)


def query_date(name: str) -> date:
    value = request.args.get(name)
    if not value:
        raise ApiError(422, "validation_error", f"Parametro {name} richiesto")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ApiError(422, "validation_error", f"Parametro {name} non valido") from exc


def query_bool(name: str) -> bool | None:
    value = request.args.get(name)
    if value is None:
        return None
    normalized = value.lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ApiError(422, "validation_error", f"Parametro {name} non valido")
