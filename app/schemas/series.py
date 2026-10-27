from datetime import UTC, datetime, timedelta
from typing import cast

from dflango.schemas import Schema, UtcDateTimeField
from marshmallow import fields

from app.models.series import Series
from app.settings.config import get_settings


class ExternalIdRead(Schema):
    source = fields.String(dump_only=True)
    external_id = fields.String(dump_only=True)


class SeriesRead(Schema):
    id = fields.UUID(dump_only=True)
    kind = fields.String(dump_only=True)
    title = fields.String(dump_only=True)
    original_title = fields.String(dump_only=True, allow_none=True)
    alternative_titles = fields.List(fields.String(), dump_only=True)
    poster_url = fields.String(dump_only=True, allow_none=True)
    synopsis = fields.String(dump_only=True, allow_none=True)
    status = fields.String(dump_only=True, allow_none=True)
    format = fields.String(dump_only=True, allow_none=True)
    genres = fields.List(fields.String(), dump_only=True)
    average_rating = fields.Float(dump_only=True, allow_none=True)
    rating_source = fields.String(dump_only=True, allow_none=True)
    episode_runtime_minutes = fields.Integer(dump_only=True, allow_none=True)
    year = fields.Integer(dump_only=True, allow_none=True)
    start_date = fields.Date(dump_only=True, allow_none=True)
    external_ids = fields.List(fields.Nested(ExternalIdRead), dump_only=True)
    last_synced_at = UtcDateTimeField(dump_only=True, allow_none=True)
    last_sync_status = fields.String(dump_only=True, allow_none=True)
    stale = fields.Boolean(dump_only=True)
    followed = fields.Boolean(dump_only=True)


class SeriesSummary(Schema):
    id = fields.UUID(dump_only=True)
    kind = fields.String(dump_only=True)
    title = fields.String(dump_only=True)
    poster_url = fields.String(dump_only=True, allow_none=True)
    average_rating = fields.Float(dump_only=True, allow_none=True)


def dump_series(series: Series, followed: bool = False) -> dict[str, object]:
    data = cast(dict[str, object], SeriesRead().dump(series))
    limit = datetime.now(UTC) - timedelta(hours=2 * get_settings().sync_interval_hours)
    data["stale"] = (
        series.last_sync_status == "error"
        or series.last_synced_at is None
        or series.last_synced_at < limit
    )
    data["followed"] = followed
    return data
