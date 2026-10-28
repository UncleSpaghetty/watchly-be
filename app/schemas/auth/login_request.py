# dFlango
from dflango.schemas import Schema

# Third-party
from marshmallow import fields, validate


class LoginRequestSchema(Schema):
    email = fields.String(required=True, validate=validate.Length(min=3, max=320))
    password = fields.String(
        required=True,
        load_only=True,
        validate=validate.Length(min=1, max=256),
    )
