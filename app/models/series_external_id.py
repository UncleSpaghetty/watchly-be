import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.series import Series


class SeriesExternalId(Base):
    __tablename__ = "series_external_ids"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    series_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("series.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(20), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(100))

    series: Mapped[Series] = relationship(back_populates="external_ids")
