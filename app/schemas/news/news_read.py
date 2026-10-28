# dFlango
from dflango.schemas import Schema, UtcDateTimeField

# Third-party
from marshmallow import fields

# Schemas
from app.schemas.news.news_series_summary_read import NewsSeriesSummarySchema


class NewsReadSchema(Schema):
    id = fields.UUID(dump_only=True)
    source = fields.String(dump_only=True)
    url = fields.String(dump_only=True)
    title = fields.String(dump_only=True)
    published_at = UtcDateTimeField(dump_only=True, allow_none=True)
    excerpt = fields.String(dump_only=True, allow_none=True)
    image_url = fields.String(dump_only=True, allow_none=True)
    category = fields.String(dump_only=True, allow_none=True)
    series = fields.List(fields.Nested(NewsSeriesSummarySchema), dump_only=True)
    confidence = fields.Float(dump_only=True, allow_none=True)
    saved = fields.Boolean(dump_only=True)
    read_at = UtcDateTimeField(dump_only=True, allow_none=True)
