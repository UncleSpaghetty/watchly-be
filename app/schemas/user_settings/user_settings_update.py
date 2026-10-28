# dFlango
from dflango import ModelSchema

# Third-party
from marshmallow import ValidationError, fields, validate, validates

# Models
from app.models.user import User

# Services
from app.services.timeutil import get_zone


class UserSettingsUpdateSchema(ModelSchema):
    display_name = fields.String(allow_none=True, validate=validate.Length(max=100))
    timezone = fields.String(allow_none=True)
    locale = fields.String(allow_none=True)
    notifications_enabled = fields.Boolean(allow_none=True)
    notification_local_time = fields.String(
        allow_none=True,
        validate=validate.Regexp(r"^([01]\d|2[0-3]):[0-5]\d$"),
    )
    notification_quiet_start = fields.String(
        allow_none=True,
        validate=validate.Regexp(r"^([01]\d|2[0-3]):[0-5]\d$"),
    )
    notification_quiet_end = fields.String(
        allow_none=True,
        validate=validate.Regexp(r"^([01]\d|2[0-3]):[0-5]\d$"),
    )
    notification_lead_days = fields.Integer(validate=validate.OneOf([0, 1, 3, 7]))
    notify_releases = fields.Boolean()
    notify_schedule_changes = fields.Boolean()
    notify_new_seasons = fields.Boolean()
    notify_news = fields.Boolean()
    weekly_digest = fields.Boolean()
    preferred_services = fields.List(
        fields.String(validate=validate.Length(min=1, max=100)),
        validate=validate.Length(max=20),
    )

    class Meta:
        model = User

    @validates("timezone")
    def valid_timezone(self, value: str | None, **kwargs: object) -> None:
        if value is not None and get_zone(value).key != value:
            raise ValidationError("Fuso orario sconosciuto")
