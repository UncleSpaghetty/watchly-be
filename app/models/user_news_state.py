import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class UserNewsState(Base):
    __tablename__ = "user_news_states"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    news_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("news_articles.id", ondelete="CASCADE"), primary_key=True
    )
    saved: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
