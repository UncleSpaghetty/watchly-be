import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class WatchedEpisode(Base):
    __tablename__ = "watched_episodes"
    __table_args__ = (Index("ix_watched_episodes_user_watched_at", "user_id", "watched_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    episode_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("episodes.id", ondelete="CASCADE"), primary_key=True
    )
    watched_at: Mapped[datetime] = mapped_column(default=utcnow)
