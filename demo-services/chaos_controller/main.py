from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import docker
import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("chaos-controller")

# 控制器配置
CHAOS_TOKEN = os.getenv("CHAOS_TOKEN", "dev-chaos-token")
CHAOS_ENABLED = os.getenv("CHAOS_ENABLED", "true").lower() == "true"
TOXIPROXY_URL = os.getenv("TOXIPROXY_URL", "http://toxiproxy:8474")
ORDER_URL = os.getenv("ORDER_URL", "http://order-service:8001")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://inventory-service:8003")
TARGET_CONTAINER = os.getenv("TARGET_CONTAINER", "order-service")
DEFAULT_TTL_SECONDS = int(os.getenv("DEFAULT_TTL_SECONDS", "600"))

# toxiproxy 代理：Redis 与支付链路
PROXIES = {
    "redis": ("0.0.0.0:8666", "redis:6379"),
    "payment": ("0.0.0.0:8667", "payment-service:8002"),
}

# 七个故障场景及预期告警
SCENARIOS: dict[str, dict[str, str]] = {
    "db_pool_exhaustion": {
        "target_service": "inventory-service",
        "description": "Hold all inventory database pool connections",
        "expected_alert": "DBPoolExhausted",
    },
    "redis_connection_failure": {
        "target_service": "order-service",
        "description": "Disable the Redis toxiproxy upstream",
        "expected_alert": "RedisDown",
    },
    "upstream_timeout": {
        "target_service": "order-service",
        "description": "Add 3s latency to the payment toxiproxy upstream",
        "expected_alert": "HighLatencyP95",
    },
    "error_burst": {
        "target_service": "order-service",
        "description": "Inject HTTP 500 responses into order creation",
        "expected_alert": "HighErrorRate",
    },
    "cpu_burn": {
        "target_service": "order-service",
        "description": "Burn CPU inside the order service",
        "expected_alert": "HighCPU",
    },
    "instance_unavailable": {
        "target_service": "order-service",
        "description": "Pause the order service container",
        "expected_alert": "InstanceDown",
    },
    "bad_release": {
        "target_service": "order-service",
        "description": "Enable slow N+1 query behavior in order creation",
        "expected_alert": "HighLatencyP95",
    },
}


class StartRequest(BaseModel):
    duration_seconds: int = Field(default=DEFAULT_TTL_SECONDS, ge=5, le=3600)


class ScenarioState(BaseModel):
    name: str
    target_service: str
    started_at: str
    expires_at: str
    details: dict[str, Any] = Field(default_factory=dict)


class Controller:
    """负责启动、停止与自动恢复故障场景。"""

    def __init__(self) -> None:
        self.active: ScenarioState | None = None
        self._auto_stop: asyncio.Task | None = None

    async def ensure_proxies(self) -> None:
        """确保 toxiproxy 代理存在。"""
        async with httpx.AsyncClient(timeout=10) as client:
            for name, (listen, upstream) in PROXIES.items():
                try:
                    response = await client.post(
                        f"{TOXIPROXY_URL}/proxies",
                        json={
                            "name": name,
                            "listen": listen,
                            "upstream": upstream,
                            "enabled": True,
                        },
                    )
                    if response.status_code >= 400 and "already exists" not in response.text:
                        logger.warning(
                            "toxiproxy setup failed name=%s status=%s",
                            name,
                            response.status_code,
                        )
                except httpx.HTTPError as exc:
                    logger.warning("toxiproxy unavailable: %s", exc)

    async def start(self, name: str, duration_seconds: int) -> ScenarioState:
        """启动场景；同一时间只允许一个场景。"""
        if not CHAOS_ENABLED:
            raise HTTPException(status_code=403, detail="chaos is disabled")
        if name not in SCENARIOS:
            raise HTTPException(status_code=404, detail="unknown scenario")
        if self.active is not None:
            await self.stop()

        await self.ensure_proxies()
        details = await self._apply(name, duration_seconds)
        now = datetime.now(UTC)
        state = ScenarioState(
            name=name,
            target_service=SCENARIOS[name]["target_service"],
            started_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=duration_seconds)).isoformat(),
            details=details,
        )
        self.active = state
        self._auto_stop = asyncio.create_task(self._auto_stop_after(duration_seconds))
        logger.warning("scenario started name=%s duration=%s", name, duration_seconds)
        return state

    async def stop(self) -> ScenarioState | None:
        state = self.active
        if state is None:
            return None
        if self._auto_stop is not None and self._auto_stop is not asyncio.current_task():
            self._auto_stop.cancel()
        self._auto_stop = None
        await self._revert(state.name)
        self.active = None
        logger.warning("scenario stopped name=%s", state.name)
        return state

    async def _auto_stop_after(self, duration_seconds: int) -> None:
        await asyncio.sleep(duration_seconds)
        with contextlib.suppress(Exception):
            await self.stop()

    async def _apply(self, name: str, duration_seconds: int) -> dict[str, Any]:
        """根据场景调用目标服务、toxiproxy 或 Docker。"""
        async with httpx.AsyncClient(timeout=15) as client:
            if name == "db_pool_exhaustion":
                await self._service_chaos(
                    client,
                    INVENTORY_URL,
                    name,
                    {"duration_seconds": duration_seconds, "params": {"connections": 15}},
                )
                return {"connections": 15}
            if name == "redis_connection_failure":
                await self._toxiproxy(client, "redis", "disable")
                return {"proxy": "redis"}
            if name == "upstream_timeout":
                await self._toxiproxy(client, "payment", "enable")
                await self._add_latency(client)
                return {"proxy": "payment", "latency_ms": 3000}
            if name == "error_burst":
                await self._service_chaos(
                    client,
                    ORDER_URL,
                    name,
                    {"duration_seconds": duration_seconds, "params": {"ratio": 0.3}},
                )
                return {"ratio": 0.3}
            if name == "cpu_burn":
                await self._service_chaos(
                    client,
                    ORDER_URL,
                    name,
                    {"duration_seconds": min(duration_seconds, 90), "params": {}},
                )
                return {"duration_seconds": min(duration_seconds, 90)}
            if name == "bad_release":
                await self._service_chaos(
                    client,
                    ORDER_URL,
                    name,
                    {"duration_seconds": duration_seconds, "params": {}},
                )
                return {"release": "v2-bad"}
            if name == "instance_unavailable":
                await asyncio.to_thread(self._pause_container, True)
                return {"container": TARGET_CONTAINER, "paused": True}
        raise HTTPException(status_code=500, detail="scenario not implemented")

    async def _revert(self, name: str) -> None:
        """撤销场景，恢复服务与网络。"""
        async with httpx.AsyncClient(timeout=15) as client:
            if name == "db_pool_exhaustion":
                await self._service_chaos(client, INVENTORY_URL, name, None)
            elif name == "redis_connection_failure":
                await self._toxiproxy(client, "redis", "enable")
            elif name == "upstream_timeout":
                await self._delete_latency(client)
            elif name in {"error_burst", "cpu_burn", "bad_release"}:
                await self._service_chaos(client, ORDER_URL, name, None)
            elif name == "instance_unavailable":
                await asyncio.to_thread(self._pause_container, False)

    async def _service_chaos(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        name: str,
        payload: dict[str, Any] | None,
    ) -> None:
        headers = {"X-Chaos-Token": CHAOS_TOKEN}
        try:
            if payload is None:
                response = await client.delete(f"{base_url}/internal/chaos/{name}", headers=headers)
            else:
                response = await client.post(
                    f"{base_url}/internal/chaos/{name}",
                    headers=headers,
                    json=payload,
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "service chaos call failed service=%s scenario=%s error=%s",
                base_url,
                name,
                exc,
            )
            raise HTTPException(
                status_code=502, detail=f"target service rejected chaos: {exc}"
            ) from exc

    async def _toxiproxy(self, client: httpx.AsyncClient, proxy: str, action: str) -> None:
        try:
            response = await client.post(f"{TOXIPROXY_URL}/proxies/{proxy}/{action}")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"toxiproxy action failed: {exc}") from exc

    async def _add_latency(self, client: httpx.AsyncClient) -> None:
        with contextlib.suppress(httpx.HTTPError):
            await client.delete(f"{TOXIPROXY_URL}/proxies/payment/toxics/latency")
        try:
            response = await client.post(
                f"{TOXIPROXY_URL}/proxies/payment/toxics",
                json={
                    "name": "latency",
                    "type": "latency",
                    "stream": "downstream",
                    "attributes": {"latency": 3000, "jitter": 0},
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"toxiproxy latency failed: {exc}") from exc

    async def _delete_latency(self, client: httpx.AsyncClient) -> None:
        with contextlib.suppress(httpx.HTTPError):
            await client.delete(f"{TOXIPROXY_URL}/proxies/payment/toxics/latency")

    def _pause_container(self, paused: bool) -> None:
        try:
            client = docker.from_env()
            container = client.containers.get(TARGET_CONTAINER)
            if paused:
                container.pause()
            else:
                container.unpause()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"docker control failed: {exc}") from exc


controller = Controller()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if CHAOS_ENABLED:
        await controller.ensure_proxies()
    yield
    if controller.active is not None:
        with contextlib.suppress(Exception):
            await controller.stop()


app = FastAPI(title="IncidentPilot Chaos Controller", version="0.1.0", lifespan=lifespan)


def verify_token(x_chaos_token: str | None = Header(default=None)) -> None:
    if not x_chaos_token or x_chaos_token != CHAOS_TOKEN:
        raise HTTPException(status_code=401, detail="invalid chaos token")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "enabled": CHAOS_ENABLED, "active": controller.active}


@app.get("/scenarios", dependencies=[Depends(verify_token)])
async def scenarios() -> dict[str, Any]:
    return {
        "active": controller.active,
        "scenarios": [
            {
                "name": name,
                **metadata,
                "active": controller.active and controller.active.name == name,
            }
            for name, metadata in SCENARIOS.items()
        ],
    }


@app.get("/state", dependencies=[Depends(verify_token)])
async def state() -> dict[str, Any]:
    return {"active": controller.active}


@app.post("/scenarios/{name}/start", dependencies=[Depends(verify_token)])
async def start_scenario(name: str, payload: StartRequest | None = None) -> ScenarioState:
    duration = payload.duration_seconds if payload else DEFAULT_TTL_SECONDS
    return await controller.start(name, duration)


@app.post("/scenarios/{name}/stop", dependencies=[Depends(verify_token)])
async def stop_scenario(name: str) -> dict[str, Any]:
    if controller.active is None or controller.active.name != name:
        return {"stopped": False, "reason": "scenario is not active"}
    state = await controller.stop()
    return {"stopped": True, "scenario": state.name if state else name}
