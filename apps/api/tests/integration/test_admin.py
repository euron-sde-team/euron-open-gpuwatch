"""Dashboard platform: sign-in, sessions, roles, API keys, users, audit, system info."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.integration.conftest import OWNER, Api, batch, gpu, login, now, sample

pytestmark = pytest.mark.integration


async def test_login_failures_and_lockout(api: Api) -> None:
    async with api.anonymous() as c:
        bad = await c.post(
            "/api/v1/auth/login", json={"email": OWNER["email"], "password": "wrong"}
        )
        assert bad.status_code == 401
        for _ in range(5):
            await c.post("/api/v1/auth/login", json={"email": OWNER["email"], "password": "wrong"})
        locked = await c.post("/api/v1/auth/login", json=OWNER)
        assert locked.status_code == 401 and locked.json()["error"]["code"] == "account_locked"
        assert (await c.get("/api/v1/auth/me")).status_code == 401


async def test_cookie_session_requires_csrf_header(api: Api) -> None:
    async with api.anonymous() as c:
        await c.post("/api/v1/auth/login", json=OWNER)
        assert (await c.get("/api/v1/auth/me")).status_code == 200
        resp = await c.post("/api/v1/keys", json={"name": "x"})
        assert resp.status_code == 403 and resp.json()["error"]["code"] == "csrf_required"
        ok = await c.post("/api/v1/keys", json={"name": "x"}, headers={"x-gpuwatch-csrf": "1"})
        assert ok.status_code == 201


async def test_roles_are_enforced(api: Api) -> None:
    await api.ok(
        "POST",
        "/api/v1/users",
        {
            "email": "viewer@example.test",
            "name": "V",
            "password": "Viewer-Pass-123",
            "role": "viewer",
        },
    )
    viewer = await login(api.app, {"email": "viewer@example.test", "password": "Viewer-Pass-123"})
    try:
        for path in (
            "/api/v1/hosts",
            "/api/v1/gpus",
            "/api/v1/costs",
            "/api/v1/insights",
            "/api/v1/alerts/rules",
        ):
            assert (await viewer.get(path)).status_code == 200, path
        for method, path, body in (
            ("POST", "/api/v1/keys", {"name": "x"}),
            ("POST", "/api/v1/enrolment-tokens", {"name": "x"}),
            ("POST", "/api/v1/rates", {"scope": "model", "gpu_model": "X", "usd_per_hour": "1"}),
            (
                "POST",
                "/api/v1/alerts/rules",
                {"name": "x", "metric": "temp_c", "operator": "gt", "threshold": 1},
            ),
            ("PUT", "/api/v1/settings/insights", {}),
            ("GET", "/api/v1/audit", None),
            ("GET", "/api/v1/enrolment-tokens", None),
        ):
            r = await viewer.request(method, path, json=body)
            assert r.status_code == 403, (method, path, r.text)
    finally:
        await viewer.aclose()


async def test_api_keys_read_but_never_write(api: Api) -> None:
    created = await api.ok("POST", "/api/v1/keys", {"name": "grafana"})
    assert created["key"].startswith("gwk_") and created["display"].endswith("_****")
    headers = {"authorization": f"Bearer {created['key']}"}
    async with api.anonymous() as c:
        assert (await c.get("/api/v1/gpus", headers=headers)).status_code == 200
        assert (await c.get("/api/v1/costs", headers=headers)).status_code == 200
        r = await c.post(
            "/api/v1/rates",
            json={"scope": "model", "gpu_model": "X", "usd_per_hour": "1"},
            headers=headers,
        )
        assert r.status_code == 403 and r.json()["error"]["code"] == "read_only_key"
        assert (await c.get("/api/v1/audit", headers=headers)).status_code == 403  # admin only
    await api.ok("POST", f"/api/v1/keys/{created['id']}/revoke")
    async with api.anonymous() as c:
        r = await c.get("/api/v1/gpus", headers=headers)
        assert r.status_code == 401 and r.json()["error"]["code"] == "revoked_api_key"
        bad = await c.get("/api/v1/gpus", headers={"authorization": "Bearer gwk_000000000000_nope"})
        assert bad.status_code == 401


async def test_api_key_rate_limit(api: Api) -> None:
    key = (await api.ok("POST", "/api/v1/keys", {"name": "tiny", "rpm_limit": 3}))["key"]
    async with api.anonymous() as c:
        codes = [
            (await c.get("/api/v1/hosts", headers={"authorization": f"Bearer {key}"})).status_code
            for _ in range(4)
        ]
    assert codes == [200, 200, 200, 429]


async def test_users_keep_an_owner(api: Api) -> None:
    me = await api.ok("GET", "/api/v1/auth/me")
    resp = await api.client.patch(f"/api/v1/users/{me['id']}", json={"role": "viewer"})
    assert resp.status_code == 403
    assert len(await api.ok("GET", "/api/v1/users")) == 1


async def test_password_change_ends_other_sessions(api: Api) -> None:
    other = await login(api.app)
    try:
        await api.ok(
            "POST",
            "/api/v1/auth/password",
            {"current_password": OWNER["password"], "new_password": "Changed-Pass-456"},
        )
        assert (await other.get("/api/v1/auth/me")).status_code == 401
    finally:
        await other.aclose()


async def test_audit_log_records_changes_and_is_append_only(api: Api) -> None:
    await api.ok("POST", "/api/v1/keys", {"name": "audited"})
    await api.enrolment_token()
    actions = {e["action"] for e in (await api.ok("GET", "/api/v1/audit"))["items"]}
    assert {"auth.login", "api_key.created", "enrolment_token.created"} <= actions
    async with api.container.db.engine.begin() as conn:
        with pytest.raises(Exception, match="append-only"):
            await conn.execute(text("UPDATE audit_log SET action = 'x'"))


async def test_system_info_health_and_metrics(api: Api) -> None:
    host = await api.host()
    await host.ok(batch([gpu(host.uuids[0])], [sample(host.uuids[0], now())]))
    info = await api.ok("GET", "/api/v1/system")
    assert info["cache_backend"] in ("redis", "memory")
    assert info["raw_retention_days"] == 7
    async with api.anonymous() as c:
        assert (await c.get("/healthz")).json() == {"status": "ok"}
        assert (await c.get("/health")).status_code == 200
        ready = await c.get("/readyz")
        assert ready.status_code == 200 and ready.json()["status"] == "ready"
        metrics = (await c.get("/metrics")).text
        assert "gpuwatch_ingest_batches_total" in metrics
        assert 'gpuwatch_gpu_up{host="gpu-node-1"' in metrics


async def test_metrics_token_protects_the_fleet_exposition(api: Api) -> None:
    api.container.settings.metrics_token = "scrape-secret-123"
    try:
        async with api.anonymous() as c:
            assert (await c.get("/metrics")).status_code == 401
            ok = await c.get("/metrics", headers={"authorization": "Bearer scrape-secret-123"})
            assert ok.status_code == 200
    finally:
        api.container.settings.metrics_token = None
