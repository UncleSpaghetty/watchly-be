# dFlango
from dflango import ModelSchema

# Third-party
from marshmallow import fields, validate

# Models
from app.models.following import Following


class FollowingUpdateSchema(ModelSchema):
    notifications_enabled = fields.Boolean(allow_none=True)
    watch_status = fields.String(
        validate=validate.OneOf(
            ["in_list", "planned", "watching", "paused", "completed", "dropped"]
        )
    )
    favorite = fields.Boolean()

    class Meta:
        model = Following
