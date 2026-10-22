from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from app.services.timeutil import get_zone

HHMM = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class UserSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timezone: str
    locale: str
    notifications_enabled: bool
    notification_local_time: str
    last_successful_sync_at: datetime | None
    push_available: bool = False
    push_subscriptions: int = 0


class UserSettingsUpdate(BaseModel):
    timezone: str | None = None
    locale: str | None = None
    notifications_enabled: bool | None = None
    notification_local_time: HHMM | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is not None and get_zone(value).key != value:
            raise ValueError("Fuso orario sconosciuto")
        return value
