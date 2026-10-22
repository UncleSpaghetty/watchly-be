from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "production"
    database_url: str = "postgresql+psycopg://watchly_app:watchly@localhost:5432/watchly"
    log_level: str = "INFO"

    allowed_origins: Annotated[list[str], NoDecode] = []
    session_cookie_name: str = "watchly_session"
    session_cookie_secure: bool = True
    session_cookie_samesite: str = "lax"
    session_cookie_domain: str | None = None
    session_ttl_days: int = 30

    owner_email: str | None = None
    owner_password: str | None = None

    tmdb_read_token: str | None = None
    news_feed_urls: Annotated[list[str], NoDecode] = []

    vapid_private_key: str | None = None
    vapid_public_key: str | None = None
    vapid_subject: str = "mailto:admin@example.com"

    sync_interval_hours: int = 12
    sync_cooldown_seconds: int = 300
    news_refresh_minutes: int = 30
    worker_tick_seconds: int = 30

    @field_validator("allowed_origins", "news_feed_urls", mode="before")
    @classmethod
    def split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
