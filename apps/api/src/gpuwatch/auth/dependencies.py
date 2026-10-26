"""Authentication: session cookie (browser), bearer session token, or a read-only API key.

``gwk_`` API keys authenticate as a viewer and may only read (GET); every change needs a
signed-in user with the right role. Cookie-authenticated mutations must carry
``X-GPUWatch-CSRF: 1``. Browsers cannot add a
custom header to a cross-site request without a CORS preflight, which the allowlist
refuses, so this blocks CSRF without server-side token state.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from gpuwatch.audit.service import Actor
from gpuwatch.auth.models import RevokedSession
from gpuwatch.core.deps import ContainerDep, SessionDep, client_ip
from gpuwatch.core.errors import AuthenticationError, PermissionDeniedError
from gpuwatch.core.security import API_KEY_PREFIX, SessionClaims, decode_session
from gpuwatch.keys.dependencies import authenticate_key
from gpuwatch.users.models import User

SESSION_COOKIE = "gw_session"
CSRF_HEADER = "x-gpuwatch-csrf"
ROLE_RANK = {"viewer": 0, "admin": 1, "owner": 2}
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def is_revoked(session: AsyncSession, claims: SessionClaims) -> bool:
    """A signed-out session stays refused until it would have expired anyway (a primary
    key lookup in Postgres: durable, and never evicted like a cache entry)."""
    if not claims.jti:
        return False
    return await session.get(RevokedSession, claims.jti) is not None


async def revoke(session: AsyncSession, claims: SessionClaims) -> None:
    """Record a signed-out session and prune rows whose tokens have expired anyway."""
    if not claims.jti or claims.expires_at is None:
        return
    now = datetime.now(UTC)
    await session.execute(delete(RevokedSession).where(RevokedSession.expires_at < now))
    if claims.expires_at > now:
        await session.execute(
            insert(RevokedSession)
            .values(jti=claims.jti, expires_at=claims.expires_at)
            .on_conflict_do_nothing()
        )


def session_token(request: Request) -> tuple[str | None, bool]:
    """The session token and whether it came from the cookie."""
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else None
    if token:
        return token, False
    cookie = request.cookies.get(SESSION_COOKIE)
    return cookie, cookie is not None


async def current_user(request: Request, container: ContainerDep, session: SessionDep) -> User:
    # An explicit Authorization header wins: browsers never attach it cross-site, so it
    # needs no CSRF check. The cookie is the fallback for the dashboard.
    token, via_cookie = session_token(request)
    if not token:
        raise AuthenticationError("Sign in to continue", code="not_signed_in")
    claims = decode_session(token, container.settings.session_secret)
    if claims is None or await is_revoked(session, claims):
        raise AuthenticationError("Your session expired. Sign in again", code="session_expired")
    user = await session.get(User, claims.user_id)
    if user is None or user.disabled or user.session_version != claims.session_version:
        raise AuthenticationError("Your session expired. Sign in again", code="session_expired")
    if (
        via_cookie
        and request.method not in _SAFE_METHODS
        and request.headers.get(CSRF_HEADER) != "1"
    ):
        raise PermissionDeniedError("Missing CSRF header", code="csrf_required")
    request.state.actor = Actor(user.id, user.email, user.role, client_ip(request))
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def current_actor(request: Request, container: ContainerDep, session: SessionDep) -> Actor:
    """A signed-in user, or an API key acting as a read-only viewer."""
    token, _ = session_token(request)
    if token and token.startswith(f"{API_KEY_PREFIX}_"):
        if request.method not in _SAFE_METHODS:
            raise PermissionDeniedError(
                "API keys are read-only. Sign in to make changes", code="read_only_key"
            )
        key = await authenticate_key(token, container)
        actor = Actor(key.id, f"api key: {key.name}", "viewer", client_ip(request))
        request.state.actor = actor
        return actor
    await current_user(request, container, session)
    signed_in: Actor = request.state.actor
    return signed_in


CurrentActor = Annotated[Actor, Depends(current_actor)]


def require_role(role: str) -> Callable[..., Coroutine[Any, Any, Actor]]:
    async def dependency(actor: CurrentActor) -> Actor:
        if ROLE_RANK.get(actor.role, -1) < ROLE_RANK[role]:
            raise PermissionDeniedError(
                f"This action needs the {role} role", code="insufficient_role"
            )
        return actor

    return dependency


Viewer = Annotated[Actor, Depends(require_role("viewer"))]
Admin = Annotated[Actor, Depends(require_role("admin"))]
Owner = Annotated[Actor, Depends(require_role("owner"))]
