from dflango.schemas import Schema, UtcDateTimeField
from marshmallow import fields



class NewsSeriesSummary(Schema):
    id = fields.UUID(dump_only=True)
    title = fields.String(dump_only=True)
    followed = fields.Boolean(dump_only=True)


class NewsRead(Schema):
    id = fields.UUID(dump_only=True)
    source = fields.String(dump_only=True)
    url = fields.String(dump_only=True)
    title = fields.String(dump_only=True)
    published_at = UtcDateTimeField(dump_only=True, allow_none=True)
    excerpt = fields.String(dump_only=True, allow_none=True)
    image_url = fields.String(dump_only=True, allow_none=True)
    series = fields.List(fields.Nested(NewsSeriesSummary), dump_only=True)
    confidence = fields.Float(dump_only=True, allow_none=True)


class NewsPage(Schema):
    items = fields.List(fields.Nested(NewsRead), dump_only=True)
    next_cursor = fields.String(dump_only=True, allow_none=True)
    configured = fields.Boolean(dump_only=True)
