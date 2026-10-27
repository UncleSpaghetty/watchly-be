import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, CheckConstraint, Date, Float, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, new_id, utcnow

if TYPE_CHECKING:
    from app.models.series_external_id import SeriesExternalId


class Series(Base):
    __tablename__ = "series"
    __table_args__ = (CheckConstraint("kind IN ('anime', 'tv')", name="kind"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(10), index=True)
    title: Mapped[str] = mapped_column(String(500))
    original_title: Mapped[str | None] = mapped_column(String(500))
    alternative_titles: Mapped[list[Any]] = mapped_column(JSON, default=list)
    poster_url: Mapped[str | None] = mapped_column(String(1000))
    synopsis: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(50))
    format: Mapped[str | None] = mapped_column(String(50))
    genres: Mapped[list[str]] = mapped_column(JSON, default=list)
    average_rating: Mapped[float | None] = mapped_column(Float)
    rating_source: Mapped[str | None] = mapped_column(String(20))
    episode_runtime_minutes: Mapped[int | None] = mapped_column(Integer)
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    start_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    last_synced_at: Mapped[datetime | None]
    last_sync_status: Mapped[str | None] = mapped_column(String(20))
    last_sync_error: Mapped[str | None] = mapped_column(String(300))

    external_ids: Mapped[list["SeriesExternalId"]] = relationship(
        back_populates="series", cascade="all, delete-orphan", lazy="selectin"
    )
