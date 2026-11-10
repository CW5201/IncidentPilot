from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.enums import AlertStatus


class AlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, alert_id: uuid.UUID) -> Alert | None:
        return await self.session.get(Alert, alert_id)

    async def get_by_fingerprint(
        self, fingerprint: str, starts_at: datetime
    ) -> Alert | None:
        stmt = select(Alert).where(
            Alert.fingerprint == fingerprint,
            Alert.starts_at == starts_at,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, alert: Alert) -> Alert:
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def list(
        self,
        *,
        status: AlertStatus | None = None,
        service_name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Alert], int]:
        conditions = []
        if status is not None:
            conditions.append(Alert.status == status)
        if service_name:
            conditions.append(Alert.service_name == service_name)
        count_stmt = select(func.count()).select_from(Alert)
        stmt = select(Alert).order_by(Alert.last_seen_at.desc())
        if conditions:
            count_stmt = count_stmt.where(*conditions)
            stmt = stmt.where(*conditions)
        total = await self.session.scalar(count_stmt)
        result = await self.session.execute(stmt.limit(limit).offset(offset))
        return list(result.scalars().all()), int(total or 0)
