import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id, utcnow


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (UniqueConstraint("user_id", "local_date", "channel"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    local_date: Mapped[date] = mapped_column(Date)
    channel: Mapped[str] = mapped_column(String(20), default="webpush")
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending|sent|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    episode_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_attempt_at: Mapped[datetime | None]
    sent_at: Mapped[datetime | None]
