from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

from gpuwatch.audit import service
from gpuwatch.auth.dependencies import Admin
from gpuwatch.core.deps import SessionDep
from gpuwatch.core.schemas import ApiModel, Page, decode_cursor, encode_cursor

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


class AuditOut(ApiModel):
    id: int
    at: datetime
    actor_id: uuid.UUID | None
    actor_email: str | None
    action: str
    target_type: str | None
    target_id: str | None
    details: dict[str, Any]
    ip: str | None


@router.get("", response_model=Page[AuditOut], summary="Append-only audit log")
async def list_audit(
    _: Admin,
    session: SessionDep,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    action: str | None = None,
) -> Page[AuditOut]:
    after = decode_cursor(cursor)
    rows = await service.list_entries(
        session, int(after) if after and after.isdigit() else None, limit, action
    )
    return Page[AuditOut](
        items=[AuditOut.model_validate(r) for r in rows[:limit]],
        next_cursor=encode_cursor(rows[limit - 1].id) if len(rows) > limit else None,
    )
