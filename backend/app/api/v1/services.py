from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.errors import NotFound
from app.core.pagination import PageParams, page_params
from app.db.session import get_session
from app.models.enums import UserRole
from app.models.service import Service
from app.models.user import User
from app.repositories.service import ServiceRepository
from app.schemas.service import ServiceCreate, ServiceOut

router = APIRouter(prefix="/services", tags=["services"])


@router.get("", response_model=list[ServiceOut])
async def list_services(
    response: Response,
    params: PageParams = Depends(page_params),
    _: User = Depends(require_roles(UserRole.VIEWER, UserRole.SRE, UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> list[Service]:
    services, total = await ServiceRepository(session).list(
        limit=params.page_size, offset=params.offset
    )
    response.headers["X-Total-Count"] = str(total)
    return services


@router.get("/{service_id}", response_model=ServiceOut)
async def get_service(
    service_id: uuid.UUID,
    _: User = Depends(require_roles(UserRole.VIEWER, UserRole.SRE, UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> Service:
    service = await ServiceRepository(session).get(service_id)
    if service is None:
        raise NotFound("Service not found")
    return service


@router.post("", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
async def create_service(
    payload: ServiceCreate,
    _: User = Depends(require_roles(UserRole.SRE, UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> Service:
    service = Service(
        name=payload.name,
        display_name=payload.display_name,
        namespace=payload.namespace,
        tier=payload.tier,
        repo_url=payload.repo_url,
        owner_team=payload.owner_team,
        slo=payload.slo,
        labels=payload.labels,
    )
    service = await ServiceRepository(session).create(service)
    await session.commit()
    return service
