from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    client_ip,
    get_current_user,
    request_id,
    require_roles,
)
from app.core.config import get_settings
from app.core.errors import NotFound
from app.core.pagination import PageParams, page_params
from app.core.rate_limit import enforce_login_rate_limit
from app.db.session import get_session
from app.models.enums import ActorType, UserRole
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import (
    LoginRequest,
    PasswordChange,
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services.audit import AuditService
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
admin_router = APIRouter(prefix="/users", tags=["users"])


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.refresh_cookie_name,
        token,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path=f"{settings.api_prefix}/auth",
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    await enforce_login_rate_limit(request)
    service = AuthService(session)
    user = await service.authenticate(payload.email, payload.password)
    access_token, refresh_token, expires_in = await service.issue_tokens(
        user,
        user_agent=request.headers.get("User-Agent"),
        ip=client_ip(request),
    )
    await AuditService(session).record(
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
        actor_type=ActorType.USER,
        actor_id=user.id,
        ip=client_ip(request),
        request_id=request_id(request),
    )
    await session.commit()
    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    payload: RefreshRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    settings = get_settings()
    raw_token = payload.refresh_token if payload else request.cookies.get(
        settings.refresh_cookie_name
    )
    if not raw_token:
        from app.core.errors import Unauthenticated

        raise Unauthenticated("Missing refresh token")
    service = AuthService(session)
    access_token, refresh_token, expires_in = await service.rotate_refresh_token(
        raw_token,
        user_agent=request.headers.get("User-Agent"),
        ip=client_ip(request),
    )
    await session.commit()
    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    payload: RefreshRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_session),
) -> Response:
    settings = get_settings()
    raw_token = payload.refresh_token if payload else request.cookies.get(
        settings.refresh_cookie_name
    )
    if raw_token:
        await AuthService(session).logout(raw_token)
        await session.commit()
    response.delete_cookie(settings.refresh_cookie_name, path=f"{settings.api_prefix}/auth")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChange,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    service = AuthService(session)
    await service.change_password(
        user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    await AuditService(session).record(
        action="auth.password_changed",
        resource_type="user",
        resource_id=user.id,
        actor_id=user.id,
        ip=client_ip(request),
        request_id=request_id(request),
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.get("", response_model=list[UserOut])
async def list_users(
    params: PageParams = Depends(page_params),
    _: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> list[User]:
    users, _total = await UserRepository(session).list(
        limit=params.page_size, offset=params.offset
    )
    return users


@admin_router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    request: Request,
    actor: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> User:
    service = AuthService(session)
    user = await service.create_user(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
    )
    await AuditService(session).record(
        action="user.created",
        resource_type="user",
        resource_id=user.id,
        actor_id=actor.id,
        after={"email": user.email, "role": user.role.value},
        ip=client_ip(request),
        request_id=request_id(request),
    )
    await session.commit()
    return user


@admin_router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    request: Request,
    actor: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> User:
    repo = UserRepository(session)
    user = await repo.get(user_id)
    if user is None:
        raise NotFound("User not found")
    before = {"full_name": user.full_name, "role": user.role.value, "is_active": user.is_active}
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
        if not payload.is_active:
            await repo.revoke_all_refresh_tokens(user.id)
    await session.flush()
    await AuditService(session).record(
        action="user.updated",
        resource_type="user",
        resource_id=user.id,
        actor_id=actor.id,
        before=before,
        after={"full_name": user.full_name, "role": user.role.value, "is_active": user.is_active},
        ip=client_ip(request),
        request_id=request_id(request),
    )
    await session.commit()
    return user
