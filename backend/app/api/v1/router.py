from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import alerts, audit, auth, health, incidents, services

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(auth.admin_router)
api_router.include_router(alerts.router)
api_router.include_router(incidents.router)
api_router.include_router(services.router)
api_router.include_router(audit.router)
