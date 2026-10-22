import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class Following(Base):
    __tablename__ = "following"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    series_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("series.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    followed_at: Mapped[datetime] = mapped_column(default=utcnow)
    notifications_enabled: Mapped[bool | None] = mapped_column(Boolean)
