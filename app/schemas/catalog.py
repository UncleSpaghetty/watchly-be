from dflango.schemas import Schema
from marshmallow import fields

from app.schemas.series import SeriesRead


class CatalogSearchResponse(Schema):
    results = fields.List(fields.Nested(SeriesRead), dump_only=True)
    provider_errors = fields.Dict(keys=fields.String(), values=fields.String(), dump_only=True)
