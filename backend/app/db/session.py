from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

_settings = get_settings()


def _build_engine() -> AsyncEngine:
    url = _settings.database_url
    kwargs: dict = {
        "echo": _settings.database_echo,
        "pool_pre_ping": True,
    }
    if url.startswith("sqlite"):
        kwargs = {
            "echo": _settings.database_echo,
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    else:
        kwargs["pool_size"] = _settings.database_pool_size
        kwargs["max_overflow"] = _settings.database_max_overflow
    return create_async_engine(url, **kwargs)


engine: AsyncEngine = _build_engine()
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    await engine.dispose()
