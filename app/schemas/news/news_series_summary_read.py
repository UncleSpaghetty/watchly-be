# dFlango
from dflango.schemas import Schema

# Third-party
from marshmallow import fields


class NewsSeriesSummarySchema(Schema):
    id = fields.UUID(dump_only=True)
    title = fields.String(dump_only=True)
    followed = fields.Boolean(dump_only=True)
