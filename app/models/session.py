from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.settings.config import get_settings

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = get_settings().database_url
        kwargs: dict[str, object] = {}
        if not url.startswith("sqlite"):
            kwargs.update(pool_pre_ping=True, pool_size=5, max_overflow=5)
        _engine = create_engine(url, **kwargs)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _factory
    if _factory is None:
        _factory = sessionmaker(get_engine(), expire_on_commit=False)
    return _factory


def get_db() -> Iterator[Session]:
    """Sessione per richiesta; le view mutanti eseguono commit esplicito, il resto è rollback."""
    with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
