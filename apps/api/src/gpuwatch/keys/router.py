from __future__ import annotations

import uuid

from fastapi import APIRouter

from gpuwatch.auth.dependencies import Admin
from gpuwatch.core.deps import ContainerDep, SessionDep
from gpuwatch.keys import service
from gpuwatch.keys.schemas import KeyCreated, KeyIn, KeyOut, KeyUpdate

router = APIRouter(prefix="/api/v1/keys", tags=["api keys"])


@router.get("", response_model=list[KeyOut], summary="List API keys")
async def list_keys(_: Admin, session: SessionDep, include_revoked: bool = False) -> list[KeyOut]:
    return await service.list_keys(session, include_revoked)


@router.post("", response_model=KeyCreated, status_code=201, summary="Create a key (shown once)")
async def create_key(
    body: KeyIn, actor: Admin, session: SessionDep, container: ContainerDep
) -> KeyCreated:
    out = await service.create_key(session, body, container.settings.api_key_pepper, actor)
    await container.config_cache.invalidate()
    return out


@router.patch("/{key_id}", response_model=KeyOut, summary="Update a key's name, limit or expiry")
async def update_key(
    key_id: uuid.UUID, body: KeyUpdate, actor: Admin, session: SessionDep, container: ContainerDep
) -> KeyOut:
    out = await service.update_key(session, key_id, body, actor)
    await container.config_cache.invalidate()
    return out


@router.post("/{key_id}/revoke", response_model=KeyOut, summary="Revoke a key immediately")
async def revoke_key(
    key_id: uuid.UUID, actor: Admin, session: SessionDep, container: ContainerDep
) -> KeyOut:
    out = await service.revoke_key(session, key_id, actor)
    await container.config_cache.invalidate()
    return out
