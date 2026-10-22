from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProviderCache(Base):
    """ETag / Last-Modified per fetch condizionali dei provider."""

    __tablename__ = "provider_cache"

    key: Mapped[str] = mapped_column(String(1000), primary_key=True)
    etag: Mapped[str | None] = mapped_column(String(300))
    last_modified: Mapped[str | None] = mapped_column(String(100))
    fetched_at: Mapped[datetime]
    last_status: Mapped[str | None] = mapped_column(String(20))
