from dflango.schemas import Schema, UtcDateTimeField
from marshmallow import fields, validate


class LoginRequest(Schema):
    email = fields.String(required=True, validate=validate.Length(min=3, max=320))
    password = fields.String(
        required=True, load_only=True, validate=validate.Length(min=1, max=256)
    )


class UserRead(Schema):
    id = fields.UUID(dump_only=True)
    email = fields.String(dump_only=True)
    display_name = fields.String(dump_only=True, allow_none=True)
    created_at = UtcDateTimeField(dump_only=True)
