from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine
from app.infra.redis import check_redis

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict:
    settings = get_settings()
    database_ok = False
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            database_ok = True
    except Exception:
        database_ok = False
    redis_ok = await check_redis()
    status_value = "ok" if database_ok else "degraded"
    return {
        "status": status_value,
        "database": "ok" if database_ok else "unavailable",
        "redis": "ok" if redis_ok else "unavailable",
        "version": settings.app_version,
        "env": settings.app_env,
    }
