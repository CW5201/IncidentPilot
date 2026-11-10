from __future__ import annotations

import asyncio
import json
import logging
import uuid

from aio_pika.abc import AbstractIncomingMessage

from app.db.session import session_scope
from app.infra.mq import connect_robust, declare_topology
from app.models.enums import ActorType, IncidentStatus
from app.repositories.incident import IncidentRepository
from app.services.incident import IncidentService

logger = logging.getLogger(__name__)


async def _handle_message(message: AbstractIncomingMessage) -> None:
    payload = json.loads(message.body.decode("utf-8"))
    incident_id = uuid.UUID(payload["incident_id"])
    async with session_scope() as session:
        service = IncidentService(session)
        incident = await service.get(incident_id)
        if incident.status == IncidentStatus.DETECTED:
            await service.change_status(
                incident_id,
                IncidentStatus.INVESTIGATING,
                actor_type=ActorType.SYSTEM,
                note="Investigation queued by incident.created event",
            )
        else:
            await IncidentRepository(session).add_timeline(
                incident_id=incident_id,
                event_type="investigation_requested",
                summary="Investigation request received for an active incident",
                payload={"message_id": message.message_id},
                actor_type=ActorType.SYSTEM,
                event_key=f"investigation:{message.message_id}",
            )
    logger.info(
        "investigation request consumed incident_id=%s message_id=%s",
        incident_id,
        message.message_id,
    )


async def run_investigation_consumer(
    *,
    stop_event: asyncio.Event | None = None,
) -> None:
    connection = await connect_robust()
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)
    _exchange, queue, _dlq = await declare_topology(channel)

    async def on_message(message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=True):
            await _handle_message(message)

    consumer_tag = await queue.consume(on_message)
    logger.info("investigation consumer started")
    try:
        if stop_event is None:
            await asyncio.Future()
        else:
            await stop_event.wait()
    except asyncio.CancelledError:
        logger.info("investigation consumer cancelled")
        raise
    finally:
        await queue.cancel(consumer_tag)
        await channel.close()
        await connection.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_investigation_consumer())
