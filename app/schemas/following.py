from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.series import SeriesRead


class FollowingRead(BaseModel):
    series: SeriesRead
    followed_at: datetime
    notifications_enabled: bool | None
    next_italy_date: date | None = None


class FollowingUpdate(BaseModel):
    notifications_enabled: bool | None = None


class FollowingList(BaseModel):
    items: list[FollowingRead]


class FollowedId(BaseModel):
    series_id: UUID
