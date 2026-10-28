# dFlango
from dflango.schemas import Schema

# Third-party
from marshmallow import fields

# Schemas
from app.schemas.push.push_keys import PushKeysSchema


class PushSubscriptionCreateSchema(Schema):
    endpoint = fields.Url(required=True)
    keys = fields.Nested(PushKeysSchema, required=True)
