from __future__ import annotations

from fastapi import APIRouter, Request, Response
from redis.exceptions import RedisError

from gpuwatch.audit.service import Actor, audit
from gpuwatch.auth import service
from gpuwatch.auth.dependencies import SESSION_COOKIE, CurrentUser, revoke, session_token
from gpuwatch.auth.schemas import LoginRequest, PasswordChange, SessionOut, UserOut
from gpuwatch.core.deps import ContainerDep, SessionDep, client_ip
from gpuwatch.core.errors import RateLimitedError
from gpuwatch.core.schemas import Ack
from gpuwatch.core.security import decode_session, issue_session
from gpuwatch.limits.limiter import LimitDecision
from gpuwatch.users.models import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
LOGIN_RPM_PER_IP = 20


def _session(response: Response, container: ContainerDep, user: User) -> SessionOut:
    settings = container.settings
    token = issue_session(
        user.id,
        user.role,
        user.session_version,
        settings.session_secret,
        settings.session_ttl_hours,
    )
    ttl = settings.session_ttl_hours * 3600
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=ttl,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return SessionOut(user=UserOut.model_validate(user), session_token=token, expires_in_s=ttl)


@router.post("/login", response_model=SessionOut, summary="Sign in to the dashboard")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    container: ContainerDep,
    session: SessionDep,
) -> SessionOut:
    ip = client_ip(request)
    try:
        decision = await container.kv.hit(f"login:{ip}", LOGIN_RPM_PER_IP)
    except (RedisError, OSError):
        # Per-IP throttling is a convenience; per-account lockout lives in Postgres and
        # still applies, so sign-in keeps working while Redis is down.
        decision = LimitDecision(allowed=True)
    if not decision.allowed:
        raise RateLimitedError(
            "Too many sign-in attempts from this address. Wait a minute and try again",
            headers={"retry-after": str(decision.retry_after_s)},
        )
    user = await service.authenticate(session, body.email, body.password, ip)
    response.headers["cache-control"] = "no-store"
    return _session(response, container, user)


@router.post("/logout", response_model=Ack, summary="Sign out")
async def logout(
    request: Request, response: Response, container: ContainerDep, session: SessionDep
) -> Ack:
    """Ends this session server-side too: the token is refused until it expires."""
    token, _ = session_token(request)
    claims = decode_session(token, container.settings.session_secret) if token else None
    if claims is not None:
        await revoke(session, claims)
        user = await session.get(User, claims.user_id)
        if user is not None:
            actor = Actor(user.id, user.email, user.role, client_ip(request))
            audit(session, actor, "auth.logout", "user", user.id)
        await session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return Ack(message="Signed out")


@router.get("/me", response_model=UserOut, summary="The signed-in user")
async def me(user: CurrentUser) -> User:
    return user


@router.post("/password", response_model=SessionOut, summary="Change your password")
async def password(
    body: PasswordChange,
    request: Request,
    response: Response,
    user: CurrentUser,
    container: ContainerDep,
    session: SessionDep,
) -> SessionOut:
    actor: Actor = request.state.actor
    user = await service.change_password(
        session, user, body.current_password, body.new_password, actor
    )
    return _session(response, container, user)
