import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Rome")
    locale: Mapped[str] = mapped_column(String(16), default="it-IT")
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_local_time: Mapped[str] = mapped_column(String(5), default="12:00")
    notification_quiet_start: Mapped[str | None] = mapped_column(String(5))
    notification_quiet_end: Mapped[str | None] = mapped_column(String(5))
    notification_lead_days: Mapped[int] = mapped_column(Integer, default=0)
    notify_releases: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_schedule_changes: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_new_seasons: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_news: Mapped[bool] = mapped_column(Boolean, default=False)
    weekly_digest: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_services: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_successful_sync_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
