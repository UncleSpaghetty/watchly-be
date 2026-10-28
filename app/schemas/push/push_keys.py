# dFlango
from dflango.schemas import Schema

# Third-party
from marshmallow import fields, validate


class PushKeysSchema(Schema):
    p256dh = fields.String(required=True, validate=validate.Length(min=1, max=200))
    auth = fields.String(required=True, validate=validate.Length(min=1, max=100))
