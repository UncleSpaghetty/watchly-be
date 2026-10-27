from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from google.auth.exceptions import GoogleAuthError, TransportError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.user import User
from app.models.user_identity import UserIdentity

PROVIDER = "google"


class InvalidGoogleCredential(ValueError):
    pass


class GoogleIdentityUnavailable(RuntimeError):
    pass


class GoogleIdentityConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GoogleClaims:
    subject: str
    email: str
    display_name: str | None
    email_authoritative: bool


def _required_string(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise InvalidGoogleCredential(f"Claim Google mancante: {name}")
    return value.strip()


def verify_google_credential(credential: str, client_id: str) -> GoogleClaims:
    verify_token = cast(
        Callable[[str, GoogleRequest, str], dict[str, Any]],
        id_token.verify_oauth2_token,
    )
    try:
        payload = verify_token(
            credential,
            GoogleRequest(),
            client_id,
        )
    except TransportError as exc:
        raise GoogleIdentityUnavailable("Verifica Google temporaneamente non disponibile") from exc
    except (GoogleAuthError, ValueError) as exc:
        raise InvalidGoogleCredential("Credenziale Google non valida") from exc

    subject = _required_string(payload, "sub")
    email = _required_string(payload, "email").lower()
    if payload.get("email_verified") is not True:
        raise InvalidGoogleCredential("L'indirizzo Google non è verificato")

    raw_name = payload.get("name")
    display_name = (
        raw_name.strip()[:100] if isinstance(raw_name, str) and raw_name.strip() else None
    )
    hosted_domain = payload.get("hd")
    email_authoritative = email.endswith("@gmail.com") or (
        isinstance(hosted_domain, str) and bool(hosted_domain.strip())
    )
    return GoogleClaims(
        subject=subject,
        email=email,
        display_name=display_name,
        email_authoritative=email_authoritative,
    )


def _identity_by_subject(db: Session, subject: str) -> UserIdentity | None:
    return db.scalar(
        select(UserIdentity).where(
            UserIdentity.provider == PROVIDER,
            UserIdentity.subject == subject,
        )
    )


def resolve_google_user(db: Session, claims: GoogleClaims) -> User:
    """Trova o crea l'utente applicativo usando `sub` come identità stabile."""
    identity = _identity_by_subject(db, claims.subject)
    if identity is not None:
        user = db.get(User, identity.user_id)
        if user is None:  # pragma: no cover - impedito dalla foreign key
            raise RuntimeError("Identità Google senza utente")
        identity.email = claims.email
        identity.last_login_at = utcnow()
        if user.display_name is None and claims.display_name:
            user.display_name = claims.display_name
        db.commit()
        return user

    user = db.scalar(select(User).where(User.email == claims.email))
    if user is not None:
        if not claims.email_authoritative:
            raise GoogleIdentityConflict(
                "Google non è autoritativo per l'email dell'account esistente"
            )
        linked_identity = db.scalar(
            select(UserIdentity).where(
                UserIdentity.user_id == user.id,
                UserIdentity.provider == PROVIDER,
            )
        )
        if linked_identity is not None:
            raise GoogleIdentityConflict("Utente già collegato a un'altra identità Google")

    try:
        if user is None:
            user = User(
                email=claims.email,
                password_hash=None,
                display_name=claims.display_name,
            )
            db.add(user)
            db.flush()

        identity = UserIdentity(
            user_id=user.id,
            provider=PROVIDER,
            subject=claims.subject,
            email=claims.email,
            last_login_at=utcnow(),
        )
        db.add(identity)
        db.commit()
    except IntegrityError as exc:
        # Due primi accessi concorrenti possono provare a creare la stessa
        # identità. Il vincitore è ora leggibile: si riusa il suo utente.
        db.rollback()
        identity = _identity_by_subject(db, claims.subject)
        if identity is None:
            raise GoogleIdentityConflict("Email già collegata a un'altra identità") from exc
        user = db.get(User, identity.user_id)
        if user is None:  # pragma: no cover - impedito dalla foreign key
            raise RuntimeError("Identità Google senza utente") from exc
    return user
