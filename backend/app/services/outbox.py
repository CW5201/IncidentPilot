from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OutboxStatus
from app.models.outbox import OutboxEvent
from app.repositories.outbox import OutboxRepository


class OutboxService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = OutboxRepository(session)

    async def enqueue(
        self,
        *,
        topic: str,
        payload: dict,
        event_id: uuid.UUID | None = None,
    ) -> OutboxEvent:
        event = OutboxEvent(
            id=event_id or uuid.uuid4(),
            topic=topic,
            payload=payload,
            status=OutboxStatus.PENDING,
        )
        return await self.repo.add(event)
