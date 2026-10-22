from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SyncRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    status: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    details: dict[str, Any]
    error: str | None
