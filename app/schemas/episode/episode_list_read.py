# dFlango
from dflango.schemas import Schema, UtcDateTimeField

# Third-party
from marshmallow import fields

# Schemas
from app.schemas.episode.episode_read import EpisodeReadSchema


class EpisodeListResponseSchema(Schema):
    episodes = fields.List(fields.Nested(EpisodeReadSchema), dump_only=True)
    last_synced_at = UtcDateTimeField(dump_only=True, allow_none=True)
    sync_status = fields.String(dump_only=True, allow_none=True)
    stale = fields.Boolean(dump_only=True)
