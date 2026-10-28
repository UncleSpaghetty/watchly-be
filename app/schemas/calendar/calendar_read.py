# dFlango
from dflango.schemas import Schema

# Third-party
from marshmallow import fields

# Schemas
from app.schemas.calendar.calendar_item_read import CalendarItemSchema


class CalendarResponseSchema(Schema):
    start = fields.Date(dump_only=True)
    end = fields.Date(dump_only=True)
    timezone = fields.String(dump_only=True)
    items = fields.List(fields.Nested(CalendarItemSchema), dump_only=True)
