"""Alert rules, scoping, channels, the outbox and webhook safety."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from gpuwatch.alerts.notifier import MAX_ATTEMPTS
from tests.integration.conftest import Api, WebhookReceiver, batch, gpu, now, sample

pytestmark = pytest.mark.integration


async def test_builtin_rules_exist_and_describe_themselves(api: Api) -> None:
    rules = {r["name"]: r for r in await api.ok("GET", "/api/v1/alerts/rules")}
    assert set(rules) == {"Agent offline", "GPU lost", "GPU too hot", "GPU memory almost full"}
    assert rules["GPU too hot"]["description"] == "Temperature above 85°C for 2 min"


async def test_rule_validation(api: Api) -> None:
    incomplete = await api.client.post(
        "/api/v1/alerts/rules", json={"name": "x", "metric": "temp_c"}
    )
    assert incomplete.status_code == 422
    unknown = await api.client.post(
        "/api/v1/alerts/rules",
        json={
            "name": "x",
            "metric": "temp_c",
            "operator": "gt",
            "threshold": 1,
            "channel_ids": ["00000000-0000-0000-0000-000000000000"],
        },
    )
    assert unknown.status_code == 404
    offline = await api.ok(
        "POST",
        "/api/v1/alerts/rules",
        {"name": "Offline", "kind": "agent_offline", "metric": "temp_c", "threshold": 5},
    )
    assert offline["metric"] is None and offline["threshold"] is None


async def test_rules_respect_their_scope_label(api: Api) -> None:
    await api.ok(
        "POST",
        "/api/v1/alerts/rules",
        {
            "name": "Busy prod",
            "metric": "util_gpu",
            "operator": "gt",
            "threshold": 90,
            "duration_s": 0,
            "scope_label": "env=prod",
        },
    )
    prod = await api.host(labels={"env": "prod"}, hostname="prod")
    dev = await api.host(labels={"env": "dev"}, hostname="dev")
    for h, name in ((prod, "prod"), (dev, "dev")):
        await h.ok(
            batch([gpu(h.uuids[0])], [sample(h.uuids[0], now(), util_gpu=99.0)], hostname=name)
        )
    await api.evaluate_alerts()
    events = [
        e
        for e in await api.ok("GET", "/api/v1/alerts/events?firing=true")
        if e["rule_name"] == "Busy prod"
    ]
    assert len(events) == 1 and events[0]["host_name"] == "prod"


async def test_a_metric_the_gpu_does_not_report_never_fires(api: Api) -> None:
    await api.ok(
        "POST",
        "/api/v1/alerts/rules",
        {"name": "Fan", "metric": "fan_pct", "operator": "lt", "threshold": 10, "duration_s": 0},
    )
    host = await api.host()
    await host.ok(batch([gpu(host.uuids[0])], [sample(host.uuids[0], now(), fan_pct=None)]))
    await api.evaluate_alerts()
    assert not [e for e in await api.ok("GET", "/api/v1/alerts/events") if e["rule_name"] == "Fan"]


async def test_a_short_breach_does_not_fire_a_long_rule(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    t = now()
    await host.ok(
        batch([gpu(u)], [sample(u, t - timedelta(seconds=s), temp_c=99.0) for s in range(0, 40, 5)])
    )
    await api.evaluate_alerts()  # GPU too hot needs 120 s
    assert not [
        e for e in await api.ok("GET", "/api/v1/alerts/events") if e["rule_name"] == "GPU too hot"
    ]


async def test_disabling_a_rule_resolves_its_events(api: Api) -> None:
    rule = await api.ok(
        "POST",
        "/api/v1/alerts/rules",
        {"name": "Hot now", "metric": "temp_c", "operator": "gt", "threshold": 50, "duration_s": 0},
    )
    host = await api.host()
    await host.ok(batch([gpu(host.uuids[0])], [sample(host.uuids[0], now(), temp_c=70.0)]))
    await api.evaluate_alerts()
    await api.ok(
        "PUT",
        f"/api/v1/alerts/rules/{rule['id']}",
        {
            **{k: rule[k] for k in ("name", "metric", "operator", "threshold", "duration_s")},
            "enabled": False,
        },
    )
    await api.evaluate_alerts()
    events = [
        e for e in await api.ok("GET", "/api/v1/alerts/events") if e["rule_name"] == "Hot now"
    ]
    assert len(events) == 1 and events[0]["resolved_at"] is not None
    await api.ok("DELETE", f"/api/v1/alerts/rules/{rule['id']}")
    assert all(r["name"] != "Hot now" for r in await api.ok("GET", "/api/v1/alerts/rules"))


async def test_webhooks_cannot_target_metadata_or_odd_schemes(api: Api) -> None:
    for url in (
        "http://169.254.169.254/latest/meta-data",
        "ftp://example.test/x",
        "http:///nohost",
    ):
        r = await api.client.post(
            "/api/v1/alerts/channels", json={"name": f"bad {url}", "kind": "webhook", "url": url}
        )
        assert r.status_code == 400 and r.json()["error"]["code"] == "webhook_url_blocked", url
    api.container.settings.webhook_allow_private = False
    try:
        r = await api.client.post(
            "/api/v1/alerts/channels",
            json={"name": "local", "kind": "webhook", "url": "http://127.0.0.1:9/x"},
        )
        assert r.status_code == 400
    finally:
        api.container.settings.webhook_allow_private = True


async def test_channel_crud_and_secret_handling(api: Api, webhook: WebhookReceiver) -> None:
    created = await api.ok(
        "POST",
        "/api/v1/alerts/channels",
        {"name": "Hook", "kind": "webhook", "url": webhook.url, "secret": "abc-123-secret"},
    )
    dup = await api.client.post(
        "/api/v1/alerts/channels",
        json={"name": "Hook", "kind": "email", "emails": ["a@example.test"]},
    )
    assert dup.status_code == 409
    kept = await api.ok(
        "PUT",
        f"/api/v1/alerts/channels/{created['id']}",
        {"name": "Hook", "kind": "webhook", "url": webhook.url},
    )
    assert kept["signed"] is True  # omitted secret: unchanged
    cleared = await api.ok(
        "PUT",
        f"/api/v1/alerts/channels/{created['id']}",
        {"name": "Hook", "kind": "webhook", "url": webhook.url, "secret": ""},
    )
    assert cleared["signed"] is False
    bad = await api.client.post(
        "/api/v1/alerts/channels", json={"name": "E", "kind": "email", "emails": []}
    )
    assert bad.status_code == 422
    rule = await api.ok(
        "POST",
        "/api/v1/alerts/rules",
        {
            "name": "R",
            "metric": "temp_c",
            "operator": "gt",
            "threshold": 1,
            "channel_ids": [created["id"]],
        },
    )
    await api.ok("DELETE", f"/api/v1/alerts/channels/{created['id']}")
    rules = {r["id"]: r for r in await api.ok("GET", "/api/v1/alerts/rules")}
    assert rules[rule["id"]]["channel_ids"] == []


async def test_failed_deliveries_back_off_then_fail_visibly(
    api: Api, webhook: WebhookReceiver
) -> None:
    webhook.status = 500
    channel = await api.ok(
        "POST", "/api/v1/alerts/channels", {"name": "Flaky", "kind": "webhook", "url": webhook.url}
    )
    await api.ok("POST", f"/api/v1/alerts/channels/{channel['id']}/test")
    t = datetime.now(UTC)
    assert await api.deliver(t) == 1
    assert await api.deliver(t) == 0  # backing off
    notes = await api.ok("GET", "/api/v1/alerts/notifications")
    assert (
        notes[0]["attempts"] == 1
        and "500" in notes[0]["last_error"]
        and notes[0]["failed_at"] is None
    )
    for i in range(MAX_ATTEMPTS):
        await api.deliver(t + timedelta(hours=i + 1))
    note = (await api.ok("GET", "/api/v1/alerts/notifications"))[0]
    assert note["failed_at"] is not None and note["attempts"] == MAX_ATTEMPTS
    assert (await api.ok("GET", "/api/v1/alerts/channels"))[0]["last_error"]
    webhook.status = 200
    await api.ok("POST", f"/api/v1/alerts/channels/{channel['id']}/test")
    assert await api.deliver(t + timedelta(days=1)) == 1
    assert (await api.ok("GET", "/api/v1/alerts/channels"))[0]["last_error"] is None


async def test_disabled_channels_cannot_be_tested(api: Api) -> None:
    channel = await api.ok(
        "POST",
        "/api/v1/alerts/channels",
        {"name": "Off", "kind": "email", "emails": ["a@example.test"], "enabled": False},
    )
    r = await api.client.post(f"/api/v1/alerts/channels/{channel['id']}/test")
    assert r.status_code == 400 and r.json()["error"]["code"] == "channel_disabled"


async def test_a_retired_gpu_resolves_its_lost_alert(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    await host.ok(batch([gpu(u)], [sample(u, now())]))
    await api.sql("UPDATE gpus SET last_seen_at = now() - interval '5 minutes'")
    await api.evaluate_alerts()
    gid = await api.gpu_id(u)
    await api.ok("PATCH", f"/api/v1/gpus/{gid}", {"retired": True})
    await api.evaluate_alerts()
    lost = [e for e in await api.ok("GET", "/api/v1/alerts/events") if e["kind"] == "gpu_lost"]
    assert len(lost) == 1 and lost[0]["resolved_at"] is not None


async def test_viewers_and_keys_see_where_a_webhook_goes_not_its_secret_url(api: Api) -> None:
    url = "http://127.0.0.1:9/services/T000/B000/secret-path-token"
    created = await api.ok(
        "POST", "/api/v1/alerts/channels", {"name": "Chat", "kind": "webhook", "url": url}
    )
    assert created["url"] == url  # the admin who set it sees it
    key = (await api.ok("POST", "/api/v1/keys", {"name": "reader"}))["key"]
    async with api.anonymous() as c:
        r = await c.get("/api/v1/alerts/channels", headers={"authorization": f"Bearer {key}"})
    assert r.status_code == 200
    seen = next(ch for ch in r.json() if ch["name"] == "Chat")
    assert seen["url"] == "http://127.0.0.1:9/..."
    assert all("secret-path-token" not in str(ch) for ch in r.json())
