from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.enums import ActorType
from app.repositories.audit import AuditRepository


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = AuditRepository(session)

    async def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str | uuid.UUID | None = None,
        actor_type: ActorType = ActorType.USER,
        actor_id: str | uuid.UUID | None = None,
        before: dict | None = None,
        after: dict | None = None,
        ip: str | None = None,
        request_id: str | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor_type=actor_type,
            actor_id=str(actor_id) if actor_id is not None else None,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            before=before,
            after=after,
            ip=ip,
            request_id=request_id,
        )
        return await self.repo.add(entry)
