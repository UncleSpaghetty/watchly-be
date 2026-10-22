from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.series import SeriesSummary


class NewsRead(BaseModel):
    id: UUID
    source: str
    url: str
    title: str
    published_at: datetime | None
    excerpt: str | None
    image_url: str | None
    series: list[SeriesSummary]
    confidence: float | None = None


class NewsPage(BaseModel):
    items: list[NewsRead]
    next_cursor: str | None
