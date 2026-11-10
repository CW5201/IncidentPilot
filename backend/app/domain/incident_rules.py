from __future__ import annotations

from datetime import UTC, datetime

from app.core.errors import Conflict
from app.models.enums import AlertSeverity, IncidentSeverity, IncidentStatus

SEVERITY_MAP: dict[AlertSeverity, IncidentSeverity] = {
    AlertSeverity.CRITICAL: IncidentSeverity.SEV1,
    AlertSeverity.WARNING: IncidentSeverity.SEV2,
    AlertSeverity.INFO: IncidentSeverity.SEV3,
}

ALLOWED_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.DETECTED: {IncidentStatus.INVESTIGATING, IncidentStatus.FAILED},
    IncidentStatus.INVESTIGATING: {
        IncidentStatus.AWAITING_APPROVAL,
        IncidentStatus.RESOLVED,
        IncidentStatus.FAILED,
    },
    IncidentStatus.AWAITING_APPROVAL: {
        IncidentStatus.REMEDIATING,
        IncidentStatus.INVESTIGATING,
        IncidentStatus.FAILED,
    },
    IncidentStatus.REMEDIATING: {IncidentStatus.VERIFYING, IncidentStatus.FAILED},
    IncidentStatus.VERIFYING: {
        IncidentStatus.RESOLVED,
        IncidentStatus.INVESTIGATING,
        IncidentStatus.FAILED,
    },
    IncidentStatus.RESOLVED: set(),
    IncidentStatus.FAILED: {IncidentStatus.INVESTIGATING},
}


def aggregation_key(service_name: str | None, rule_name: str) -> str:
    return f"{(service_name or 'unknown').lower()}:{rule_name.lower()}"


def incident_title(rule_name: str, service_name: str | None, summary: str | None) -> str:
    if summary:
        return summary[:255]
    return f"{rule_name} on {service_name or 'unknown service'}"[:255]


def assert_transition(current: IncidentStatus, target: IncidentStatus) -> None:
    if current == target:
        return
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise Conflict(f"Illegal incident transition: {current} -> {target}")


def next_incident_no(last_incident_no: str | None, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    prefix = f"INC-{now:%Y%m%d}-"
    sequence = 1
    if last_incident_no and last_incident_no.startswith(prefix):
        try:
            sequence = int(last_incident_no.rsplit("-", 1)[-1]) + 1
        except ValueError:
            sequence = 1
    return f"{prefix}{sequence:04d}"
