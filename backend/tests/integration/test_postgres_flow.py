from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.incident import Incident
from app.schemas.alert import AlertmanagerWebhook
from app.services.alert import AlertService

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is not set"),
]


async def test_alert_flow_against_postgres() -> None:
    assert POSTGRES_URL
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fingerprint = f"integration-{uuid.uuid4().hex}"
    service_name = f"integration-service-{uuid.uuid4().hex[:8]}"
    try:
        async with factory() as session:
            payload = AlertmanagerWebhook.model_validate(
                {
                    "version": "4",
                    "groupKey": "integration",
                    "status": "firing",
                    "receiver": "incidentpilot",
                    "commonLabels": {
                        "alertname": "DbPoolExhausted",
                        "severity": "critical",
                        "service": service_name,
                    },
                    "alerts": [
                        {
                            "status": "firing",
                            "labels": {
                                "alertname": "DbPoolExhausted",
                                "severity": "critical",
                                "service": service_name,
                            },
                            "annotations": {"summary": "Integration DB pool exhaustion"},
                            "startsAt": "2026-11-10T06:00:00Z",
                            "fingerprint": fingerprint,
                        }
                    ],
                }
            )
            ack = await AlertService(session).ingest(payload)
            assert ack.accepted == 1
            incident = await session.get(Incident, ack.incident_ids[0])
            assert incident is not None
            assert incident.status.value == "DETECTED"
            assert incident.severity.value == "SEV1"
            assert incident.incident_no.startswith("INC-")
            await session.rollback()
    finally:
        await engine.dispose()
