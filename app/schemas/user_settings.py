from dflango import ModelSchema
from dflango.schemas import Schema, UtcDateTimeField
from marshmallow import ValidationError, fields, validate, validates

from app.models.user import User
from app.services.timeutil import get_zone


class UserSettingsRead(Schema):
    timezone = fields.String(dump_only=True)
    locale = fields.String(dump_only=True)
    notifications_enabled = fields.Boolean(dump_only=True)
    notification_local_time = fields.String(dump_only=True)
    last_successful_sync_at = UtcDateTimeField(dump_only=True, allow_none=True)
    push_available = fields.Boolean(dump_only=True)
    push_subscriptions = fields.Integer(dump_only=True)


class UserSettingsUpdate(ModelSchema):
    timezone = fields.String(allow_none=True)
    locale = fields.String(allow_none=True)
    notifications_enabled = fields.Boolean(allow_none=True)
    notification_local_time = fields.String(
        allow_none=True,
        validate=validate.Regexp(r"^([01]\d|2[0-3]):[0-5]\d$"),
    )

    class Meta:
        model = User

    @validates("timezone")
    def valid_timezone(self, value: str | None, **kwargs: object) -> None:
        if value is not None and get_zone(value).key != value:
            raise ValidationError("Fuso orario sconosciuto")
