from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import engine, session_scope
from app.models.enums import ServiceTier, UserRole
from app.models.service import Service
from app.models.user import User
from app.workers.outbox_publisher import run_outbox_publisher

logger = logging.getLogger(__name__)


async def _init_db() -> None:
    import app.models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def _seed() -> None:
    settings = get_settings()
    async with session_scope() as session:
        seeds = [
            (
                settings.bootstrap_admin_email,
                settings.bootstrap_admin_password,
                "Platform Admin",
                UserRole.ADMIN,
            ),
            (
                settings.bootstrap_sre_email,
                settings.bootstrap_sre_password,
                "Demo SRE",
                UserRole.SRE,
            ),
            (
                settings.bootstrap_viewer_email,
                settings.bootstrap_viewer_password,
                "Demo Viewer",
                UserRole.VIEWER,
            ),
        ]
        for email, password, full_name, role in seeds:
            existing = await session.scalar(select(User).where(User.email == email.lower()))
            if existing is None:
                session.add(
                    User(
                        email=email.lower(),
                        hashed_password=hash_password(password),
                        full_name=full_name,
                        role=role,
                    )
                )
        service = await session.scalar(select(Service).where(Service.name == "checkout-service"))
        if service is None:
            session.add(
                Service(
                    name="checkout-service",
                    display_name="Checkout Service",
                    namespace="demo",
                    tier=ServiceTier.CORE,
                    repo_url="https://github.com/example/checkout-service",
                    owner_team="payments",
                    slo={"availability": 0.999, "latency_p95_ms": 300},
                    labels={"language": "python", "runtime": "kubernetes"},
                )
            )
    logger.info("seed complete")


async def _outbox_worker() -> None:
    configure_logging()
    await run_outbox_publisher()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="incidentpilot")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db")
    sub.add_parser("seed")
    sub.add_parser("outbox-worker")
    args = parser.parse_args()

    configure_logging()
    if args.command == "init-db":
        asyncio.run(_init_db())
    elif args.command == "seed":
        asyncio.run(_seed())
    elif args.command == "outbox-worker":
        asyncio.run(_outbox_worker())


if __name__ == "__main__":
    main()
