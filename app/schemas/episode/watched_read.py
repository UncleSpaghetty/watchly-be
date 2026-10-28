# dFlango
from dflango.schemas import Schema, UtcDateTimeField

# Third-party
from marshmallow import fields


class WatchedReadSchema(Schema):
    episode_id = fields.UUID(dump_only=True)
    watched = fields.Boolean(dump_only=True)
    watched_at = UtcDateTimeField(dump_only=True, allow_none=True)
