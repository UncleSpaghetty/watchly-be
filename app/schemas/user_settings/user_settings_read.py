# dFlango
from dflango.schemas import Schema, UtcDateTimeField

# Third-party
from marshmallow import fields


class UserSettingsReadSchema(Schema):
    timezone = fields.String(dump_only=True)
    locale = fields.String(dump_only=True)
    notifications_enabled = fields.Boolean(dump_only=True)
    notification_local_time = fields.String(dump_only=True)
    last_successful_sync_at = UtcDateTimeField(dump_only=True, allow_none=True)
    push_available = fields.Boolean(dump_only=True)
    push_subscriptions = fields.Integer(dump_only=True)
