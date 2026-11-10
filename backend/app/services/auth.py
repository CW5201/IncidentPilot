from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import Conflict, Unauthenticated
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.core.time import ensure_aware, utcnow
from app.models.user import RefreshToken, User
from app.repositories.user import UserRepository


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.users.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            raise Unauthenticated("Invalid email or password")
        if not user.is_active:
            raise Unauthenticated("User account is disabled")
        await self.users.touch_login(user)
        return user

    async def issue_tokens(
        self,
        user: User,
        *,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> tuple[str, str, int]:
        settings = get_settings()
        access_token, expires_in = create_access_token(user_id=user.id, role=user.role.value)
        raw_refresh, refresh_hash, jti = generate_refresh_token()
        refresh = RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            jti=jti,
            expires_at=utcnow() + timedelta(days=settings.refresh_token_expire_days),
            user_agent=(user_agent or "")[:512] or None,
            ip=ip,
        )
        await self.users.add_refresh_token(refresh)
        return access_token, raw_refresh, expires_in

    async def rotate_refresh_token(
        self,
        raw_refresh: str,
        *,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> tuple[str, str, int]:
        token = await self.users.get_refresh_token(hash_refresh_token(raw_refresh))
        if token is None or token.revoked_at is not None:
            raise Unauthenticated("Refresh token is invalid")
        if ensure_aware(token.expires_at) <= utcnow():
            raise Unauthenticated("Refresh token has expired")
        user = await self.users.get(token.user_id)
        if user is None or not user.is_active:
            raise Unauthenticated("User account is disabled")
        await self.users.revoke_refresh_token(token)
        return await self.issue_tokens(user, user_agent=user_agent, ip=ip)

    async def logout(self, raw_refresh: str) -> None:
        token = await self.users.get_refresh_token(hash_refresh_token(raw_refresh))
        if token is not None and token.revoked_at is None:
            await self.users.revoke_refresh_token(token)

    async def create_user(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        role,
    ) -> User:
        existing = await self.users.get_by_email(email)
        if existing is not None:
            raise Conflict("A user with this email already exists")
        user = User(
            email=email.lower(),
            hashed_password=hash_password(password),
            full_name=full_name,
            role=role,
        )
        return await self.users.create(user)

    async def change_password(
        self,
        user: User,
        *,
        current_password: str,
        new_password: str,
    ) -> None:
        if not verify_password(current_password, user.hashed_password):
            raise Unauthenticated("Current password is incorrect")
        user.hashed_password = hash_password(new_password)
        await self.users.revoke_all_refresh_tokens(user.id)
        await self.session.flush()
