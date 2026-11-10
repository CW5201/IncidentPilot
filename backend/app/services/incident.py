from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound
from app.core.time import utcnow
from app.domain.incident_rules import (
    SEVERITY_MAP,
    aggregation_key,
    assert_transition,
    incident_title,
    next_incident_no,
)
from app.models.alert import Alert
from app.models.enums import ActorType, IncidentStatus
from app.models.incident import Incident
from app.repositories.incident import IncidentRepository
from app.services.outbox import OutboxService


class IncidentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = IncidentRepository(session)
        self.outbox = OutboxService(session)

    async def get(self, incident_id: uuid.UUID) -> Incident:
        incident = await self.repo.get(incident_id)
        if incident is None:
            raise NotFound("Incident not found")
        return incident

    async def list(
        self,
        *,
        status: IncidentStatus | None = None,
        service_name: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Incident], int]:
        return await self.repo.list(
            status=status,
            service_name=service_name,
            limit=limit,
            offset=offset,
        )

    async def _next_number(self) -> str:
        prefix = f"INC-{utcnow():%Y%m%d}-"
        last = await self.session.scalar(
            select(Incident.incident_no)
            .where(Incident.incident_no.like(f"{prefix}%"))
            .order_by(Incident.incident_no.desc())
            .limit(1)
        )
        return next_incident_no(last)

    async def get_or_create_from_alert(
        self,
        alert: Alert,
        *,
        rule_name: str,
        summary: str | None,
    ) -> tuple[Incident, bool]:
        key = aggregation_key(alert.service_name, rule_name)
        existing = await self.repo.get_active_by_aggregation_key(key)
        if existing is not None:
            await self.repo.link_alert(existing.id, alert.id)
            await self.repo.add_timeline(
                incident_id=existing.id,
                event_type="alert_linked",
                summary=f"Alert {rule_name} linked to active incident",
                payload={"alert_id": str(alert.id), "fingerprint": alert.fingerprint},
                actor_type=ActorType.SYSTEM,
                event_key=f"alert:{alert.id}",
            )
            return existing, False

        incident = Incident(
            incident_no=await self._next_number(),
            title=incident_title(rule_name, alert.service_name, summary),
            status=IncidentStatus.DETECTED,
            severity=SEVERITY_MAP[alert.severity],
            primary_service_id=alert.service_id,
            service_name=alert.service_name,
            aggregation_key=key,
            started_at=alert.starts_at,
            detected_at=utcnow(),
        )
        await self.repo.create(incident)
        await self.repo.link_alert(incident.id, alert.id)
        await self.repo.add_timeline(
            incident_id=incident.id,
            event_type="alert_received",
            summary=f"Alert {rule_name} received from {alert.source.value}",
            payload={
                "alert_id": str(alert.id),
                "fingerprint": alert.fingerprint,
                "severity": alert.severity.value,
            },
            actor_type=ActorType.SYSTEM,
            event_key=f"alert:{alert.id}",
        )
        await self.outbox.enqueue(
            topic="incident.created",
            payload={
                "incident_id": str(incident.id),
                "incident_no": incident.incident_no,
                "thread_id": f"incident-{incident.id}",
                "service_name": incident.service_name,
                "severity": incident.severity.value,
                "title": incident.title,
            },
        )
        return incident, True

    async def change_status(
        self,
        incident_id: uuid.UUID,
        target: IncidentStatus,
        *,
        actor_type: ActorType = ActorType.USER,
        actor_id: str | uuid.UUID | None = None,
        note: str | None = None,
        expected_version: int | None = None,
    ) -> Incident:
        incident = await self.get(incident_id)
        assert_transition(incident.status, target)
        previous_status = incident.status
        current_version = incident.version if expected_version is None else expected_version
        values = {
            "status": target,
            "version": Incident.version + 1,
        }
        if target == IncidentStatus.RESOLVED:
            values["resolved_at"] = utcnow()
        result = await self.session.execute(
            update(Incident)
            .where(Incident.id == incident_id, Incident.version == current_version)
            .values(**values)
        )
        if cast(CursorResult, result).rowcount == 0:
            raise Conflict("Incident was modified concurrently; reload and retry")
        await self.session.refresh(incident)
        await self.repo.add_timeline(
            incident_id=incident.id,
            event_type="status_changed",
            summary=f"Status changed to {target.value}" + (f": {note}" if note else ""),
            payload={
                "from": previous_status.value,
                "to": target.value,
                "note": note,
            },
            actor_type=actor_type,
            actor_id=str(actor_id) if actor_id is not None else None,
        )
        return incident
