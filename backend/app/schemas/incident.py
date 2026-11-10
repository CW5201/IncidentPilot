from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ActorType,
    AgentRunStatus,
    IncidentSeverity,
    IncidentStatus,
)


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_no: str
    title: str
    status: IncidentStatus
    severity: IncidentSeverity
    service_name: str | None = None
    started_at: datetime
    detected_at: datetime
    resolved_at: datetime | None = None
    summary: str | None = None
    root_cause_label: str | None = None
    root_cause_confidence: float | None = None
    version: int
    created_at: datetime


class TimelineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    actor_type: ActorType
    actor_id: str | None = None
    summary: str
    payload: dict
    created_at: datetime


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    thread_id: str
    status: AgentRunStatus
    round: int
    model_name: str | None = None
    total_tokens: int
    error_code: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int | None = None


class IncidentDetail(IncidentOut):
    timeline: list[TimelineOut] = Field(default_factory=list)
    agent_runs: list[AgentRunOut] = Field(default_factory=list)


class IncidentStatusUpdate(BaseModel):
    status: IncidentStatus
    note: str | None = Field(default=None, max_length=500)
    expected_version: int | None = None


class ApprovalDecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    comment: str | None = Field(default=None, max_length=1000)
    expected_version: int | None = None
