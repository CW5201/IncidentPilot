from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

# 模拟支付网关，延迟由 toxiproxy 注入
router = APIRouter(tags=["payments"])


class PaymentRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=64)
    amount: float = Field(gt=0, le=100000)
    customer_id: str = Field(min_length=1, max_length=64)


class PaymentResponse(BaseModel):
    payment_id: str
    order_id: str
    status: str


@router.post("/payments/authorize", response_model=PaymentResponse)
async def authorize(payload: PaymentRequest) -> PaymentResponse:
    return PaymentResponse(
        payment_id=str(uuid.uuid4()),
        order_id=payload.order_id,
        status="authorized",
    )
