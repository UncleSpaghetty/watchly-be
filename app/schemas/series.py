from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.series import Series
from app.settings.config import get_settings


class ExternalIdRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    external_id: str


class SeriesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    title: str
    original_title: str | None
    alternative_titles: list[str]
    poster_url: str | None
    synopsis: str | None
    status: str | None
    format: str | None
    year: int | None
    start_date: date | None
    external_ids: list[ExternalIdRead]
    last_synced_at: datetime | None
    last_sync_status: str | None
    stale: bool = False
    followed: bool = False

    @classmethod
    def from_model(cls, series: Series, followed: bool = False) -> "SeriesRead":
        item = cls.model_validate(series)
        limit = datetime.now(UTC) - timedelta(hours=2 * get_settings().sync_interval_hours)
        item.stale = (
            series.last_sync_status == "error"
            or series.last_synced_at is None
            or series.last_synced_at < limit
        )
        item.followed = followed
        return item


class SeriesSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    title: str
    poster_url: str | None
