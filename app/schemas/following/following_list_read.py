# dFlango
from dflango.schemas import Schema

# Third-party
from marshmallow import fields

# Schemas
from app.schemas.following.following_read import FollowingReadSchema


class FollowingListSchema(Schema):
    items = fields.List(fields.Nested(FollowingReadSchema), dump_only=True)
