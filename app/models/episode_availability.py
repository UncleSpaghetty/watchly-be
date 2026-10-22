import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id


class EpisodeAvailability(Base):
    __tablename__ = "episode_availability"
    __table_args__ = (
        CheckConstraint("country_code = 'IT'", name="country"),
        CheckConstraint("precision IN ('timestamp', 'date')", name="precision_values"),
        CheckConstraint(
            "status IN ('confirmed', 'estimated', 'unknown', 'disputed', 'withdrawn')",
            name="status_values",
        ),
        CheckConstraint(
            "(precision = 'timestamp' AND available_at_utc IS NOT NULL "
            "AND available_local_date IS NOT NULL) "
            "OR (precision = 'date' AND available_local_date IS NOT NULL "
            "AND available_at_utc IS NULL) "
            "OR (precision IS NULL AND available_at_utc IS NULL "
            "AND available_local_date IS NULL)",
            name="precision_consistency",
        ),
        CheckConstraint(
            "status <> 'confirmed' OR (evidence_type IS NOT NULL AND precision IS NOT NULL)",
            name="confirmed_has_evidence",
        ),
        Index("ix_availability_episode_service", "episode_id", "service_id", "country_code"),
        Index("ix_availability_local_date_status", "available_local_date", "status"),
        Index("uq_availability_source_record", "source_id", "source_record_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    episode_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"))
    country_code: Mapped[str] = mapped_column(String(2), default="IT")
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"))
    available_at_utc: Mapped[datetime | None]
    available_local_date: Mapped[date | None] = mapped_column(Date)
    precision: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10))
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    source_record_id: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    evidence_type: Mapped[str | None] = mapped_column(String(50))
    observed_at: Mapped[datetime]
    last_verified_at: Mapped[datetime | None]
    invalidated_at: Mapped[datetime | None]
