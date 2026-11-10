from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ServiceTier


class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*$")
    display_name: str = Field(min_length=1, max_length=200)
    namespace: str = Field(default="demo", max_length=120)
    tier: ServiceTier = ServiceTier.STANDARD
    repo_url: str | None = Field(default=None, max_length=500)
    owner_team: str | None = Field(default=None, max_length=120)
    slo: dict = Field(default_factory=dict)
    labels: dict = Field(default_factory=dict)


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    display_name: str
    namespace: str
    tier: ServiceTier
    repo_url: str | None = None
    owner_team: str | None = None
    slo: dict
    labels: dict
    created_at: datetime
