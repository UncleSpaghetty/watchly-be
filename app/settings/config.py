import os
from dataclasses import dataclass, fields
from functools import lru_cache

from dotenv import load_dotenv


def _boolean(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


@dataclass(frozen=True, slots=True)
class Settings:
    """Configurazione Watchly caricata dall'ambiente e inoltrata a Flask/dflango."""

    environment: str = "production"
    database_url: str = "postgresql+psycopg://watchly_app:watchly@localhost:5432/watchly"
    log_level: str = "INFO"
    allowed_origins: tuple[str, ...] = ()
    session_cookie_name: str = "watchly_session"
    session_cookie_secure: bool = True
    session_cookie_samesite: str = "lax"
    session_cookie_domain: str | None = None
    session_ttl_days: int = 30
    google_client_id: str | None = None
    owner_email: str | None = None
    owner_password: str | None = None
    tmdb_read_token: str | None = None
    news_feed_urls: tuple[str, ...] = ()
    vapid_private_key: str | None = None
    vapid_public_key: str | None = None
    vapid_subject: str = "mailto:admin@example.com"
    sync_interval_hours: int = 12
    sync_cooldown_seconds: int = 300
    news_refresh_minutes: int = 30
    worker_tick_seconds: int = 30

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(override=False)
        return cls(
            environment=os.getenv("ENVIRONMENT", "production"),
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql+psycopg://watchly_app:watchly@localhost:5432/watchly",
            ),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            allowed_origins=tuple(_csv(os.getenv("ALLOWED_ORIGINS"))),
            session_cookie_name=os.getenv("SESSION_COOKIE_NAME", "watchly_session"),
            session_cookie_secure=_boolean(os.getenv("SESSION_COOKIE_SECURE"), True),
            session_cookie_samesite=os.getenv("SESSION_COOKIE_SAMESITE", "lax"),
            session_cookie_domain=os.getenv("SESSION_COOKIE_DOMAIN") or None,
            session_ttl_days=int(os.getenv("SESSION_TTL_DAYS", "30")),
            google_client_id=os.getenv("GOOGLE_CLIENT_ID") or None,
            owner_email=os.getenv("OWNER_EMAIL") or None,
            owner_password=os.getenv("OWNER_PASSWORD") or None,
            tmdb_read_token=os.getenv("TMDB_READ_TOKEN") or None,
            news_feed_urls=tuple(_csv(os.getenv("NEWS_FEED_URLS"))),
            vapid_private_key=os.getenv("VAPID_PRIVATE_KEY") or None,
            vapid_public_key=os.getenv("VAPID_PUBLIC_KEY") or None,
            vapid_subject=os.getenv("VAPID_SUBJECT", "mailto:admin@example.com"),
            sync_interval_hours=int(os.getenv("SYNC_INTERVAL_HOURS", "12")),
            sync_cooldown_seconds=int(os.getenv("SYNC_COOLDOWN_SECONDS", "300")),
            news_refresh_minutes=int(os.getenv("NEWS_REFRESH_MINUTES", "30")),
            worker_tick_seconds=int(os.getenv("WORKER_TICK_SECONDS", "30")),
        )

    def flask_config(self) -> dict[str, object]:
        allowed = [origin.rstrip("/") for origin in self.allowed_origins]
        config: dict[str, object] = {
            "SQLALCHEMY_DATABASE_URI": self.database_url,
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "CORS_ORIGINS": allowed,
            "CORS_ALLOW_HEADERS": ["Content-Type", "X-Request-ID", "X-Requested-With", "DNT"],
            "CORS_SUPPORTS_CREDENTIALS": True,
            "DFLANGO_CORS_ORIGINS": allowed,
            "DFLANGO_CORS_ALLOW_HEADERS": [
                "Content-Type",
                "X-Request-ID",
                "X-Requested-With",
                "DNT",
            ],
            "DFLANGO_CORS_SUPPORTS_CREDENTIALS": True,
            "DFLANGO_APPEND_SLASH": False,
        }
        config.update({field.name.upper(): getattr(self, field.name) for field in fields(self)})
        return config


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
