from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_incidentpilot.db"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["WEBHOOK_TOKEN"] = "test-token"

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import engine, session_scope  # noqa: E402
from app.main import app  # noqa: E402
from app.models.enums import ServiceTier, UserRole  # noqa: E402
from app.models.service import Service  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def reset_database():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest_asyncio.fixture
async def seeded_users():
    async with session_scope() as session:
        admin = User(
            email="admin@example.com",
            hashed_password=hash_password("AdminPass12345!"),
            full_name="Admin",
            role=UserRole.ADMIN,
        )
        sre = User(
            email="sre@example.com",
            hashed_password=hash_password("SrePass123456!"),
            full_name="SRE",
            role=UserRole.SRE,
        )
        viewer = User(
            email="viewer@example.com",
            hashed_password=hash_password("ViewerPass1234!"),
            full_name="Viewer",
            role=UserRole.VIEWER,
        )
        session.add_all([admin, sre, viewer])
        session.add(
            Service(
                name="checkout-service",
                display_name="Checkout Service",
                namespace="demo",
                tier=ServiceTier.CORE,
            )
        )
    return {"admin": admin, "sre": sre, "viewer": viewer}


async def login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def webhook_payload(
    *,
    status: str = "firing",
    starts_at: str = "2026-11-10T05:00:00Z",
    fingerprint: str = "fp-checkout-db-pool",
) -> dict:
    return {
        "version": "4",
        "groupKey": "{}:{alertname=\"DbPoolExhausted\"}",
        "status": status,
        "receiver": "incidentpilot",
        "groupLabels": {"alertname": "DbPoolExhausted"},
        "commonLabels": {
            "alertname": "DbPoolExhausted",
            "severity": "critical",
            "service": "checkout-service",
            "namespace": "demo",
        },
        "commonAnnotations": {"summary": "Checkout DB connection pool exhausted"},
        "alerts": [
            {
                "status": status,
                "labels": {
                    "alertname": "DbPoolExhausted",
                    "severity": "critical",
                    "service": "checkout-service",
                },
                "annotations": {"summary": "Checkout DB connection pool exhausted"},
                "startsAt": starts_at,
                "endsAt": "0001-01-01T00:00:00Z" if status == "resolved" else None,
                "fingerprint": fingerprint,
            }
        ],
    }
