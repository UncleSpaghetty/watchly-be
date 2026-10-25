from dflango.schemas import Schema, UtcDateTimeField
from marshmallow import fields, validate


class PushKeys(Schema):
    p256dh = fields.String(required=True, validate=validate.Length(min=1, max=200))
    auth = fields.String(required=True, validate=validate.Length(min=1, max=100))


class PushSubscriptionCreate(Schema):
    endpoint = fields.Url(required=True)
    keys = fields.Nested(PushKeys, required=True)


class PushSubscriptionDelete(Schema):
    endpoint = fields.Url(required=True)


class PushSubscriptionRead(Schema):
    id = fields.UUID(dump_only=True)
    created_at = UtcDateTimeField(dump_only=True)
    last_success_at = UtcDateTimeField(dump_only=True, allow_none=True)


class VapidKeyRead(Schema):
    public_key = fields.String(dump_only=True, allow_none=True)
