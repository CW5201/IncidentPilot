from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from app.core.time import utcnow
from app.db.session import session_scope
from app.infra.mq import connect_robust, declare_topology, publish_json
from app.models.enums import OutboxStatus
from app.repositories.outbox import OutboxRepository

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
BATCH_SIZE = 50


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(2 ** attempts, 60))


async def run_outbox_publisher(
    *,
    stop_event: asyncio.Event | None = None,
    poll_interval: float = 1.0,
) -> None:
    connection = await connect_robust()
    channel = await connection.channel(publisher_confirms=True)
    exchange, _queue, _dlq = await declare_topology(channel)
    logger.info("outbox publisher connected")
    try:
        while stop_event is None or not stop_event.is_set():
            processed = 0
            try:
                async with session_scope() as session:
                    repo = OutboxRepository(session)
                    events = await repo.fetch_pending(limit=BATCH_SIZE)
                    for event in events:
                        try:
                            await publish_json(
                                exchange,
                                routing_key=event.topic,
                                payload=event.payload,
                                message_id=str(event.id),
                            )
                        except Exception as exc:
                            event.attempts += 1
                            event.last_error = str(exc)[:1000]
                            event.next_attempt_at = utcnow() + _backoff(event.attempts)
                            if event.attempts >= MAX_ATTEMPTS:
                                event.status = OutboxStatus.FAILED
                            logger.warning(
                                "outbox publish failed event_id=%s attempts=%s: %s",
                                event.id,
                                event.attempts,
                                exc,
                            )
                        else:
                            event.status = OutboxStatus.SENT
                            event.sent_at = utcnow()
                            processed += 1
            except Exception as exc:
                logger.warning("outbox poll failed: %s", exc)
                await asyncio.sleep(poll_interval)
                continue
            if processed == 0:
                await asyncio.sleep(poll_interval)
    except asyncio.CancelledError:
        logger.info("outbox publisher cancelled")
        raise
    finally:
        await channel.close()
        await connection.close()
