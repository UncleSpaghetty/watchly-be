# dFlango
from dflango.schemas import Schema, UtcDateTimeField

# Third-party
from marshmallow import fields


class UserSettingsReadSchema(Schema):
    display_name = fields.String(dump_only=True, allow_none=True)
    timezone = fields.String(dump_only=True)
    locale = fields.String(dump_only=True)
    notifications_enabled = fields.Boolean(dump_only=True)
    notification_local_time = fields.String(dump_only=True)
    notification_quiet_start = fields.String(dump_only=True, allow_none=True)
    notification_quiet_end = fields.String(dump_only=True, allow_none=True)
    notification_lead_days = fields.Integer(dump_only=True)
    notify_releases = fields.Boolean(dump_only=True)
    notify_schedule_changes = fields.Boolean(dump_only=True)
    notify_new_seasons = fields.Boolean(dump_only=True)
    notify_news = fields.Boolean(dump_only=True)
    weekly_digest = fields.Boolean(dump_only=True)
    preferred_services = fields.List(fields.String(), dump_only=True)
    last_successful_sync_at = UtcDateTimeField(dump_only=True, allow_none=True)
    push_available = fields.Boolean(dump_only=True)
    push_subscriptions = fields.Integer(dump_only=True)
