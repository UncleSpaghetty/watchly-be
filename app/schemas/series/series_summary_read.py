# dFlango
from dflango.schemas import Schema

# Third-party
from marshmallow import fields


class SeriesSummarySchema(Schema):
    id = fields.UUID(dump_only=True)
    kind = fields.String(dump_only=True)
    title = fields.String(dump_only=True)
    poster_url = fields.String(dump_only=True, allow_none=True)
    average_rating = fields.Float(dump_only=True, allow_none=True)
