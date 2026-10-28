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
