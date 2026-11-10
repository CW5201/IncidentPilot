from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import login


async def test_login_me_and_refresh_rotation(client: AsyncClient, seeded_users):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "sre@example.com", "password": "SrePass123456!"},
    )
    assert response.status_code == 200
    tokens = response.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] > 0

    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["role"] == "SRE"

    rotated = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert rotated.status_code == 200
    new_tokens = rotated.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    reused = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert reused.status_code == 401


async def test_login_rejects_wrong_password(client: AsyncClient, seeded_users):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "sre@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401


async def test_viewer_cannot_change_incident_status(client: AsyncClient, seeded_users):
    viewer_token = await login(client, "viewer@example.com", "ViewerPass1234!")
    sre_token = await login(client, "sre@example.com", "SrePass123456!")

    ack = await client.post(
        "/api/v1/webhooks/alertmanager",
        json={
            "version": "4",
            "groupKey": "g",
            "status": "firing",
            "receiver": "incidentpilot",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "HighLatency",
                        "severity": "warning",
                        "service": "checkout-service",
                    },
                    "annotations": {"summary": "High latency"},
                    "startsAt": "2026-11-10T05:00:00Z",
                    "fingerprint": "fp-rbac",
                }
            ],
        },
    )
    assert ack.status_code == 200
    incident_id = ack.json()["incident_ids"][0]

    forbidden = await client.patch(
        f"/api/v1/incidents/{incident_id}/status",
        json={"status": "INVESTIGATING"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert forbidden.status_code == 403

    allowed = await client.patch(
        f"/api/v1/incidents/{incident_id}/status",
        json={"status": "INVESTIGATING"},
        headers={"Authorization": f"Bearer {sre_token}"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "INVESTIGATING"
