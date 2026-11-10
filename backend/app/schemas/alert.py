from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AlertSeverity, AlertSource, AlertStatus


class AlertmanagerAlert(BaseModel):
    status: Literal["firing", "resolved"]
    labels: dict[str, str]
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: datetime
    endsAt: datetime | None = None
    generatorURL: str | None = None
    fingerprint: str


class AlertmanagerWebhook(BaseModel):
    version: str = "4"
    groupKey: str
    truncatedAlerts: int = 0
    status: Literal["firing", "resolved"]
    receiver: str
    groupLabels: dict[str, str] = Field(default_factory=dict)
    commonLabels: dict[str, str] = Field(default_factory=dict)
    commonAnnotations: dict[str, str] = Field(default_factory=dict)
    externalURL: str | None = None
    alerts: list[AlertmanagerAlert]


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fingerprint: str
    source: AlertSource
    rule_name: str
    severity: AlertSeverity
    status: AlertStatus
    service_name: str | None = None
    labels: dict
    annotations: dict
    starts_at: datetime
    ends_at: datetime | None = None
    last_seen_at: datetime
    occurrence_count: int
    incident_id: uuid.UUID | None = None
    created_at: datetime


class WebhookAck(BaseModel):
    accepted: int
    incident_ids: list[uuid.UUID]
    duplicate: bool = False
