# dFlango
from dflango.schemas import Schema

# Third-party
from marshmallow import fields


class ExternalIdReadSchema(Schema):
    source = fields.String(dump_only=True)
    external_id = fields.String(dump_only=True)
