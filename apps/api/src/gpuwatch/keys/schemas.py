"""API keys: read-only bearer tokens for the REST API (GET requests only)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from gpuwatch.core.schemas import ApiModel


class KeyIn(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    rpm_limit: int | None = Field(None, ge=1, le=1_000_000)
    expires_at: datetime | None = None


class KeyUpdate(ApiModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    rpm_limit: int | None = Field(None, ge=1, le=1_000_000)
    expires_at: datetime | None = None


class KeyOut(ApiModel):
    id: uuid.UUID
    name: str
    prefix: str
    display: str = Field(description="Safe identifier: gwk_<prefix>_****")
    rpm_limit: int | None
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class KeyCreated(KeyOut):
    key: str = Field(description="The full key. Shown once; store it now")
