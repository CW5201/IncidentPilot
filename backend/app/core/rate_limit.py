from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import ServiceUnavailable, TooManyRequests
from app.infra.redis import get_redis

logger = logging.getLogger(__name__)


async def _incr_with_ttl(key: str, ttl_seconds: int) -> int:
    redis = get_redis()
    async with redis.pipeline(transaction=True) as pipe:
        pipe.incr(key, 1)
        pipe.expire(key, ttl_seconds)
        result = await pipe.execute()
    return int(result[0])


async def enforce_login_rate_limit(request: Request) -> None:
    settings = get_settings()
    if not settings.rate_limit_enabled or settings.is_test:
        return
    client = request.client.host if request.client else "unknown"
    bucket = datetime.now(UTC).strftime("%Y%m%d%H%M")
    key = f"rl:login:{client}:{bucket}"
    try:
        count = await _incr_with_ttl(key, 90)
    except Exception as exc:
        logger.warning("login rate limiter unavailable: %s", exc)
        if settings.is_production:
            raise ServiceUnavailable("Rate limiter unavailable") from exc
        return
    if count > settings.login_rate_limit_per_minute:
        raise TooManyRequests("Too many login attempts, retry later")


async def enforce_webhook_rate_limit(request: Request) -> None:
    settings = get_settings()
    if not settings.rate_limit_enabled or settings.is_test:
        return
    bucket = int(datetime.now(UTC).timestamp())
    key = f"rl:webhook:{bucket}"
    try:
        count = await _incr_with_ttl(key, 2)
    except Exception as exc:
        logger.warning("webhook rate limiter unavailable: %s", exc)
        if settings.is_production:
            raise ServiceUnavailable("Rate limiter unavailable") from exc
        return
    if count > settings.webhook_rate_limit_per_second:
        raise TooManyRequests("Webhook rate limit exceeded")
