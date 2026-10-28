# dFlango
from dflango.schemas import Schema

# Third-party
from marshmallow import fields


class PushSubscriptionDeleteSchema(Schema):
    endpoint = fields.Url(required=True)
