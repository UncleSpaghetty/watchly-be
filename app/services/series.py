# Built-in
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

# Third party
from sqlalchemy.orm import Session

# Configuration
from app.config import get_settings

# Exceptions
from app.errors import ApiError

# Models
from app.models.series import Series

# Schemas
from app.schemas.series.series_read import SeriesReadSchema


def dump_series(series: Series, followed: bool = False) -> dict[str, object]:
    data = cast(
        dict[str, object],
        SeriesReadSchema().dump(series),  # type: ignore[no-untyped-call]
    )
    limit = datetime.now(UTC) - timedelta(hours=2 * get_settings().sync_interval_hours)
    data["stale"] = (
        series.last_sync_status == "error"
        or series.last_synced_at is None
        or series.last_synced_at < limit
    )
    data["followed"] = followed
    return data


def get_series_or_404(session: Session, series_id: UUID) -> Series:
    series = session.get(Series, series_id)
    if series is None:
        raise ApiError(404, "series_not_found", "Serie non trovata")
    return series
