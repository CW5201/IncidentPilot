from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import login, webhook_payload


async def test_webhook_creates_incident_with_timeline(client: AsyncClient, seeded_users):
    response = await client.post("/api/v1/webhooks/alertmanager", json=webhook_payload())
    assert response.status_code == 200, response.text
    ack = response.json()
    assert ack["accepted"] == 1
    assert len(ack["incident_ids"]) == 1

    token = await login(client, "sre@example.com", "SrePass123456!")
    incident = await client.get(
        f"/api/v1/incidents/{ack['incident_ids'][0]}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert incident.status_code == 200
    body = incident.json()
    assert body["status"] == "DETECTED"
    assert body["severity"] == "SEV1"
    assert body["service_name"] == "checkout-service"
    assert body["incident_no"].startswith("INC-")
    assert body["timeline"][0]["event_type"] == "alert_received"


async def test_duplicate_webhook_does_not_create_second_incident(
    client: AsyncClient, seeded_users
):
    first = await client.post("/api/v1/webhooks/alertmanager", json=webhook_payload())
    second = await client.post("/api/v1/webhooks/alertmanager", json=webhook_payload())
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["accepted"] == 0
    assert second.json()["duplicate"] is True
    assert first.json()["incident_ids"] == second.json()["incident_ids"]


async def test_resolved_alert_updates_alert_status(client: AsyncClient, seeded_users):
    await client.post("/api/v1/webhooks/alertmanager", json=webhook_payload())
    resolved = await client.post(
        "/api/v1/webhooks/alertmanager",
        json=webhook_payload(status="resolved"),
    )
    assert resolved.status_code == 200
    assert resolved.json()["accepted"] == 0

    token = await login(client, "sre@example.com", "SrePass123456!")
    alerts = await client.get(
        "/api/v1/alerts?status=RESOLVED",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert alerts.status_code == 200
    assert len(alerts.json()) == 1
    assert alerts.json()[0]["occurrence_count"] == 2


async def test_status_update_rejects_stale_version(client: AsyncClient, seeded_users):
    ack = await client.post("/api/v1/webhooks/alertmanager", json=webhook_payload())
    incident_id = ack.json()["incident_ids"][0]
    token = await login(client, "sre@example.com", "SrePass123456!")

    first = await client.patch(
        f"/api/v1/incidents/{incident_id}/status",
        json={"status": "INVESTIGATING", "expected_version": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200
    assert first.json()["version"] == 2

    stale = await client.patch(
        f"/api/v1/incidents/{incident_id}/status",
        json={"status": "FAILED", "expected_version": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert stale.status_code == 409


async def test_illegal_transition_is_rejected(client: AsyncClient, seeded_users):
    ack = await client.post("/api/v1/webhooks/alertmanager", json=webhook_payload())
    incident_id = ack.json()["incident_ids"][0]
    token = await login(client, "sre@example.com", "SrePass123456!")

    response = await client.patch(
        f"/api/v1/incidents/{incident_id}/status",
        json={"status": "RESOLVED"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409


async def test_health_endpoints(client: AsyncClient):
    live = await client.get("/api/v1/health/live")
    assert live.status_code == 200
    ready = await client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"
