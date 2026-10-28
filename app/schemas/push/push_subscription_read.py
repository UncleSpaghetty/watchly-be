# dFlango
from dflango.schemas import Schema, UtcDateTimeField

# Third-party
from marshmallow import fields


class PushSubscriptionReadSchema(Schema):
    id = fields.UUID(dump_only=True)
    created_at = UtcDateTimeField(dump_only=True)
    last_success_at = UtcDateTimeField(dump_only=True, allow_none=True)
