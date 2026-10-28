# dFlango
from dflango import ModelSchema

# Third-party
from marshmallow import fields

# Models
from app.models.following import Following


class FollowingUpdateSchema(ModelSchema):
    notifications_enabled = fields.Boolean(allow_none=True)

    class Meta:
        model = Following
