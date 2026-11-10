from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from sqlalchemy import text

from app.metrics import CHAOS_ACTIVE

logger = logging.getLogger(__name__)

SCENARIOS = (
    "db_pool_exhaustion",
    "redis_connection_failure",
    "upstream_timeout",
    "error_burst",
    "cpu_burn",
    "instance_unavailable",
    "bad_release",
)


class ChaosManager:
    """管理单个服务内的故障注入状态与自动恢复。"""

    def __init__(self, service_name: str, session_factory) -> None:
        self.service_name = service_name
        self.session_factory = session_factory
        self.error_ratio = 0.0
        self.bad_release = False
        self._expires_at: dict[str, float] = {}
        self._tasks: set[asyncio.Task] = set()
        self._threads: list[threading.Thread] = []
        self._stop_event = threading.Event()
        for scenario in SCENARIOS:
            CHAOS_ACTIVE.labels(self.service_name, scenario).set(0)

    def is_active(self, scenario: str) -> bool:
        expires_at = self._expires_at.get(scenario)
        if expires_at is None:
            return False
        if time.monotonic() >= expires_at:
            self._expires_at.pop(scenario, None)
            CHAOS_ACTIVE.labels(self.service_name, scenario).set(0)
            return False
        return True

    async def start(self, scenario: str, duration_seconds: int, params: dict[str, Any]) -> None:
        """启动场景，并注册 TTL 自动停止。"""
        await self.stop(scenario)
        duration = max(1, min(int(duration_seconds), 3600))
        self._expires_at[scenario] = time.monotonic() + duration
        CHAOS_ACTIVE.labels(self.service_name, scenario).set(1)

        if scenario == "db_pool_exhaustion":
            await self._start_db_pool_hold(duration, int(params.get("connections", 15)))
        elif scenario == "error_burst":
            self.error_ratio = float(params.get("ratio", 0.3))
        elif scenario == "cpu_burn":
            self._start_cpu_burn(duration)
        elif scenario == "bad_release":
            self.bad_release = True

        task = asyncio.create_task(self._auto_stop(scenario, duration))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        logger.warning("chaos started", extra={"scenario": scenario, "duration": duration})

    async def stop(self, scenario: str) -> None:
        self._expires_at.pop(scenario, None)
        CHAOS_ACTIVE.labels(self.service_name, scenario).set(0)
        if scenario == "error_burst":
            self.error_ratio = 0.0
        if scenario == "bad_release":
            self.bad_release = False
        if scenario == "db_pool_exhaustion":
            await self._cancel_tasks()
        if scenario == "cpu_burn":
            self._stop_event.set()
            self._threads.clear()
        logger.info("chaos stopped", extra={"scenario": scenario})

    async def _auto_stop(self, scenario: str, duration: int) -> None:
        await asyncio.sleep(duration)
        if self.is_active(scenario):
            await self.stop(scenario)

    async def _start_db_pool_hold(self, duration: int, connections: int) -> None:
        """占满连接池，模拟慢查询/长事务。"""
        for _ in range(connections):
            task = asyncio.create_task(self._hold_connection(duration + 5))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _hold_connection(self, seconds: int) -> None:
        try:
            async with self.session_factory() as session:
                await session.execute(text("SELECT pg_sleep(:seconds)"), {"seconds": seconds})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("db hold connection ended", extra={"error": str(exc)})

    async def _cancel_tasks(self) -> None:
        current = asyncio.current_task()
        for task in list(self._tasks):
            if task is not current:
                task.cancel()
        await asyncio.sleep(0)

    def _start_cpu_burn(self, duration: int) -> None:
        """启动后台线程消耗 CPU。"""
        self._stop_event.clear()
        deadline = time.monotonic() + duration

        def burn() -> None:
            while not self._stop_event.is_set() and time.monotonic() < deadline:
                _ = sum(index * index for index in range(20000))

        thread = threading.Thread(target=burn, name="chaos-cpu-burn", daemon=True)
        thread.start()
        self._threads.append(thread)


def build_manager(service_name: str, session_factory) -> ChaosManager:
    return ChaosManager(service_name, session_factory)
