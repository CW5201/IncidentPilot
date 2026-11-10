from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ActorType


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_type: ActorType
    actor_id: str | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    before: dict | None = None
    after: dict | None = None
    ip: str | None = None
    request_id: str | None = None
    created_at: datetime
