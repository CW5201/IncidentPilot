from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # 服务名决定启用哪些路由
    service_name: str = os.getenv("SERVICE_NAME", "order-service")
    app_env: str = os.getenv("APP_ENV", "demo")
    # 演示服务共用 incidentpilot 库的 demo schema
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://incidentpilot:incidentpilot@postgres:5432/incidentpilot",
    )
    # 连接池故意设置得较小，便于复现耗尽场景
    database_pool_size: int = _int("DATABASE_POOL_SIZE", 5)
    database_max_overflow: int = _int("DATABASE_MAX_OVERFLOW", 10)
    database_pool_timeout: float = _float("DATABASE_POOL_TIMEOUT", 2.0)
    # Redis 与支付调用都经过 toxiproxy
    redis_url: str = os.getenv("REDIS_URL", "redis://toxiproxy:8666/1")
    payment_url: str = os.getenv("PAYMENT_URL", "http://toxiproxy:8667")
    inventory_url: str = os.getenv("INVENTORY_URL", "http://inventory-service:8003")
    # OTel 与内部故障注入配置
    otel_endpoint: str = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    otel_enabled: bool = os.getenv("OTEL_ENABLED", "true").lower() == "true"
    chaos_token: str = os.getenv("CHAOS_TOKEN", "dev-chaos-token")
    request_timeout_seconds: float = _float("REQUEST_TIMEOUT_SECONDS", 2.0)

    @property
    def is_order(self) -> bool:
        return self.service_name == "order-service"

    @property
    def is_inventory(self) -> bool:
        return self.service_name == "inventory-service"

    @property
    def is_payment(self) -> bool:
        return self.service_name == "payment-service"


settings = Settings()
