from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=200)
    auth: str = Field(min_length=1, max_length=100)


class PushSubscriptionCreate(BaseModel):
    endpoint: HttpUrl
    keys: PushKeys


class PushSubscriptionDelete(BaseModel):
    endpoint: HttpUrl


class PushSubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    last_success_at: datetime | None


class VapidKeyRead(BaseModel):
    public_key: str | None
