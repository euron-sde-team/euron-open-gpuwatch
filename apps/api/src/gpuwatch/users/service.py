"""Dashboard user management. Guards keep at least one active owner at all times."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gpuwatch.audit.service import Actor, audit
from gpuwatch.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from gpuwatch.core.security import hash_password, password_problems
from gpuwatch.users.models import User
from gpuwatch.users.schemas import UserCreate, UserUpdate


async def list_users(session: AsyncSession) -> Sequence[User]:
    return (await session.scalars(select(User).order_by(User.created_at))).all()


async def _active_owners(session: AsyncSession) -> int:
    """Count active owners, locking their rows until commit so two owners demoting each
    other at once cannot both pass the last-owner check."""
    rows = await session.scalars(
        select(User.id).where(User.role == "owner", User.disabled.is_(False)).with_for_update()
    )
    return len(rows.all())


async def create_user(session: AsyncSession, data: UserCreate, actor: Actor) -> User:
    if await session.scalar(select(User.id).where(func.lower(User.email) == data.email.lower())):
        raise ConflictError("A user with this email already exists", code="email_taken")
    if problems := password_problems(data.password):
        raise AppError("Password needs " + ", ".join(problems), code="weak_password")
    if data.role == "owner" and actor.role != "owner":
        raise PermissionDeniedError("Only an owner can create another owner")
    user = User(
        email=data.email.lower(),
        name=data.name,
        role=data.role,
        password_hash=await asyncio.to_thread(hash_password, data.password),
    )
    session.add(user)
    await session.flush()
    audit(session, actor, "user.created", "user", user.id, email=user.email, role=user.role)
    await session.commit()
    return user


async def update_user(
    session: AsyncSession, user_id: uuid.UUID, data: UserUpdate, actor: Actor
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    changes = data.model_dump(exclude_unset=True)
    if user.id == actor.id and ("role" in changes or changes.get("disabled")):
        raise PermissionDeniedError("You cannot change your own role or disable yourself")
    if (changes.get("role") == "owner" or user.role == "owner") and actor.role != "owner":
        raise PermissionDeniedError("Only an owner can change an owner")
    demoting = user.role == "owner" and (
        changes.get("role", "owner") != "owner" or changes.get("disabled")
    )
    if demoting and await _active_owners(session) <= 1:
        raise ConflictError("At least one active owner is required", code="last_owner")
    for field, value in changes.items():
        setattr(user, field, value)
    if "role" in changes or changes.get("disabled"):
        user.session_version += 1  # role and access changes take effect immediately
    audit(session, actor, "user.updated", "user", user.id, **changes)
    await session.commit()
    return user
