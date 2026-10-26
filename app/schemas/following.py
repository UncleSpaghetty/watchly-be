from dflango import ModelSchema
from dflango.schemas import Schema, UtcDateTimeField
from marshmallow import fields

from app.models.following import Following
from app.schemas.series import SeriesRead


class FollowingRead(Schema):
    series = fields.Nested(SeriesRead, dump_only=True)
    followed_at = UtcDateTimeField(dump_only=True)
    notifications_enabled = fields.Boolean(dump_only=True, allow_none=True)
    next_air_date = fields.Date(dump_only=True, allow_none=True)


class FollowingUpdate(ModelSchema):
    notifications_enabled = fields.Boolean(allow_none=True)

    class Meta:
        model = Following


class FollowingList(Schema):
    items = fields.List(fields.Nested(FollowingRead), dump_only=True)
