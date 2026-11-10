from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app import chaos_routes
from app.chaos import build_manager
from app.config import settings
from app.db import SessionLocal, dispose_db, engine, init_db
from app.logging import setup_logging
from app.metrics import DB_POOL_CHECKED_OUT, DB_POOL_SIZE, REDIS_UP
from app.otel import setup_tracing
from app.routes import health

logger = logging.getLogger(__name__)


async def _pool_metrics_loop() -> None:
    """周期刷新数据库连接池指标。"""
    while True:
        pool = engine.pool
        DB_POOL_CHECKED_OUT.labels(settings.service_name).set(pool.checkedout())
        DB_POOL_SIZE.labels(settings.service_name).set(pool.size())
        await asyncio.sleep(5)


async def _redis_metrics_loop(redis_client) -> None:
    """周期检查 Redis 可用性。"""
    while True:
        try:
            await redis_client.ping()
            REDIS_UP.labels(settings.service_name).set(1)
        except Exception:
            REDIS_UP.labels(settings.service_name).set(0)
        await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """初始化数据库、后台指标任务与 OTel。"""
    setup_logging(settings.service_name)
    tasks: list[asyncio.Task] = []
    if not settings.is_payment:
        await init_db()
        tasks.append(asyncio.create_task(_pool_metrics_loop()))
    if settings.is_order:
        from app.routes import order

        tasks.append(asyncio.create_task(_redis_metrics_loop(order.redis_client)))
    logger.info("service started", extra={"service": settings.service_name})
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if settings.is_order:
            from app.routes import order

            await order.redis_client.aclose()
        if not settings.is_payment:
            await dispose_db()
        logger.info("service stopped", extra={"service": settings.service_name})


app = FastAPI(
    title=f"IncidentPilot Demo {settings.service_name}",
    version="0.1.0",
    lifespan=lifespan,
)

chaos_routes.configure(build_manager(settings.service_name, SessionLocal))
app.include_router(health.router)
app.include_router(chaos_routes.router)

# 按服务类型挂载业务路由
if settings.is_order:
    from app.routes import order

    app.include_router(order.router)
elif settings.is_inventory:
    from app.routes import inventory

    app.include_router(inventory.router)
elif settings.is_payment:
    from app.routes import payment

    app.include_router(payment.router)

# Prometheus 指标与 OTel Trace
Instrumentator(excluded_handlers=["/metrics", "/health"]).instrument(app).expose(
    app, endpoint="/metrics", include_in_schema=False
)
setup_tracing(app, engine=None if settings.is_payment else engine)
