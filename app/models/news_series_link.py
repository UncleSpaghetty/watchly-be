import uuid

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NewsSeriesLink(Base):
    __tablename__ = "news_series_links"
    __table_args__ = (CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence"),)

    news_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("news_articles.id", ondelete="CASCADE"), primary_key=True
    )
    series_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("series.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    match_method: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[float] = mapped_column(Float)
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
