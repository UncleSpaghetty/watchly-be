# dFlango
from dflango.schemas import Schema

# Third-party
from marshmallow import fields

# Schemas
from app.schemas.series.series_read import SeriesReadSchema


class CatalogSearchResponseSchema(Schema):
    results = fields.List(fields.Nested(SeriesReadSchema), dump_only=True)
    provider_errors = fields.Dict(
        keys=fields.String(),
        values=fields.String(),
        dump_only=True,
    )
