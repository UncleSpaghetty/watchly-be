import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id, utcnow


class EpisodeDateChange(Base):
    """Audit dei cambi di data di un episodio."""

    __tablename__ = "episode_date_changes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    episode_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    old_date: Mapped[date | None] = mapped_column(Date)
    new_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(20))
    changed_at: Mapped[datetime] = mapped_column(default=utcnow)
