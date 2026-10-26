"""Integration harness: the real app in-process against real Postgres (and Redis, Mailpit,
Floci S3 and KMS when the option matrix selects them).

    make test-integration      (starts Postgres, Redis and Mailpit containers if needed)
    make test-matrix           (reruns everything under every backend combination)

Safety: the suite truncates every table, so it refuses any database whose name does not
contain "test", and any non-local host unless ALLOW_REMOTE_TEST_DB=true.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from gpuwatch.core.config import Settings
from gpuwatch.core.container import Container
from gpuwatch.main import create_app

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://gpuwatch:gpuwatch@localhost:4442/gpuwatch_test",
)
# TEST_CACHE=memory runs the whole suite with no Redis at all.
TEST_CACHE = os.environ.get("TEST_CACHE", "redis")
TEST_REDIS = os.environ.get("TEST_REDIS_URL", "redis://localhost:4479/15")
SMTP_PORT = int(os.environ.get("TEST_SMTP_PORT", "4426"))
MAILPIT_API = os.environ.get("TEST_MAILPIT_API", "http://localhost:4425/api/v1")
OWNER = {"email": "owner@example.test", "password": "Owner-Pass-123"}

BUILTIN_RULES = """
INSERT INTO alert_rules (id, name, kind, metric, operator, threshold, duration_s, severity,
                         channel_ids, notify_resolved, enabled)
VALUES
  (gen_random_uuid(), 'Agent offline', 'agent_offline', NULL, NULL, NULL, 0, 'critical', '[]', true, true),
  (gen_random_uuid(), 'GPU lost', 'gpu_lost', NULL, NULL, NULL, 0, 'critical', '[]', true, true),
  (gen_random_uuid(), 'GPU too hot', 'threshold', 'temp_c', 'gt', 85, 120, 'warning', '[]', true, true),
  (gen_random_uuid(), 'GPU memory almost full', 'threshold', 'mem_used_pct', 'gt', 95, 300, 'warning', '[]', true, true)
"""


def _guard(url: str) -> None:
    parsed = urlparse(url.replace("+asyncpg", ""))
    if "test" not in (parsed.path or ""):
        raise RuntimeError(
            f"refusing to run against {parsed.path!r}: database name must contain 'test'"
        )
    if (
        parsed.hostname not in ("localhost", "127.0.0.1", "postgres")
        and os.environ.get("ALLOW_REMOTE_TEST_DB") != "true"
    ):
        raise RuntimeError("refusing a non-local test database (set ALLOW_REMOTE_TEST_DB=true)")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
async def database() -> AsyncIterator[str]:
    _guard(TEST_DB)
    admin_url = TEST_DB.rsplit("/", 1)[0] + "/postgres"
    name = TEST_DB.rsplit("/", 1)[1]
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    await engine.dispose()
    from gpuwatch.migrations.runner import upgrade

    await asyncio.to_thread(upgrade, TEST_DB)
    yield TEST_DB


def make_settings(database: str, tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "test",
        "database_url": database,
        "redis_url": TEST_REDIS if TEST_CACHE == "redis" else "",
        "session_secret": "test-only-session-secret-with-32-plus-bytes",
        "api_key_pepper": "test-only-api-key-pepper-with-32-plus-bytes",
        "local_master_key": "test-only-master-key-with-32-plus-bytes-ok",
        "local_storage_dir": str(tmp_path / "reports"),
        "mail_mode": os.environ.get("TEST_MAIL_MODE", "smtp"),
        "smtp_host": "localhost",
        "smtp_port": SMTP_PORT,
        # gpuwatch.local is the SES identity the local-floci Terraform verifies.
        "mail_from": "GPUWatch Tests <alerts@gpuwatch.local>",
        "dashboard_url": "http://dashboard.test",
        "rollup_lag_s": 60,
        # The option matrix (make test-matrix) reruns the suite against Floci KMS, S3 and SES.
        "key_mode": os.environ.get("TEST_KEY_MODE", "local"),
        "storage": os.environ.get("TEST_STORAGE", "local"),
        "aws_endpoint_url": os.environ.get("TEST_AWS_ENDPOINT"),
        "s3_force_path_style": True,
        "kms_key_id": os.environ.get("TEST_KMS_KEY_ID", "alias/gpuwatch-local"),
        "reports_bucket": os.environ.get("TEST_REPORTS_BUCKET", "gpuwatch-local-reports"),
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def settings(database: str, tmp_path: Path) -> Settings:
    return make_settings(database, tmp_path)


async def reset(settings: Settings) -> None:
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        tables = (
            (
                await conn.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                        "AND tablename <> 'alembic_version'"
                    )
                )
            )
            .scalars()
            .all()
        )
        await conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
        await conn.execute(text(BUILTIN_RULES))
    await engine.dispose()
    if settings.redis_url:
        from redis.asyncio import Redis

        redis = Redis.from_url(settings.redis_url)
        await redis.flushdb()
        await redis.aclose()


async def bootstrap_owner(settings: Settings) -> None:
    from gpuwatch.core.db import Database
    from gpuwatch.core.security import hash_password
    from gpuwatch.users.models import User

    db = Database(settings.database_url, pool_size=1, max_overflow=0)
    async with db.sessionmaker() as session:
        session.add(
            User(
                email=OWNER["email"],
                name="Owner",
                role="owner",
                password_hash=hash_password(OWNER["password"]),
            )
        )
        await session.commit()
    await db.dispose()


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    await reset(settings)
    await bootstrap_owner(settings)
    application = create_app(settings)
    async with LifespanManager(application, startup_timeout=60, shutdown_timeout=30):
        yield application


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver", timeout=30
    )


async def login(app: FastAPI, creds: dict[str, str] = OWNER) -> httpx.AsyncClient:
    client = client_for(app)
    resp = await client.post("/api/v1/auth/login", json=creds)
    assert resp.status_code == 200, resp.text
    client.headers["authorization"] = f"Bearer {resp.json()['session_token']}"
    return client


# ── batch builders ───────────────────────────────────────────────────────────


def now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def gpu(
    uuid_: str, index: int = 0, name: str = "NVIDIA A100-SXM4-80GB", mem: float = 81_920.0
) -> dict[str, Any]:
    return {
        "uuid": uuid_,
        "index": index,
        "name": name,
        "memory_total_mib": mem,
        "power_limit_w": 400.0,
    }


def sample(uuid_: str, ts: datetime, interval: float = 5.0, **metrics: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "gpu_uuid": uuid_,
        "ts": ts.isoformat(),
        "interval_s": interval,
        "util_gpu": 50.0,
        "mem_used_mib": 20_000.0,
        "mem_total_mib": 81_920.0,
        "temp_c": 60.0,
        "power_w": 200.0,
        "power_limit_w": 400.0,
        "procs": 0,
    }
    base.update(metrics)
    return base


def process(uuid_: str, ts: datetime, pid: int, name: str, **extra: Any) -> dict[str, Any]:
    return {"gpu_uuid": uuid_, "ts": ts.isoformat(), "pid": pid, "name": name, **extra}


def batch(
    gpus: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    processes: list[dict[str, Any]] | None = None,
    inference: list[dict[str, Any]] | None = None,
    *,
    batch_id: str | None = None,
    status: str = "ok",
    problems: list[dict[str, str]] | None = None,
    interval: float = 5.0,
    hostname: str = "gpu-node-1",
) -> dict[str, Any]:
    return {
        "batch_id": batch_id or str(uuid.uuid4()),
        "agent": {
            "version": "0.1.0",
            "collector": "nvml",
            "hostname": hostname,
            "driver_version": "550.127.05",
            "cuda_version": "12.4",
            "interval_s": interval,
            "status": status,
            "problems": problems or [],
        },
        "gpus": gpus,
        "samples": samples,
        "processes": processes or [],
        "inference": inference or [],
    }


@dataclass
class Host:
    """An enrolled agent host: sends batches with its host token."""

    app: FastAPI
    token: str
    host_id: str
    uuids: list[str] = field(default_factory=list)

    async def send(self, body: dict[str, Any]) -> httpx.Response:
        async with client_for(self.app) as c:
            return await c.post(
                "/ingest/v1/batches", json=body, headers={"authorization": f"Bearer {self.token}"}
            )

    async def ok(self, body: dict[str, Any]) -> dict[str, Any]:
        r = await self.send(body)
        assert r.status_code == 200, r.text
        data: dict[str, Any] = r.json()
        return data


@dataclass
class Api:
    """A signed-in owner client plus helpers for common setup and worker jobs."""

    client: httpx.AsyncClient
    app: FastAPI

    def anonymous(self) -> httpx.AsyncClient:
        return client_for(self.app)

    @property
    def container(self) -> Container:
        c: Container = self.app.state.container
        return c

    async def ok(self, method: str, path: str, json: Any = None, status: int | None = None) -> Any:
        resp = await self.client.request(method, path, json=json)
        expected = status or (201 if method == "POST" and resp.status_code == 201 else 200)
        assert resp.status_code == expected, f"{method} {path}: {resp.status_code} {resp.text}"
        return resp.json() if resp.content else None

    async def enrolment_token(self, *, simulated: bool = False, **body: Any) -> str:
        if simulated:
            from gpuwatch.fleet import service
            from gpuwatch.fleet.schemas import EnrolmentTokenIn

            async with self.container.db.sessionmaker() as session:
                created = await service.create_token(
                    session,
                    EnrolmentTokenIn(name=body.get("name", "sim")),
                    self.container.settings.api_key_pepper,
                    None,
                    simulated=True,
                )
            return created.token
        created = await self.ok("POST", "/api/v1/enrolment-tokens", {"name": "tests", **body})
        return str(created["token"])

    async def host(
        self,
        *,
        simulated: bool = False,
        machine: str | None = None,
        hostname: str = "gpu-node-1",
        labels: dict[str, str] | None = None,
        gpus: int = 1,
    ) -> Host:
        token = await self.enrolment_token(simulated=simulated)
        async with client_for(self.app) as c:
            r = await c.post(
                "/ingest/v1/enroll",
                json={
                    "token": token,
                    "machine_id": machine or f"machine-{uuid.uuid4().hex[:12]}",
                    "hostname": hostname,
                    "labels": labels or {},
                },
            )
        assert r.status_code == 201, r.text
        body = r.json()
        return Host(
            self.app,
            body["host_token"],
            body["host_id"],
            [f"GPU-{uuid.uuid4()}" for _ in range(gpus)],
        )

    async def gpu_id(self, gpu_uuid: str) -> str:
        for g in await self.ok("GET", "/api/v1/gpus?include_retired=true"):
            if g["uuid"] == gpu_uuid:
                return str(g["id"])
        raise AssertionError(f"GPU {gpu_uuid} not found")

    async def rollup(self, at: datetime | None = None) -> None:
        from gpuwatch.telemetry import rollups

        await rollups.tick(self.container, (at or now()) + timedelta(minutes=5))

    async def evaluate_alerts(self, at: datetime | None = None) -> None:
        from gpuwatch.alerts import evaluator

        await evaluator.evaluate(self.container, at)

    async def deliver(self, at: datetime | None = None) -> int:
        from gpuwatch.alerts import notifier

        return await notifier.deliver_pending(self.container, at)

    async def insights(self, at: datetime | None = None) -> int:
        from gpuwatch.insights import service

        return await service.evaluate(self.container, at)

    async def set_rate(self, model: str, usd: str) -> None:
        await self.ok(
            "POST", "/api/v1/rates", {"scope": "model", "gpu_model": model, "usd_per_hour": usd}
        )

    async def sql(self, statement: str, **params: Any) -> Any:
        async with self.container.db.engine.begin() as conn:
            result = await conn.execute(text(statement), params)
            return result.all() if result.returns_rows else None


@pytest.fixture
async def api(app: FastAPI) -> AsyncIterator[Api]:
    client = await login(app)
    try:
        yield Api(client, app)
    finally:
        await client.aclose()


# ── webhook receiver and Mailpit ─────────────────────────────────────────────


@dataclass
class Received:
    path: str
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


class WebhookReceiver:
    def __init__(self) -> None:
        self.received: list[Received] = []
        self.status = 200
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("content-length", "0"))
                receiver.received.append(
                    Received(
                        self.path,
                        {k.lower(): v for k, v in self.headers.items()},
                        self.rfile.read(length),
                    )
                )
                self.send_response(receiver.status)
                self.end_headers()

            def log_message(self, *_: object) -> None:
                return None

        self.server = ThreadingHTTPServer(("127.0.0.1", free_port()), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/hook"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()


@pytest.fixture
def webhook() -> Iterator[WebhookReceiver]:
    receiver = WebhookReceiver()
    yield receiver
    receiver.close()


class Mailpit:
    async def clear(self) -> None:
        async with httpx.AsyncClient() as c:
            await c.delete(f"{MAILPIT_API}/messages")

    async def messages(self, to: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient() as c:
            data = (await c.get(f"{MAILPIT_API}/search", params={"query": f"to:{to}"})).json()
        return list(data.get("messages", []))


@pytest.fixture
async def mailpit() -> Mailpit:
    box = Mailpit()
    await box.clear()
    return box


# ── a real HTTP server (server-sent events, the real agent) ──────────────────


@dataclass
class LiveServer:
    url: str
    app: FastAPI


@pytest.fixture
async def live_server(settings: Settings) -> AsyncIterator[LiveServer]:
    import time

    import uvicorn

    await reset(settings)
    await bootstrap_owner(settings)
    application = create_app(settings)
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(application, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            ok = await asyncio.to_thread(lambda: httpx.get(f"{url}/healthz", timeout=1))
            if ok.status_code == 200:
                break
        except httpx.HTTPError:
            await asyncio.sleep(0.1)
    try:
        yield LiveServer(url, application)
    finally:
        server.should_exit = True
        await asyncio.to_thread(thread.join, 10)
