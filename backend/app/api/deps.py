from __future__ import annotations

import uuid

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import Forbidden, Unauthenticated
from app.core.security import constant_time_compare, decode_access_token
from app.db.session import get_session
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user import UserRepository

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None:
        raise Unauthenticated("Missing bearer token")
    payload = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (TypeError, ValueError) as exc:
        raise Unauthenticated("Invalid token subject") from exc
    user = await UserRepository(session).get(user_id)
    if user is None:
        raise Unauthenticated("User no longer exists")
    if not user.is_active:
        raise Unauthenticated("User account is disabled")
    return user


def require_roles(*roles: UserRole):
    allowed = set(roles)

    async def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise Forbidden("Insufficient role")
        return user

    return dependency


async def verify_webhook_token(
    x_webhook_token: str | None = Header(default=None, alias="X-Webhook-Token"),
) -> None:
    settings = get_settings()
    if settings.is_test:
        return
    if not x_webhook_token or not constant_time_compare(
        x_webhook_token, settings.webhook_token
    ):
        raise Unauthenticated("Invalid webhook token")


def request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
