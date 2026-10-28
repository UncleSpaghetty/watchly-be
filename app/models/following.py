import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class Following(Base):
    __tablename__ = "following"
    __table_args__ = (
        CheckConstraint(
            "watch_status IN ('in_list', 'planned', 'watching', 'paused', 'completed', 'dropped')",
            name="watch_status",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    series_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("series.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    followed_at: Mapped[datetime] = mapped_column(default=utcnow)
    notifications_enabled: Mapped[bool | None] = mapped_column(Boolean)
    watch_status: Mapped[str] = mapped_column(String(20), default="in_list")
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    status_updated_at: Mapped[datetime] = mapped_column(default=utcnow)
