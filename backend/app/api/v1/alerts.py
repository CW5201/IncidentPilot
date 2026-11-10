from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles, verify_webhook_token
from app.core.pagination import PageParams, page_params
from app.core.rate_limit import enforce_webhook_rate_limit
from app.db.session import get_session
from app.models.enums import AlertStatus, UserRole
from app.models.user import User
from app.repositories.alert import AlertRepository
from app.schemas.alert import AlertmanagerWebhook, AlertOut, WebhookAck
from app.services.alert import AlertService

router = APIRouter(tags=["alerts"])


@router.post(
    "/webhooks/alertmanager",
    response_model=WebhookAck,
    dependencies=[Depends(verify_webhook_token)],
)
async def alertmanager_webhook(
    payload: AlertmanagerWebhook,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> WebhookAck:
    await enforce_webhook_rate_limit(request)
    service = AlertService(session)
    ack = await service.ingest(payload)
    await session.commit()
    return ack


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(
    response: Response,
    status: AlertStatus | None = None,
    service_name: str | None = None,
    params: PageParams = Depends(page_params),
    _: User = Depends(require_roles(UserRole.VIEWER, UserRole.SRE, UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> list:
    alerts, total = await AlertRepository(session).list(
        status=status,
        service_name=service_name,
        limit=params.page_size,
        offset=params.offset,
    )
    response.headers["X-Total-Count"] = str(total)
    return alerts
