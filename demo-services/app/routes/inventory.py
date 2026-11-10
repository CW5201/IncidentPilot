from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import InventoryItem, get_session

# 库存服务接口，重点观察数据库连接池
router = APIRouter(tags=["inventory"])


class ReserveRequest(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    quantity: int = Field(default=1, ge=1, le=100)


class InventoryOut(BaseModel):
    sku: str
    available: int
    updated_at: datetime


@router.get("/inventory/{sku}", response_model=InventoryOut)
async def get_inventory(sku: str, session: AsyncSession = Depends(get_session)) -> InventoryItem:
    item = await session.get(InventoryItem, sku)
    if item is None:
        raise HTTPException(status_code=404, detail="sku not found")
    return item


@router.post("/inventory/reserve", response_model=InventoryOut)
async def reserve(
    payload: ReserveRequest,
    session: AsyncSession = Depends(get_session),
) -> InventoryItem:
    result = await session.execute(
        # 行锁保证并发扣减安全
        select(InventoryItem).where(InventoryItem.sku == payload.sku).with_for_update()
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="sku not found")
    if item.available < payload.quantity:
        raise HTTPException(status_code=409, detail="insufficient inventory")
    item.available -= payload.quantity
    item.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(item)
    return item
