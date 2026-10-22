from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.schemas.episode import AvailabilityRead
from app.schemas.series import SeriesSummary


class CalendarItem(BaseModel):
    episode_id: UUID
    series: SeriesSummary
    season_number: int | None
    episode_number: int | None
    title: str | None
    local_date: date  # Europe/Rome
    date_kind: str  # "italy" = disponibilità IT confermata, "original" = uscita originale
    italy: AvailabilityRead
    watched: bool


class CalendarResponse(BaseModel):
    start: date
    end: date
    timezone: str
    items: list[CalendarItem]
