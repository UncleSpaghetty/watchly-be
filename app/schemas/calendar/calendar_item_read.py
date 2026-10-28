# dFlango
from dflango.schemas import Schema

# Third-party
from marshmallow import fields

# Schemas
from app.schemas.series.series_summary_read import SeriesSummarySchema


class CalendarItemSchema(Schema):
    episode_id = fields.UUID(dump_only=True)
    series = fields.Nested(SeriesSummarySchema, dump_only=True)
    season_number = fields.Integer(dump_only=True, allow_none=True)
    episode_number = fields.Integer(dump_only=True, allow_none=True)
    title = fields.String(dump_only=True, allow_none=True)
    air_date = fields.Date(dump_only=True)
    source = fields.String(dump_only=True)
    watched = fields.Boolean(dump_only=True)
