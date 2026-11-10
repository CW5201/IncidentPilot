from __future__ import annotations

from prometheus_client import Gauge

# 数据库连接池指标
DB_POOL_CHECKED_OUT = Gauge(
    "sqlalchemy_pool_checked_out",
    "Number of SQLAlchemy pool connections currently checked out",
    ["service"],
)
DB_POOL_SIZE = Gauge(
    "sqlalchemy_pool_size",
    "Configured SQLAlchemy pool size",
    ["service"],
)
REDIS_UP = Gauge(
    "redis_up",
    "Redis availability from the service perspective",
    ["service"],
)
# 故障注入状态指标
CHAOS_ACTIVE = Gauge(
    "chaos_active",
    "Whether a chaos scenario is currently active",
    ["service", "scenario"],
)
