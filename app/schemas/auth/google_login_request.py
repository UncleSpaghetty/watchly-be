# dFlango
from dflango.schemas import Schema

# Third-party
from marshmallow import fields, validate


class GoogleLoginRequestSchema(Schema):
    credential = fields.String(
        required=True,
        load_only=True,
        validate=validate.Length(min=1, max=8192),
    )
