from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import IncidentStatus
from app.models.incident import Incident, IncidentAlert, IncidentTimeline


class IncidentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, incident_id: uuid.UUID) -> Incident | None:
        stmt = (
            select(Incident)
            .where(Incident.id == incident_id)
            .options(
                selectinload(Incident.timeline),
                selectinload(Incident.agent_runs),
                selectinload(Incident.alerts),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_no(self, incident_no: str) -> Incident | None:
        stmt = select(Incident).where(Incident.incident_no == incident_no)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_aggregation_key(self, key: str) -> Incident | None:
        stmt = select(Incident).where(
            Incident.aggregation_key == key,
            Incident.status.not_in((IncidentStatus.RESOLVED, IncidentStatus.FAILED)),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, incident: Incident) -> Incident:
        self.session.add(incident)
        await self.session.flush()
        return incident

    async def link_alert(self, incident_id: uuid.UUID, alert_id: uuid.UUID) -> None:
        existing = await self.session.get(IncidentAlert, (incident_id, alert_id))
        if existing is None:
            self.session.add(IncidentAlert(incident_id=incident_id, alert_id=alert_id))
            await self.session.flush()

    async def add_timeline(
        self,
        *,
        incident_id: uuid.UUID,
        event_type: str,
        summary: str,
        payload: dict | None = None,
        actor_type=None,
        actor_id: str | None = None,
        event_key: str | None = None,
    ) -> IncidentTimeline | None:
        if event_key:
            existing = await self.session.scalar(
                select(IncidentTimeline).where(IncidentTimeline.event_key == event_key)
            )
            if existing is not None:
                return existing
        from app.models.enums import ActorType

        entry = IncidentTimeline(
            incident_id=incident_id,
            event_type=event_type,
            summary=summary,
            payload=payload or {},
            actor_type=actor_type or ActorType.SYSTEM,
            actor_id=actor_id,
            event_key=event_key,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list(
        self,
        *,
        status: IncidentStatus | None = None,
        service_name: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Incident], int]:
        conditions = []
        if status is not None:
            conditions.append(Incident.status == status)
        if service_name:
            conditions.append(Incident.service_name == service_name)
        count_stmt = select(func.count()).select_from(Incident)
        stmt = select(Incident).order_by(Incident.started_at.desc())
        if conditions:
            count_stmt = count_stmt.where(*conditions)
            stmt = stmt.where(*conditions)
        total = await self.session.scalar(count_stmt)
        result = await self.session.execute(stmt.limit(limit).offset(offset))
        return list(result.scalars().all()), int(total or 0)

    async def save(self, incident: Incident) -> Incident:
        await self.session.flush()
        return incident

    async def count_since(self, since: datetime) -> int:
        stmt = select(func.count()).select_from(Incident).where(Incident.detected_at >= since)
        return int(await self.session.scalar(stmt) or 0)
