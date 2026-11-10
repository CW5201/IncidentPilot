from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from datetime import UTC, datetime

import httpx
import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import chaos_routes
from app.config import settings
from app.db import OrderRecord, get_session

logger = logging.getLogger(__name__)
# 订单服务接口
router = APIRouter(tags=["orders"])
redis_client = redis.from_url(settings.redis_url, decode_responses=True)


class OrderCreate(BaseModel):
    customer_id: str = Field(min_length=1, max_length=64)
    sku: str = Field(min_length=1, max_length=64)
    quantity: int = Field(default=1, ge=1, le=100)
    amount: float = Field(gt=0, le=100000)


class OrderOut(BaseModel):
    id: str
    customer_id: str
    sku: str
    quantity: int
    amount: float
    status: str
    created_at: datetime


def _chaos_active(scenario: str) -> bool:
    manager = chaos_routes.manager
    return manager is not None and manager.is_active(scenario)


def _error_ratio() -> float:
    manager = chaos_routes.manager
    return manager.error_ratio if manager is not None else 0.0


@router.get("/orders", response_model=list[OrderOut])
async def list_orders(session: AsyncSession = Depends(get_session)) -> list[OrderRecord]:
    result = await session.execute(
        select(OrderRecord).order_by(OrderRecord.created_at.desc()).limit(50)
    )
    return list(result.scalars())


@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(order_id: str, session: AsyncSession = Depends(get_session)) -> OrderRecord:
    cached = await redis_client.get(f"order:{order_id}")
    if cached:
        return OrderOut.model_validate(json.loads(cached))
    order = await session.get(OrderRecord, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return order


@router.post("/orders", response_model=OrderOut, status_code=201)
async def create_order(
    payload: OrderCreate,
    session: AsyncSession = Depends(get_session),
) -> OrderRecord:
    # 场景 4：按比例注入 500
    if _chaos_active("error_burst") and random.random() < _error_ratio():
        logger.error("injected order processing failure")
        raise HTTPException(status_code=500, detail="injected order processing failure")

    try:
        await redis_client.ping()
    except Exception as exc:
        # 场景 2：Redis 不可用时快速失败
        logger.error("redis unavailable", exc_info=exc)
        raise HTTPException(status_code=503, detail="redis unavailable") from exc

    timeout = httpx.Timeout(settings.request_timeout_seconds)
    # 调用库存与支付，HTTPX 自动传播 Trace 上下文
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            inventory_response = await client.post(
                f"{settings.inventory_url}/inventory/reserve",
                json={"sku": payload.sku, "quantity": payload.quantity},
            )
            inventory_response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "inventory rejected reservation",
                extra={"status": exc.response.status_code},
            )
            raise HTTPException(status_code=409, detail="inventory reservation failed") from exc
        except httpx.HTTPError as exc:
            logger.error("inventory call failed", exc_info=exc)
            raise HTTPException(status_code=502, detail="inventory unavailable") from exc

        try:
            payment_response = await client.post(
                f"{settings.payment_url}/payments/authorize",
                json={
                    "order_id": str(uuid.uuid4()),
                    "amount": payload.amount,
                    "customer_id": payload.customer_id,
                },
            )
            payment_response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "payment rejected authorization",
                extra={"status": exc.response.status_code},
            )
            raise HTTPException(status_code=502, detail="payment rejected") from exc
        except httpx.HTTPError as exc:
            logger.error("payment call failed", exc_info=exc)
            raise HTTPException(status_code=504, detail="upstream timeout") from exc

    if _chaos_active("bad_release"):
        # 场景 7：模拟 N+1 查询
        for _ in range(30):
            await session.execute(select(OrderRecord).limit(1))
            await asyncio.sleep(0.02)

    order = OrderRecord(
        id=str(uuid.uuid4()),
        customer_id=payload.customer_id,
        sku=payload.sku,
        quantity=payload.quantity,
        amount=payload.amount,
        status="created",
        created_at=datetime.now(UTC),
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    await redis_client.setex(
        f"order:{order.id}",
        60,
        json.dumps(
            {
                "id": order.id,
                "customer_id": order.customer_id,
                "sku": order.sku,
                "quantity": order.quantity,
                "amount": float(order.amount),
                "status": order.status,
                "created_at": order.created_at.isoformat(),
            }
        ),
    )
    return order
