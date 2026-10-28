# dFlango
from dflango.schemas import Schema, UtcDateTimeField

# Third-party
from marshmallow import fields


class UserReadSchema(Schema):
    id = fields.UUID(dump_only=True)
    email = fields.String(dump_only=True)
    display_name = fields.String(dump_only=True, allow_none=True)
    timezone = fields.String(dump_only=True)
    locale = fields.String(dump_only=True)
    created_at = UtcDateTimeField(dump_only=True)
