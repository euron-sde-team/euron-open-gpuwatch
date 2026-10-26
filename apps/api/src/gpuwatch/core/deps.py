"""FastAPI dependencies shared across domains."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from gpuwatch.core.container import Container


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


async def get_session(
    container: Annotated[Container, Depends(get_container)],
) -> AsyncIterator[AsyncSession]:
    async with container.db.sessionmaker() as session:
        yield session


ContainerDep = Annotated[Container, Depends(get_container)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def client_ip(request: Request) -> str | None:
    """The peer address. Uvicorn's proxy-headers support already resolved X-Forwarded-For
    against FORWARDED_ALLOW_IPS (the load balancer), so a client cannot forge it."""
    return request.client.host if request.client else None
