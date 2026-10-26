"""Abuse and race cases: hostile input, forged headers, parallel requests, evicted caches.

Each test pins one production-readiness guarantee: bounded work per request, no 500s on odd
but valid JSON, agents that cannot write outside their host, and state that stays correct
under concurrency.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from gpuwatch.audit.models import AuditLog
from gpuwatch.users.models import User
from tests.integration.conftest import OWNER, Api, batch, gpu, login, now, sample

pytestmark = pytest.mark.integration


async def test_lone_surrogate_is_a_422_not_a_500(api: Api) -> None:
    host = await api.host()
    raw = (
        b'{"batch_id": "6f1c3c3e-2b7a-4c1e-9d55-1f0e2a7b9c11", "agent": {"version": "1", '
        b'"collector": "nvml", "hostname": "bad \\ud800 host", "interval_s": 5}}'
    )
    async with api.anonymous() as c:
        r = await c.post(
            "/ingest/v1/batches",
            content=raw,
            headers={"authorization": f"Bearer {host.token}", "content-type": "application/json"},
        )
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_json"


async def test_chunked_bodies_obey_the_body_limit(api: Api) -> None:
    host = await api.host()
    settings = api.container.settings
    settings.max_body_bytes = 2000

    async def chunks() -> AsyncIterator[bytes]:
        yield b'{"batch_id": "6f1c3c3e-2b7a-4c1e-9d55-1f0e2a7b9c11", "agent": {"hostname": "'
        for _ in range(20):
            yield b"x" * 500
        yield b'"}}'

    try:
        async with api.anonymous() as c:
            r = await c.post(
                "/ingest/v1/batches",
                content=chunks(),
                headers={
                    "authorization": f"Bearer {host.token}",
                    "content-type": "application/json",
                },
            )
        assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"
    finally:
        settings.max_body_bytes = 8_000_000


async def test_a_batch_over_the_row_limit_is_refused_whole(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    api.container.settings.ingest_max_samples = 100
    try:
        rows = [sample(u, now() - timedelta(seconds=i)) for i in range(101)]
        r = await host.send(batch([gpu(u)], rows))
        assert r.status_code == 400 and r.json()["error"]["code"] == "batch_too_large"
    finally:
        api.container.settings.ingest_max_samples = 20_000


async def test_impossible_readings_are_stored_as_not_available_and_never_stall_rollups(
    api: Api,
) -> None:
    host = await api.host()
    u = host.uuids[0]
    t0 = now() - timedelta(minutes=5)
    odd = {"util_gpu": 150.0, "temp_c": 9999.0, "mem_used_mib": -1.0, "power_w": 1.7e308}
    reply = await host.ok(
        batch([gpu(u)], [sample(u, t0, **odd), sample(u, t0 + timedelta(seconds=5))])
    )
    assert reply["samples"] == 2  # the batch is kept; only the impossible values are dropped
    g = (await api.ok("GET", "/api/v1/gpus"))[0]
    series = await api.ok("GET", f"/api/v1/gpus/{g['id']}/metrics?resolution=raw")
    first = series["points"][0]
    assert (first["util"], first["temp_c"], first["mem_used_mib"], first["power_w"]) == (
        None,
        None,
        None,
        None,
    )
    # A float8 overflow in the energy sum would fail every rollup tick from here on.
    await api.rollup()
    # Structural errors still refuse the batch.
    for bad in ({"interval_s": 0},):
        r = await host.send(batch([gpu(u)], [sample(u, now(), **bad)]))
        assert r.status_code == 422, bad


async def test_an_agent_cannot_write_into_another_hosts_gpu(api: Api) -> None:
    a = await api.host(hostname="a")
    b = await api.host(hostname="b")
    await a.ok(batch([gpu(a.uuids[0])], [sample(a.uuids[0], now())], hostname="a"))
    # Host b reports samples for a's GPU without declaring it: dropped.
    reply = await b.ok(batch([], [sample(a.uuids[0], now() + timedelta(seconds=1))], hostname="b"))
    assert reply["samples"] == 0 and reply["dropped"] == 1


async def test_ingest_is_rate_limited_per_host(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    api.container.settings.ingest_rpm_per_host = 10
    try:
        codes = []
        for i in range(12):
            r = await host.send(batch([gpu(u)], [sample(u, now() - timedelta(seconds=i))]))
            codes.append(r.status_code)
        assert codes[:10] == [200] * 10 and codes[-1] == 429
    finally:
        api.container.settings.ingest_rpm_per_host = 240


async def test_forwarded_for_cannot_dodge_the_login_throttle(api: Api) -> None:
    async with api.anonymous() as c:
        codes = []
        for i in range(22):
            r = await c.post(
                "/api/v1/auth/login",
                json={"email": "nobody@example.test", "password": "wrong-password"},
                headers={"x-forwarded-for": f"203.0.113.{i}"},
            )
            codes.append(r.status_code)
    assert codes[-1] == 429


async def test_parallel_wrong_passwords_still_lock_the_account(api: Api) -> None:
    async with api.anonymous() as c:
        await asyncio.gather(
            *(
                c.post("/api/v1/auth/login", json={"email": OWNER["email"], "password": "nope"})
                for _ in range(8)
            )
        )
        locked = await c.post("/api/v1/auth/login", json=OWNER)
    assert locked.json()["error"]["code"] == "account_locked"
    async with api.container.db.sessionmaker() as s:
        failures = await s.scalar(
            select(func.count()).where(AuditLog.action == "auth.login_failed")
        )
    assert failures == 8


async def test_logout_ends_the_session_server_side(api: Api) -> None:
    client = await login(api.app)
    try:
        assert (await client.get("/api/v1/auth/me")).status_code == 200
        assert (await client.post("/api/v1/auth/logout")).status_code == 200
        again = await client.get("/api/v1/auth/me")
        assert again.status_code == 401 and again.json()["error"]["code"] == "session_expired"
    finally:
        await client.aclose()
    assert (await api.client.get("/api/v1/auth/me")).status_code == 200


async def test_signed_out_session_survives_cache_eviction(api: Api) -> None:
    client = await login(api.app)
    try:
        await client.post("/api/v1/auth/logout")
        kv = api.container.kv
        for i in range(3000):
            await kv.set(f"filler:{i}", b"x" * 100, 60)
        if hasattr(kv, "redis"):
            await kv.redis.flushdb()
        assert (await client.get("/api/v1/auth/me")).status_code == 401
    finally:
        await client.aclose()


async def test_login_response_is_not_cached(api: Api) -> None:
    async with api.anonymous() as c:
        resp = await c.post("/api/v1/auth/login", json=OWNER)
    assert resp.headers["cache-control"] == "no-store"


async def test_two_owners_demoting_each_other_keep_an_owner(api: Api) -> None:
    other = {"email": "second-owner@example.test", "password": "Second-Owner-123"}
    created = await api.ok(
        "POST", "/api/v1/users", {"name": "Second", "role": "owner", **other}, status=201
    )
    me = await api.ok("GET", "/api/v1/auth/me")
    second = await login(api.app, other)
    try:
        results = await asyncio.gather(
            api.client.patch(f"/api/v1/users/{created['id']}", json={"role": "viewer"}),
            second.patch(f"/api/v1/users/{me['id']}", json={"role": "viewer"}),
        )
    finally:
        await second.aclose()
    assert sorted(r.status_code for r in results)[0] == 200
    async with api.container.db.sessionmaker() as s:
        owners = await s.scalar(
            select(func.count()).where(User.role == "owner", User.disabled.is_(False))
        )
    assert owners == 1


async def test_racing_user_creates_conflict_without_leaking_hashes(
    api: Api, caplog: pytest.LogCaptureFixture
) -> None:
    body = {
        "email": "race@example.test",
        "name": "Race",
        "role": "viewer",
        "password": "Race-Pass-12345",
    }
    results = await asyncio.gather(*(api.client.post("/api/v1/users", json=body) for _ in range(4)))
    codes = sorted(r.status_code for r in results)
    assert codes[0] == 201 and set(codes[1:]) <= {409}
    assert "argon2" not in caplog.text


async def test_concurrent_batches_from_one_host_all_land(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    t = now()
    results = await asyncio.gather(
        *(host.send(batch([gpu(u)], [sample(u, t - timedelta(seconds=i))])) for i in range(10))
    )
    assert all(r.status_code == 200 for r in results)
    assert (await api.sql("SELECT count(*) FROM gpu_samples"))[0][0] == 10


async def test_concurrent_alert_evaluations_fire_once(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    t = now()
    await host.ok(
        batch(
            [gpu(u)], [sample(u, t - timedelta(seconds=s), temp_c=95.0) for s in range(0, 150, 5)]
        )
    )
    await asyncio.gather(*(api.evaluate_alerts() for _ in range(5)))
    hot = [
        e for e in await api.ok("GET", "/api/v1/alerts/events") if e["rule_name"] == "GPU too hot"
    ]
    assert len(hot) == 1


async def test_security_headers_on_every_response(api: Api) -> None:
    async with api.anonymous() as c:
        r = await c.get("/healthz")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "x-request-id" in r.headers
