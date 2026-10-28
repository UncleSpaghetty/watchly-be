# dFlango
from dflango.schemas import Schema, UtcDateTimeField

# Third-party
from marshmallow import fields


class EpisodeReadSchema(Schema):
    id = fields.UUID(dump_only=True)
    series_id = fields.UUID(dump_only=True)
    season_number = fields.Integer(dump_only=True, allow_none=True)
    episode_number = fields.Integer(dump_only=True, allow_none=True)
    title = fields.String(dump_only=True, allow_none=True)
    duration_minutes = fields.Integer(dump_only=True, allow_none=True)
    air_at = UtcDateTimeField(dump_only=True, allow_none=True)
    air_date = fields.Date(dump_only=True, allow_none=True)
    source = fields.String(dump_only=True)
    watched = fields.Boolean(dump_only=True)
