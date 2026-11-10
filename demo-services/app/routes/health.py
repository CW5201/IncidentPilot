from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.db import SessionLocal
from app.metrics import REDIS_UP

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> JSONResponse:
    """检查数据库与 Redis 依赖。"""
    checks: dict[str, str] = {}
    healthy = True
    if not settings.is_payment:
        try:
            async with SessionLocal() as session:
                await session.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {exc}"
            healthy = False
    if settings.is_order:
        from app.routes import order

        try:
            await order.redis_client.ping()
            checks["redis"] = "ok"
            REDIS_UP.labels(settings.service_name).set(1)
        except Exception as exc:
            checks["redis"] = f"error: {exc}"
            REDIS_UP.labels(settings.service_name).set(0)
            healthy = False
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "service": settings.service_name,
            "checks": checks,
        },
    )
