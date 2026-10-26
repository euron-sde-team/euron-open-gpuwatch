from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from gpuwatch.core.schemas import ApiModel, Email


class LoginRequest(ApiModel):
    email: Email
    password: str = Field(min_length=1, max_length=256)


class UserOut(ApiModel):
    id: uuid.UUID
    email: str
    name: str
    role: str
    disabled: bool
    last_login_at: datetime | None
    created_at: datetime


class SessionOut(ApiModel):
    user: UserOut
    session_token: str = Field(description="Bearer token for API clients; browsers use the cookie")
    expires_in_s: int


class PasswordChange(ApiModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)
