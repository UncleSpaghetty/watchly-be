# dFlango
from dflango import ModelSchema

# Third-party
from marshmallow import ValidationError, fields, validate, validates

# Models
from app.models.user import User

# Services
from app.services.timeutil import get_zone


class UserSettingsUpdateSchema(ModelSchema):
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
