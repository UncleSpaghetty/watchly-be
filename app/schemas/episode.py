from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class AvailabilityRead(BaseModel):
    """Disponibilità italiana, distinta dalla data di uscita originale."""

    status: str  # confirmed | estimated | disputed | withdrawn | unknown
    service_id: str | None = None
    local_date: date | None = None
    source_id: str | None = None
    source_url: str | None = None
    evidence_type: str | None = None


class EpisodeRead(BaseModel):
    id: UUID
    series_id: UUID
    season_number: int | None
    episode_number: int | None
    title: str | None
    original_air_at: datetime | None
    original_air_date: date | None
    italy: AvailabilityRead
    watched: bool = False


class EpisodeListResponse(BaseModel):
    episodes: list[EpisodeRead]
    last_synced_at: datetime | None
    sync_status: str | None
    stale: bool


class WatchedRead(BaseModel):
    episode_id: UUID
    watched: bool
    watched_at: datetime | None
