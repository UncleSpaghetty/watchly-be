import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.data_source import DataSource
from app.models.user import User
from app.settings.config import Settings
from app.settings.security import hash_password

logger = logging.getLogger(__name__)

# Nessuna fonte parte come «validata per la disponibilità italiana»: va deciso dopo il gate
# di fattibilità documentato nell'analisi tecnica (§5).
DEFAULT_SOURCES = [
    ("kitsu", "Kitsu", "https://kitsu.io/api/docs"),
    ("anilist", "AniList", "https://anilist.gitbook.io/anilist-apiv2-docs"),
    ("tmdb", "TMDB", "https://www.themoviedb.org/api-terms-of-use"),
]


def seed_reference_data(db: Session) -> None:
    for source_id, name, terms in DEFAULT_SOURCES:
        if db.get(DataSource, source_id) is None:
            db.add(DataSource(id=source_id, name=name, terms_url=terms))
    db.commit()


def ensure_owner(db: Session, email: str, password: str) -> User:
    email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, password_hash=hash_password(password), display_name="Owner")
        db.add(user)
        db.commit()
        logger.info("owner account created")
    return user


def bootstrap(db: Session, settings: Settings) -> None:
    """Seed idempotente; la registrazione pubblica non esiste, l'unico utente è l'owner."""
    seed_reference_data(db)
    if settings.owner_email and settings.owner_password:
        ensure_owner(db, settings.owner_email, settings.owner_password)
