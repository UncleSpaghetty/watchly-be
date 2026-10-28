# dFlango
from dflango.schemas import Schema

# Third-party
from marshmallow import fields

# Schemas
from app.schemas.news.news_read import NewsReadSchema


class NewsPageSchema(Schema):
    items = fields.List(fields.Nested(NewsReadSchema), dump_only=True)
    next_cursor = fields.String(dump_only=True, allow_none=True)
    configured = fields.Boolean(dump_only=True)
