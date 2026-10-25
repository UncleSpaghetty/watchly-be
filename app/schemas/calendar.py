from dflango.schemas import Schema
from marshmallow import fields

from app.schemas.episode import AvailabilityRead
from app.schemas.series import SeriesSummary


class CalendarItem(Schema):
    episode_id = fields.UUID(dump_only=True)
    series = fields.Nested(SeriesSummary, dump_only=True)
    season_number = fields.Integer(dump_only=True, allow_none=True)
    episode_number = fields.Integer(dump_only=True, allow_none=True)
    title = fields.String(dump_only=True, allow_none=True)
    local_date = fields.Date(dump_only=True)
    date_kind = fields.String(dump_only=True)
    italy = fields.Nested(AvailabilityRead, dump_only=True)
    watched = fields.Boolean(dump_only=True)


class CalendarResponse(Schema):
    start = fields.Date(dump_only=True)
    end = fields.Date(dump_only=True)
    timezone = fields.String(dump_only=True)
    items = fields.List(fields.Nested(CalendarItem), dump_only=True)
