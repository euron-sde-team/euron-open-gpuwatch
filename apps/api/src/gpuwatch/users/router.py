from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastapi import APIRouter

from gpuwatch.auth.dependencies import Admin, Owner
from gpuwatch.auth.schemas import UserOut
from gpuwatch.core.deps import SessionDep
from gpuwatch.users import service
from gpuwatch.users.models import User
from gpuwatch.users.schemas import UserCreate, UserUpdate

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("", response_model=list[UserOut], summary="List dashboard users")
async def list_users(_: Admin, session: SessionDep) -> Sequence[User]:
    return await service.list_users(session)


@router.post("", response_model=UserOut, status_code=201, summary="Invite a dashboard user")
async def create_user(body: UserCreate, actor: Owner, session: SessionDep) -> User:
    return await service.create_user(session, body, actor)


@router.patch("/{user_id}", response_model=UserOut, summary="Update a user's name, role or access")
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, actor: Owner, session: SessionDep
) -> User:
    return await service.update_user(session, user_id, body, actor)
