"""``gpuwatch seed-demo``: the demo organisation's configuration.

Only configuration lives here: users, example rates, workload rules, an email channel that
lands in Mailpit, an API key, and a simulated enrolment token written where the demo agents
read it. Every number in the dashboard then comes from the simulated agents (the real agent
with its simulated collector) through the same ingest API a real agent uses.
"""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from gpuwatch.alerts.models import AlertRule, Channel
from gpuwatch.audit.service import Actor
from gpuwatch.core.config import get_settings
from gpuwatch.core.container import Container
from gpuwatch.core.money import usd_to_nusd
from gpuwatch.core.security import hash_password
from gpuwatch.costs.models import GpuRate, WorkloadRule
from gpuwatch.fleet import service as fleet_service
from gpuwatch.fleet.models import EnrolmentToken
from gpuwatch.fleet.schemas import EnrolmentTokenIn
from gpuwatch.keys import service as key_service
from gpuwatch.keys.schemas import KeyIn
from gpuwatch.users.models import User

OWNER_EMAIL = "owner@gpuwatch.local"
USERS = (
    (OWNER_EMAIL, "Priya Raman", "owner"),
    ("admin@gpuwatch.local", "Marco Silva", "admin"),
    ("viewer@gpuwatch.local", "Dana Okafor", "viewer"),
)
# Example on-demand style rates for the simulated GPU models, labelled as examples. Real
# deployments set their own; GPUWatch ships no prices.
RATES = (
    ("NVIDIA H100 80GB HBM3", Decimal("2.49")),
    ("NVIDIA L40S", Decimal("1.10")),
    ("NVIDIA L4", Decimal("0.60")),
    ("NVIDIA GeForce RTX 4090", Decimal("0.40")),
)
RULES = (
    (10, "llm-finetune", "Research", r"^python3?$", None, None, "role=training"),
    (20, "llama-chat", "Platform", r"vllm", None, None, None),
    (30, "summarizer", "Platform", r"text-generation", None, None, None),
    (40, "notebooks", "Research", r"jupyter|ipykernel", None, None, None),
    (50, "batch-scoring", "Analytics", r"score", None, None, None),
)
TOKEN_NAME = "Demo fleet (simulated)"  # noqa: S105 a display name


async def _owner(container: Container, password: str) -> Actor:
    async with container.db.sessionmaker() as session:
        for email, name, role in USERS:
            user = await session.scalar(select(User).where(func.lower(User.email) == email))
            if user is None:
                session.add(
                    User(
                        email=email,
                        name=name,
                        role=role,
                        password_hash=await asyncio.to_thread(hash_password, password),
                    )
                )
        await session.commit()
        owner = await session.scalar(select(User).where(User.email == OWNER_EMAIL))
        assert owner is not None
        return Actor(owner.id, owner.email, owner.role, None)


async def _configure(container: Container, actor: Actor) -> str | None:
    """Rates, rules, channel, rule wiring and an API key. Returns the API key (new only)."""
    async with container.db.sessionmaker() as session:
        for model, usd in RATES:
            exists = await session.scalar(
                select(GpuRate.id).where(GpuRate.scope == "model", GpuRate.gpu_model == model)
            )
            if not exists:
                session.add(
                    GpuRate(
                        scope="model",
                        gpu_model=model,
                        nusd_per_hour=usd_to_nusd(usd),
                        note="Example rate for the demo; set your own",
                    )
                )
        if not await session.scalar(select(func.count()).select_from(WorkloadRule)):
            for priority, workload, team, pattern, prefix, user, label in RULES:
                session.add(
                    WorkloadRule(
                        priority=priority,
                        workload=workload,
                        team=team,
                        process_pattern=pattern,
                        container_prefix=prefix,
                        username=user,
                        host_label=label,
                    )
                )
        channel = await session.scalar(select(Channel).where(Channel.name == "Ops on-call email"))
        if channel is None:
            channel = Channel(name="Ops on-call email", kind="email", emails=["ops@gpuwatch.local"])
            session.add(channel)
            await session.flush()
        for rule in (await session.scalars(select(AlertRule))).all():
            if rule.severity in ("warning", "critical") and str(channel.id) not in rule.channel_ids:
                rule.channel_ids = [*rule.channel_ids, str(channel.id)]
        if not await session.scalar(
            select(AlertRule.id).where(AlertRule.name == "Training GPU too hot")
        ):
            session.add(
                AlertRule(
                    name="Training GPU too hot",
                    kind="threshold",
                    metric="temp_c",
                    operator="gt",
                    threshold=80,
                    duration_s=300,
                    scope_label="role=training",
                    severity="warning",
                    channel_ids=[str(channel.id)],
                )
            )
        await session.commit()
        has_key = await key_service.count_active(session)
        if has_key:
            return None
        created = await key_service.create_key(
            session, KeyIn(name="Grafana (read only)"), container.settings.api_key_pepper, actor
        )
        return created.key


def _has_token(path: Path) -> bool:
    return path.exists() and bool(path.read_text().strip())


def _write_token(path: Path, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n")


async def _enrolment_token(container: Container, actor: Actor, token_file: Path) -> None:
    """A simulated enrolment token, written for the demo agents (once)."""
    if await asyncio.to_thread(_has_token, token_file):
        return
    async with container.db.sessionmaker() as session:
        old = await session.scalar(select(EnrolmentToken).where(EnrolmentToken.name == TOKEN_NAME))
        if old is not None and old.revoked_at is None:
            await fleet_service.revoke_token(session, old.id, actor)
        created = await fleet_service.create_token(
            session,
            EnrolmentTokenIn(name=TOKEN_NAME, labels={"env": "demo"}, expires_in_days=365),
            container.settings.api_key_pepper,
            actor,
            simulated=True,
        )
    await asyncio.to_thread(_write_token, token_file, created.token)


async def run(token_file: str = "/demo/enrolment-token") -> None:  # noqa: S107 a path
    settings = get_settings()
    if settings.environment == "production":
        raise SystemExit(
            "seed-demo creates well-known demo credentials and refuses ENVIRONMENT=production"
        )
    password = (
        os.environ.get("GW_DEMO_PASSWORD") or os.environ.get("DEMO_PASSWORD") or "WatchDemo2026"
    )
    container = Container.build(settings)
    try:
        actor = await _owner(container, password)
        key = await _configure(container, actor)
        await _enrolment_token(container, actor, Path(token_file))
        await container.config_cache.invalidate()
        print("demo configuration ready; the simulated agents enrol and backfill history now")
        print()
        print(f"  dashboard login   {OWNER_EMAIL} / {password}")
        print("                    admin@gpuwatch.local, viewer@gpuwatch.local (same password)")
        if key:
            print(f"  read-only API key {key}")
        print("  alert email       http://localhost:4425 (Mailpit)")
    finally:
        await container.close()
