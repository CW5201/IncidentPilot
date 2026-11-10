from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import ensure_aware, utcnow
from app.models.alert import Alert
from app.models.enums import AlertSeverity, AlertSource, AlertStatus
from app.models.service import Service
from app.repositories.alert import AlertRepository
from app.repositories.service import ServiceRepository
from app.schemas.alert import AlertmanagerAlert, AlertmanagerWebhook, WebhookAck
from app.services.incident import IncidentService


def _fingerprint(alert: AlertmanagerAlert) -> str:
    if alert.fingerprint:
        return alert.fingerprint[:64]
    raw = json.dumps(alert.labels, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def _severity(value: str | None) -> AlertSeverity:
    normalized = (value or "warning").upper()
    try:
        return AlertSeverity(normalized)
    except ValueError:
        return AlertSeverity.WARNING


class AlertService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.alerts = AlertRepository(session)
        self.services = ServiceRepository(session)
        self.incidents = IncidentService(session)

    async def _resolve_service(
        self,
        service_name: str | None,
        namespace: str | None,
    ) -> Service | None:
        if not service_name:
            return None
        service = await self.services.get_by_name(service_name)
        if service is None:
            service = Service(
                name=service_name[:120],
                display_name=service_name[:200],
                namespace=(namespace or "demo")[:120],
            )
            await self.services.create(service)
        return service

    async def ingest(self, webhook: AlertmanagerWebhook) -> WebhookAck:
        accepted = 0
        incident_ids: set[uuid.UUID] = set()

        for item in webhook.alerts:
            labels = {**webhook.commonLabels, **item.labels}
            annotations = {**webhook.commonAnnotations, **item.annotations}
            starts_at = ensure_aware(item.startsAt)
            ends_at = ensure_aware(item.endsAt) if item.endsAt else None
            status = AlertStatus.FIRING if item.status == "firing" else AlertStatus.RESOLVED
            fingerprint = _fingerprint(item)
            service_name = labels.get("service") or labels.get("app") or labels.get("job")
            service = await self._resolve_service(service_name, labels.get("namespace"))
            severity = _severity(labels.get("severity"))

            alert = await self.alerts.get_by_fingerprint(fingerprint, starts_at)
            if alert is None:
                alert = Alert(
                    fingerprint=fingerprint,
                    source=AlertSource.ALERTMANAGER,
                    rule_name=(labels.get("alertname") or "unknown")[:255],
                    severity=severity,
                    status=status,
                    service_id=service.id if service else None,
                    service_name=service_name[:120] if service_name else None,
                    labels=labels,
                    annotations=annotations,
                    raw_payload=item.model_dump(mode="json"),
                    starts_at=starts_at,
                    ends_at=ends_at,
                    last_seen_at=utcnow(),
                    occurrence_count=1,
                )
                await self.alerts.create(alert)
                accepted += 1
            else:
                alert.status = status
                alert.last_seen_at = utcnow()
                alert.ends_at = ends_at
                alert.occurrence_count += 1
                alert.labels = labels
                alert.annotations = annotations

            if status == AlertStatus.FIRING:
                incident, _ = await self.incidents.get_or_create_from_alert(
                    alert,
                    rule_name=alert.rule_name,
                    summary=annotations.get("summary") or annotations.get("description"),
                )
                alert.incident_id = incident.id
                incident_ids.add(incident.id)
            elif alert.incident_id is not None:
                incident_ids.add(alert.incident_id)

        return WebhookAck(
            accepted=accepted,
            incident_ids=sorted(incident_ids, key=str),
            duplicate=accepted == 0,
        )
