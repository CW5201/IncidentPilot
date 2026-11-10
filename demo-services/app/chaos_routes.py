from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.chaos import SCENARIOS, ChaosManager
from app.config import settings

logger = logging.getLogger(__name__)
# 仅 chaos-controller 可调用的内部故障注入接口
router = APIRouter(tags=["chaos"])
manager: ChaosManager | None = None


def configure(chaos_manager: ChaosManager) -> None:
    global manager
    manager = chaos_manager


def verify_chaos_token(x_chaos_token: str | None = Header(default=None)) -> None:
    """校验内部 Token，避免故障注入接口被外部调用。"""
    if not x_chaos_token or not hmac.compare_digest(x_chaos_token, settings.chaos_token):
        raise HTTPException(status_code=401, detail="invalid chaos token")


class ChaosRequest(BaseModel):
    duration_seconds: int = Field(default=600, ge=1, le=3600)
    params: dict[str, Any] = Field(default_factory=dict)


@router.get("/internal/chaos")
async def chaos_state(_: None = Depends(verify_chaos_token)) -> dict[str, Any]:
    assert manager is not None
    active = [scenario for scenario in SCENARIOS if manager.is_active(scenario)]
    return {"service": settings.service_name, "active": active}


@router.post("/internal/chaos/{scenario}")
async def start_chaos(
    scenario: str,
    payload: ChaosRequest,
    _: None = Depends(verify_chaos_token),
) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise HTTPException(status_code=404, detail="unknown scenario")
    assert manager is not None
    await manager.start(scenario, payload.duration_seconds, payload.params)
    return {"service": settings.service_name, "scenario": scenario, "active": True}


@router.delete("/internal/chaos/{scenario}")
async def stop_chaos(
    scenario: str,
    _: None = Depends(verify_chaos_token),
) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise HTTPException(status_code=404, detail="unknown scenario")
    assert manager is not None
    await manager.stop(scenario)
    return {"service": settings.service_name, "scenario": scenario, "active": False}
