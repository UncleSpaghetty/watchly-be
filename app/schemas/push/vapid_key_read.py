# dFlango
from dflango.schemas import Schema

# Third-party
from marshmallow import fields


class VapidKeyReadSchema(Schema):
    public_key = fields.String(dump_only=True, allow_none=True)
