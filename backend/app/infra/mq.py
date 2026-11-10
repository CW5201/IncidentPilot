from __future__ import annotations

import json
from typing import Any

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractQueue,
    AbstractRobustConnection,
)

from app.core.config import get_settings


async def connect_robust() -> AbstractRobustConnection:
    settings = get_settings()
    return await aio_pika.connect_robust(settings.rabbitmq_url)


async def declare_topology(
    channel: AbstractChannel,
) -> tuple[AbstractExchange, AbstractQueue, AbstractQueue]:
    settings = get_settings()
    exchange = await channel.declare_exchange(
        settings.rabbitmq_exchange,
        ExchangeType.TOPIC,
        durable=True,
    )
    dlq = await channel.declare_queue(settings.rabbitmq_dlq, durable=True)
    queue = await channel.declare_queue(
        settings.rabbitmq_investigation_queue,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": settings.rabbitmq_dlq,
        },
    )
    await queue.bind(exchange, routing_key="incident.created")
    return exchange, queue, dlq


async def publish_json(
    exchange: AbstractExchange,
    *,
    routing_key: str,
    payload: dict[str, Any],
    message_id: str,
    headers: dict[str, Any] | None = None,
) -> None:
    message = Message(
        body=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
        content_type="application/json",
        delivery_mode=DeliveryMode.PERSISTENT,
        message_id=message_id,
        headers=headers or {},
    )
    await exchange.publish(message, routing_key=routing_key)
