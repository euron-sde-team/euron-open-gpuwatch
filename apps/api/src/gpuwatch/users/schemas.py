from __future__ import annotations

from typing import Literal

from pydantic import Field

from gpuwatch.core.schemas import ApiModel, Email

Role = Literal["owner", "admin", "viewer"]


class UserCreate(ApiModel):
    email: Email
    name: str = Field(min_length=1, max_length=200)
    role: Role = "viewer"
    password: str = Field(min_length=10, max_length=256)


class UserUpdate(ApiModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    role: Role | None = None
    disabled: bool | None = None
