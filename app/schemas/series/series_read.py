# dFlango
from dflango.schemas import Schema, UtcDateTimeField

# Third-party
from marshmallow import fields

# Schemas
from app.schemas.series.external_id_read import ExternalIdReadSchema


class SeriesReadSchema(Schema):
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
    watch_providers = fields.List(fields.Dict(), dump_only=True)
    average_rating = fields.Float(dump_only=True, allow_none=True)
    rating_source = fields.String(dump_only=True, allow_none=True)
    episode_runtime_minutes = fields.Integer(dump_only=True, allow_none=True)
    year = fields.Integer(dump_only=True, allow_none=True)
    start_date = fields.Date(dump_only=True, allow_none=True)
    external_ids = fields.List(fields.Nested(ExternalIdReadSchema), dump_only=True)
    last_synced_at = UtcDateTimeField(dump_only=True, allow_none=True)
    last_sync_status = fields.String(dump_only=True, allow_none=True)
    stale = fields.Boolean(dump_only=True)
    followed = fields.Boolean(dump_only=True)
