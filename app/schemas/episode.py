from dflango.schemas import Schema, UtcDateTimeField
from marshmallow import fields


class EpisodeRead(Schema):
    id = fields.UUID(dump_only=True)
    series_id = fields.UUID(dump_only=True)
    season_number = fields.Integer(dump_only=True, allow_none=True)
    episode_number = fields.Integer(dump_only=True, allow_none=True)
    title = fields.String(dump_only=True, allow_none=True)
    air_at = UtcDateTimeField(dump_only=True, allow_none=True)
    air_date = fields.Date(dump_only=True, allow_none=True)
    source = fields.String(dump_only=True)
    watched = fields.Boolean(dump_only=True)


class EpisodeListResponse(Schema):
    episodes = fields.List(fields.Nested(EpisodeRead), dump_only=True)
    last_synced_at = UtcDateTimeField(dump_only=True, allow_none=True)
    sync_status = fields.String(dump_only=True, allow_none=True)
    stale = fields.Boolean(dump_only=True)


class WatchedRead(Schema):
    episode_id = fields.UUID(dump_only=True)
    watched = fields.Boolean(dump_only=True)
    watched_at = UtcDateTimeField(dump_only=True, allow_none=True)
