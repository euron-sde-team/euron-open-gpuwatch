"""Append-only audit trail. Written in the same transaction as the change it describes,
so a change without an audit row cannot be committed."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gpuwatch.audit.models import AuditLog


@dataclass(frozen=True, slots=True)
class Actor:
    id: uuid.UUID | None
    email: str | None
    role: str
    ip: str | None = None


def audit(
    session: AsyncSession,
    actor: Actor,
    action: str,
    target_type: str | None = None,
    target_id: object | None = None,
    **details: Any,
) -> None:
    session.add(
        AuditLog(
            actor_id=actor.id,
            actor_email=actor.email,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            details=details,
            ip=actor.ip,
        )
    )


async def list_entries(
    session: AsyncSession, after_id: int | None, limit: int, action: str | None
) -> list[AuditLog]:
    """Newest first, keyset-paginated on id; ``limit + 1`` rows so the caller can tell
    whether another page exists. ``action`` filters by prefix (``user.`` matches all)."""
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit + 1)
    if after_id is not None:
        stmt = stmt.where(AuditLog.id < after_id)
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action))
    return list((await session.scalars(stmt)).all())
