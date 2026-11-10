from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.pagination import PageParams, page_params
from app.db.session import get_session
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.audit import AuditRepository
from app.schemas.audit import AuditLogOut

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
async def list_audit_logs(
    response: Response,
    resource_type: str | None = None,
    resource_id: str | None = None,
    params: PageParams = Depends(page_params),
    _: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> list:
    logs, total = await AuditRepository(session).list(
        resource_type=resource_type,
        resource_id=resource_id,
        limit=params.page_size,
        offset=params.offset,
    )
    response.headers["X-Total-Count"] = str(total)
    return logs
