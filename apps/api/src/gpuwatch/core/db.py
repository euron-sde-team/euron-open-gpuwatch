"""Database engine, session factory and the declarative base shared by every domain."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[str]: JSONB}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Database:
    """Owns the engine and session factory for one application instance."""

    def __init__(self, url: str, *, pool_size: int = 10, max_overflow: int = 20) -> None:
        self.engine: AsyncEngine = create_async_engine(
            url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
            pool_recycle=1800,
            # Never echo bound values (password hashes, key hashes, content) into an
            # exception message, and so never into a log line.
            hide_parameters=True,
            # Rollups bucket with date_trunc, which follows the session time zone; cost
            # hours and recompute ranges are UTC. Pin it, so a Postgres initialised in a
            # half-hour zone cannot shift the hour buckets.
            connect_args={"server_settings": {"timezone": "UTC"}},
        )
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()


def import_all_models() -> None:
    """Import every domain's models so Base.metadata is complete (Alembic, tests)."""
    from gpuwatch.alerts import models as _alerts  # noqa: F401
    from gpuwatch.audit import models as _audit  # noqa: F401
    from gpuwatch.auth import models as _auth  # noqa: F401
    from gpuwatch.costs import models as _costs  # noqa: F401
    from gpuwatch.fleet import models as _fleet  # noqa: F401
    from gpuwatch.inference import models as _inference  # noqa: F401
    from gpuwatch.insights import models as _insights  # noqa: F401
    from gpuwatch.keys import models as _keys  # noqa: F401
    from gpuwatch.telemetry import models as _telemetry  # noqa: F401
    from gpuwatch.users import models as _users  # noqa: F401
