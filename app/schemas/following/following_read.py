# dFlango
from dflango.schemas import Schema, UtcDateTimeField

# Third-party
from marshmallow import fields

# Schemas
from app.schemas.series.series_read import SeriesReadSchema


class FollowingReadSchema(Schema):
    series = fields.Nested(SeriesReadSchema, dump_only=True)
    followed_at = UtcDateTimeField(dump_only=True)
    notifications_enabled = fields.Boolean(dump_only=True, allow_none=True)
    next_air_date = fields.Date(dump_only=True, allow_none=True)
    watch_status = fields.String(dump_only=True)
    favorite = fields.Boolean(dump_only=True)
    status_updated_at = UtcDateTimeField(dump_only=True)
    aired_episodes = fields.Integer(dump_only=True)
    watched_episodes = fields.Integer(dump_only=True)
    backlog_episodes = fields.Integer(dump_only=True)
    next_unwatched_episode_id = fields.UUID(dump_only=True, allow_none=True)
