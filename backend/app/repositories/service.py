from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service import Service


class ServiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, service_id: uuid.UUID) -> Service | None:
        return await self.session.get(Service, service_id)

    async def get_by_name(self, name: str) -> Service | None:
        stmt = select(Service).where(Service.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, service: Service) -> Service:
        self.session.add(service)
        await self.session.flush()
        return service

    async def list(self, limit: int = 100, offset: int = 0) -> tuple[list[Service], int]:
        total = await self.session.scalar(select(func.count()).select_from(Service))
        stmt = select(Service).order_by(Service.name).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), int(total or 0)
