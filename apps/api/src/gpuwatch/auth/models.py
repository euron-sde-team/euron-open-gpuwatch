"""Signed-out sessions, refused until the token would have expired anyway."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from gpuwatch.core.db import Base


class RevokedSession(Base):
    """One row per signed-out session token (its ``jti``).

    Kept in Postgres rather than the cache: cache eviction must never bring a signed-out
    session back. Rows past ``expires_at`` are pruned on later sign-outs.
    """

    __tablename__ = "revoked_sessions"
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
