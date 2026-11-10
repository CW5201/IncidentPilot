from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, request_id, require_roles
from app.core.errors import Conflict
from app.core.pagination import PageParams, page_params
from app.db.session import get_session
from app.models.enums import ActorType, IncidentStatus, UserRole
from app.models.incident import Incident
from app.models.user import User
from app.schemas.incident import (
    ApprovalDecision,
    IncidentDetail,
    IncidentOut,
    IncidentStatusUpdate,
)
from app.services.audit import AuditService
from app.services.incident import IncidentService

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentOut])
async def list_incidents(
    response: Response,
    status_filter: IncidentStatus | None = None,
    service_name: str | None = None,
    params: PageParams = Depends(page_params),
    _: User = Depends(require_roles(UserRole.VIEWER, UserRole.SRE, UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> list[Incident]:
    incidents, total = await IncidentService(session).list(
        status=status_filter,
        service_name=service_name,
        limit=params.page_size,
        offset=params.offset,
    )
    response.headers["X-Total-Count"] = str(total)
    return incidents


@router.get("/{incident_id}", response_model=IncidentDetail)
async def get_incident(
    incident_id: uuid.UUID,
    _: User = Depends(require_roles(UserRole.VIEWER, UserRole.SRE, UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> IncidentDetail:
    incident = await IncidentService(session).get(incident_id)
    return IncidentDetail.model_validate(incident)


@router.patch("/{incident_id}/status", response_model=IncidentOut)
async def update_incident_status(
    incident_id: uuid.UUID,
    payload: IncidentStatusUpdate,
    request: Request,
    actor: User = Depends(require_roles(UserRole.SRE, UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> Incident:
    service = IncidentService(session)
    incident = await service.change_status(
        incident_id,
        payload.status,
        actor_type=ActorType.USER,
        actor_id=actor.id,
        note=payload.note,
        expected_version=payload.expected_version,
    )
    await AuditService(session).record(
        action="incident.status_changed",
        resource_type="incident",
        resource_id=incident.id,
        actor_id=actor.id,
        after={"status": incident.status.value, "note": payload.note},
        ip=client_ip(request),
        request_id=request_id(request),
    )
    await session.commit()
    return incident


@router.post("/{incident_id}/approval", response_model=IncidentOut)
async def decide_approval(
    incident_id: uuid.UUID,
    payload: ApprovalDecision,
    request: Request,
    actor: User = Depends(require_roles(UserRole.SRE, UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> Incident:
    service = IncidentService(session)
    incident = await service.get(incident_id)
    if incident.status != IncidentStatus.AWAITING_APPROVAL:
        raise Conflict("Incident is not awaiting approval")
    target = (
        IncidentStatus.REMEDIATING
        if payload.decision == "APPROVE"
        else IncidentStatus.INVESTIGATING
    )
    incident = await service.change_status(
        incident_id,
        target,
        actor_type=ActorType.USER,
        actor_id=actor.id,
        note=payload.comment,
        expected_version=payload.expected_version,
    )
    await AuditService(session).record(
        action=f"incident.approval_{payload.decision.lower()}",
        resource_type="incident",
        resource_id=incident.id,
        actor_id=actor.id,
        after={"decision": payload.decision, "comment": payload.comment},
        ip=client_ip(request),
        request_id=request_id(request),
    )
    await session.commit()
    return incident
