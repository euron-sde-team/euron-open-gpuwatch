"""The acceptance criteria from docs/PLAN.md, one test (or a few) each.

GPUWatch's name is its contract: a watch keeps watching and raises its hand. These tests
prove it records what it can reach, tells unavailable from zero, notices idle spend and
slowdowns, accounts for every GPU-hour exactly, and alerts once per problem.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from gpuwatch.costs.rates import seconds_cost
from tests.integration.conftest import (
    Api,
    LiveServer,
    Mailpit,
    WebhookReceiver,
    batch,
    gpu,
    login,
    now,
    process,
    sample,
)

pytestmark = pytest.mark.integration
A100 = "NVIDIA A100-SXM4-80GB"


def _hour_floor(t):  # type: ignore[no-untyped-def]
    return t.replace(minute=0, second=0, microsecond=0)


# 1. Live: a sample reaches the dashboard's live view within 5 seconds.


async def test_1_a_sample_appears_in_the_live_snapshot(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    ts = now()
    await host.ok(batch([gpu(u)], [sample(u, ts, util_gpu=73.0)]))
    gpus = await api.ok("GET", "/api/v1/live")
    assert gpus[0]["status"] == "ok"
    assert gpus[0]["live"]["util_gpu"] == 73.0


async def test_1_the_live_stream_pushes_a_new_sample_within_5_seconds(
    live_server: LiveServer,
) -> None:
    async with httpx.AsyncClient(base_url=live_server.url, timeout=10) as c:
        token = (
            await c.post(
                "/api/v1/auth/login",
                json={"email": "owner@example.test", "password": "Owner-Pass-123"},
            )
        ).json()["session_token"]
        auth = {"authorization": f"Bearer {token}"}
        enrol_token = (
            await c.post("/api/v1/enrolment-tokens", json={"name": "t"}, headers=auth)
        ).json()["token"]
        enrolled = (
            await c.post(
                "/ingest/v1/enroll",
                json={"token": enrol_token, "machine_id": "live-test-1", "hostname": "n1"},
            )
        ).json()
        host_auth = {"authorization": f"Bearer {enrolled['host_token']}"}
        uuid_ = "GPU-live-0001"
        await c.post(
            "/ingest/v1/batches",
            json=batch([gpu(uuid_)], [sample(uuid_, now(), util_gpu=10.0)]),
            headers=host_auth,
        )
        async with c.stream("GET", "/api/v1/live/stream", headers=auth) as stream:
            # A compressing proxy would otherwise buffer the stream until it ends.
            assert "no-transform" in stream.headers["cache-control"]
            lines = stream.aiter_lines()
            first = await _next_snapshot(lines)
            assert first[0]["live"]["util_gpu"] == 10.0
            # An open stream holds no pooled connection between snapshots.
            pool = live_server.app.state.container.db.engine.sync_engine.pool
            assert pool.checkedout() == 0
            sent = time.monotonic()
            await c.post(
                "/ingest/v1/batches",
                json=batch(
                    [gpu(uuid_)], [sample(uuid_, now() + timedelta(seconds=1), util_gpu=88.0)]
                ),
                headers=host_auth,
            )
            while True:
                snap = await asyncio.wait_for(_next_snapshot(lines), timeout=5)
                if snap[0]["live"]["util_gpu"] == 88.0:
                    break
            assert time.monotonic() - sent < 5


async def _next_snapshot(lines):  # type: ignore[no-untyped-def]
    async for line in lines:
        if line.startswith("data: "):
            return json.loads(line[6:])
    raise AssertionError("stream ended")


# 2. Unavailable is not zero.


async def test_2_a_metric_the_driver_does_not_report_stays_null_everywhere(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    t0 = now() - timedelta(minutes=10)
    samples = [
        sample(
            u,
            t0 + timedelta(seconds=30 * i),
            interval=30,
            fan_pct=None,
            ecc_uncorrected=None,
            util_gpu=0.0,
        )
        for i in range(20)
    ]
    await host.ok(batch([gpu(u)], samples))
    g = (await api.ok("GET", "/api/v1/gpus"))[0]
    assert g["live"]["fan_pct"] is None
    assert g["live"]["util_gpu"] == 0.0  # a real zero stays zero
    series = await api.ok("GET", f"/api/v1/gpus/{g['id']}/metrics?resolution=raw")
    assert all(p["fan_pct"] is None for p in series["points"])
    assert "fan_pct" not in series["available"]
    assert "util" in series["available"]
    await api.rollup()
    minute = await api.ok(
        "GET",
        f"/api/v1/gpus/{g['id']}/metrics?resolution=1m&start={t0.isoformat().replace('+00:00', 'Z')}",
    )
    assert minute["points"] and all(p["fan_pct"] is None for p in minute["points"])
    exposition = (await api.client.get("/metrics")).text
    assert "gpuwatch_gpu_utilization_percent{" in exposition
    assert "gpuwatch_gpu_fan_percent{" not in exposition


# 3. Disconnected within 90 seconds, one alert, resolved on return.


async def test_3_a_silent_agent_is_disconnected_and_alerts_once(api: Api) -> None:
    settings = api.container.settings
    assert settings.host_offline_after_s + settings.alert_eval_interval_s <= 90
    host = await api.host(hostname="silent-node")
    u = host.uuids[0]
    await host.ok(batch([gpu(u)], [sample(u, now())], hostname="silent-node"))
    await api.sql(
        "UPDATE hosts SET last_seen_at = now() - interval '75 seconds' WHERE id = :id",
        id=host.host_id,
    )
    assert (await api.ok("GET", f"/api/v1/hosts/{host.host_id}"))["status"] == "disconnected"
    await api.evaluate_alerts()
    await api.evaluate_alerts()
    events = [
        e for e in await api.ok("GET", "/api/v1/alerts/events") if e["kind"] == "agent_offline"
    ]
    assert len(events) == 1 and events[0]["resolved_at"] is None
    assert "silent-node" in events[0]["message"]
    await host.ok(batch([gpu(u)], [sample(u, now())], hostname="silent-node"))
    await api.evaluate_alerts()
    events = [
        e for e in await api.ok("GET", "/api/v1/alerts/events") if e["kind"] == "agent_offline"
    ]
    assert len(events) == 1 and events[0]["resolved_at"] is not None


# 4. Idle spend: cost equals rate times idle hours.


async def test_4_a_loaded_but_idle_gpu_costs_rate_times_idle_hours(api: Api) -> None:
    await api.set_rate(A100, "2.50")
    host = await api.host()
    u = host.uuids[0]
    start = _hour_floor(now()) - timedelta(hours=3)
    samples, procs = [], []
    for i in range(120):  # two hours, one sample a minute, a model loaded, no work
        ts = start + timedelta(minutes=i)
        samples.append(sample(u, ts, interval=60, util_gpu=1.0, mem_used_mib=40_000.0, procs=1))
        procs.append(process(u, ts, 4242, "vllm", mem_used_mib=40_000.0, sm_util=0.0))
    await host.ok(batch([gpu(u)], samples, procs))
    await api.rollup(start + timedelta(hours=2))
    await api.insights(start + timedelta(hours=2, minutes=1))
    found = [i for i in await api.ok("GET", "/api/v1/insights") if i["kind"] == "idle_loaded"]
    assert len(found) == 1
    evidence = found[0]["evidence"]
    assert evidence["idle_seconds"] == 7200
    assert evidence["cost_nusd"] == seconds_cost(7200, 2_500_000_000) == 5_000_000_000
    assert "vllm" in found[0]["summary"]
    assert "$5.00" in found[0]["summary"]


# 5. Exact attribution: workloads plus idle equal the GPUs' cost, to the nano-dollar.


async def test_5_workload_costs_plus_idle_equal_gpu_cost_exactly(api: Api) -> None:
    await api.set_rate(A100, "1.234567")
    await api.ok(
        "POST",
        "/api/v1/workload-rules",
        {"workload": "training", "team": "Research", "process_pattern": "^python"},
    )
    host = await api.host(gpus=2)
    a, b = host.uuids
    start = _hour_floor(now()) - timedelta(hours=4)
    samples, procs = [], []
    for i in range(3 * 60 * 2):  # three hours at 30 s
        ts = start + timedelta(seconds=30 * i)
        busy = i % 7 != 0
        samples.append(sample(a, ts, interval=30, util_gpu=80.0 if busy else 2.0, procs=3))
        procs += [
            process(a, ts, 1, "python3", sm_util=37.0),
            process(a, ts, 2, "vllm", sm_util=29.0),
            process(a, ts, 3, "jupyter", sm_util=0.3),
        ]
        samples.append(sample(b, ts, interval=30, util_gpu=0.0, procs=0))
    await host.ok(batch([gpu(a, 0), gpu(b, 1)], samples, procs))
    await api.rollup(start + timedelta(hours=3))
    end = (start + timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    q = f"start={start.isoformat().replace('+00:00', 'Z')}&end={end}"
    by = {
        g: await api.ok("GET", f"/api/v1/costs?group_by={g}&{q}")
        for g in ("workload", "team", "host", "gpu", "model")
    }
    totals = {g: s["total_nusd"] for g, s in by.items()}
    assert len(set(totals.values())) == 1
    for s in by.values():
        assert sum(r["nusd"] for r in s["rows"]) == s["total_nusd"]
    # Independently: per GPU-hour, cost = round(seconds x rate / 3600).
    rows = await api.sql("SELECT gpu_id, bucket, sum(seconds) FROM workload_usage_1h GROUP BY 1, 2")
    expected = sum(seconds_cost(float(sec), 1_234_567_000) for _, _, sec in rows)
    assert totals["workload"] == expected
    workloads = {r["key"]: r for r in by["workload"]["rows"]}
    assert {"training", "vllm", "jupyter", "__idle__"} <= set(workloads)
    assert workloads["__idle__"]["nusd"] == by["workload"]["idle_nusd"]
    assert workloads["training"]["nusd"] > workloads["vllm"]["nusd"] > workloads["jupyter"]["nusd"]


# 6. Alerts: one firing, delivered by email and a signed webhook, resolved once.


async def test_6_a_hot_gpu_alerts_once_by_email_and_signed_webhook(
    api: Api, webhook: WebhookReceiver, mailpit: Mailpit
) -> None:
    email = await api.ok(
        "POST",
        "/api/v1/alerts/channels",
        {"name": "Ops", "kind": "email", "emails": ["ops@example.test"]},
    )
    hook = await api.ok(
        "POST",
        "/api/v1/alerts/channels",
        {"name": "Hook", "kind": "webhook", "url": webhook.url, "secret": "whsec-test-123"},
    )
    await api.ok(
        "POST",
        "/api/v1/alerts/rules",
        {
            "name": "Too hot",
            "metric": "temp_c",
            "operator": "gt",
            "threshold": 80,
            "duration_s": 60,
            "severity": "critical",
            "channel_ids": [email["id"], hook["id"]],
        },
    )
    host = await api.host(hostname="hot-node")
    u = host.uuids[0]
    t = now()
    hot = [sample(u, t - timedelta(seconds=s), temp_c=88.0) for s in range(0, 90, 5)]
    await host.ok(batch([gpu(u)], hot, hostname="hot-node"))
    for _ in range(3):
        await api.evaluate_alerts()
    events = [
        e for e in await api.ok("GET", "/api/v1/alerts/events") if e["rule_name"] == "Too hot"
    ]
    assert len(events) == 1 and events[0]["resolved_at"] is None and events[0]["value"] == 88.0
    assert await api.deliver() == 2
    notes = await api.ok("GET", "/api/v1/alerts/notifications")
    assert all(n["delivered_at"] for n in notes), notes
    if api.container.settings.mail_mode == "smtp":
        mail = await mailpit.messages("ops@example.test")
        assert len(mail) == 1 and "Too hot" in mail[0]["Subject"]
    assert len(webhook.received) == 1
    got = webhook.received[0]
    expected = (
        "sha256="
        + hmac.new(
            b"whsec-test-123",
            got.headers["x-gpuwatch-timestamp"].encode() + b"." + got.body,
            hashlib.sha256,
        ).hexdigest()
    )
    assert got.headers["x-gpuwatch-signature"] == expected
    assert got.json()["type"] == "alert.fired" and got.json()["value"] == 88.0
    # One cool reading is not enough: an alert hovering at its threshold must not flap.
    t1 = now()
    await host.ok(
        batch([gpu(u)], [sample(u, t1 + timedelta(seconds=1), temp_c=61.0)], hostname="hot-node")
    )
    await api.evaluate_alerts(t1 + timedelta(seconds=2))
    still = [e for e in await api.ok("GET", "/api/v1/alerts/events") if e["rule_name"] == "Too hot"]
    assert still[0]["resolved_at"] is None and await api.deliver() == 0
    # Cool for the rule's whole duration: resolved, once.
    cool = [sample(u, t1 + timedelta(seconds=s), temp_c=61.0) for s in range(5, 80, 5)]
    await host.ok(batch([gpu(u)], cool, hostname="hot-node"))
    await api.evaluate_alerts(t1 + timedelta(seconds=80))
    await api.evaluate_alerts(t1 + timedelta(seconds=81))
    events = [
        e for e in await api.ok("GET", "/api/v1/alerts/events") if e["rule_name"] == "Too hot"
    ]
    assert len(events) == 1 and events[0]["resolved_at"] is not None
    assert await api.deliver() == 2
    assert [r.json()["type"] for r in webhook.received] == ["alert.fired", "alert.resolved"]


# 7. No lost data: the real agent spools while the API is down and replays once.


async def test_7_the_agent_spools_while_the_server_is_down_and_replays_without_duplicates(
    live_server: LiveServer, tmp_path: Path
) -> None:
    from gpuwatch_agent.agent import Agent
    from gpuwatch_agent.client import Client
    from gpuwatch_agent.config import AgentConfig

    async with httpx.AsyncClient(base_url=live_server.url) as c:
        token = (
            await c.post(
                "/api/v1/auth/login",
                json={"email": "owner@example.test", "password": "Owner-Pass-123"},
            )
        ).json()["session_token"]
        enrol = (
            await c.post(
                "/api/v1/enrolment-tokens",
                json={"name": "agent"},
                headers={"authorization": f"Bearer {token}"},
            )
        ).json()["token"]
    cfg = AgentConfig(
        url=live_server.url,
        enrolment_token=enrol,
        state_dir=tmp_path / "agent",
        collector="simulated",
        sim_profile="workstation",
        machine_id="contract-ws-1",
        interval_s=5,
    )

    def run() -> tuple[int, int]:
        agent = Agent(cfg)
        agent.ensure_enrolled()
        assert agent.tick()  # online
        agent.client = Client("http://127.0.0.1:9", 1.0)  # the server goes away
        agent.client.token = (cfg.state_dir / "host-token").read_text()
        t = now()
        for i in range(3):
            assert not agent.deliver(agent.collect(t + timedelta(seconds=5 * (i + 1))))
        spooled = len(agent.spool.pending())
        agent.client = Client(cfg.url, 5.0)  # and comes back
        agent.client.token = (cfg.state_dir / "host-token").read_text()
        replayed = agent.replay()
        # Replaying a batch the server already has changes nothing.
        return spooled, replayed

    spooled, replayed = await asyncio.to_thread(run)
    assert spooled == 3 and replayed == 3
    async with httpx.AsyncClient(base_url=live_server.url) as c:
        auth = {"authorization": f"Bearer {token}"}
        g = (await c.get("/api/v1/gpus", headers=auth)).json()[0]
        end = (now() + timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
        series = (
            await c.get(f"/api/v1/gpus/{g['id']}/metrics?resolution=raw&end={end}", headers=auth)
        ).json()
    assert len(series["points"]) == 4  # one live tick + three replayed, no duplicates


async def test_7_resending_a_batch_is_a_no_op(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    body = batch([gpu(u)], [sample(u, now())])
    first = await host.ok(body)
    again = await host.ok(body)
    assert first["duplicate"] is False and first["samples"] == 1
    assert again["duplicate"] is True and again["samples"] == 0
    assert (await api.sql("SELECT count(*) FROM gpu_samples"))[0][0] == 1


# 8. Slow, explained: throttle reasons name the cause.


async def test_8_power_capping_during_busy_time_is_named(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    start = _hour_floor(now()) - timedelta(hours=2)
    samples = [
        sample(
            u,
            start + timedelta(minutes=i),
            interval=60,
            util_gpu=95.0,
            throttle_reasons=0x4 if i % 2 else 0,
        )
        for i in range(60)
    ]
    await host.ok(batch([gpu(u)], samples))
    await api.rollup(start + timedelta(hours=1))
    await api.insights(start + timedelta(hours=1, minutes=1))
    found = [i for i in await api.ok("GET", "/api/v1/insights") if i["kind"] == "throttled"]
    assert len(found) == 1
    assert found[0]["evidence"]["main_reason"] == "power"
    assert found[0]["evidence"]["shares"]["power"] == pytest.approx(0.5, abs=0.02)
    assert "power cap" in found[0]["title"]
    explanation = await api.ok("GET", f"/api/v1/gpus/{await api.gpu_id(u)}/explain")
    assert any("power cap" in s for s in explanation["sentences"])


# 9. Inference cost: TTFT p95, tokens per second and cost per million tokens.


async def test_9_inference_metrics_match_a_hand_calculation(api: Api) -> None:
    await api.set_rate(A100, "2.00")
    host = await api.host()
    u = host.uuids[0]
    t0 = _hour_floor(now()) - timedelta(hours=2)
    samples = [sample(u, t0 + timedelta(minutes=i), interval=60, util_gpu=50.0) for i in range(60)]
    rows = [
        {
            "endpoint": "chat",
            "kind": "vllm",
            "url": "http://vllm:8000/metrics",
            "model": "llama",
            "gpu_uuids": [u],
            "ts": (t0 + timedelta(minutes=i, seconds=30)).isoformat(),
            "interval_s": 60,
            "up": True,
            "requests": 120,
            "prompt_tokens": 60_000,
            "generation_tokens": 12_000,
            "running": 8,
            "waiting": 0,
            "kv_cache_usage": 0.4,
            "ttft": {"0.1": 60, "0.25": 48, "0.5": 12, "+Inf": 0},
            "itl": {"0.05": 12_000, "+Inf": 0},
            "e2e": {"5.0": 120, "+Inf": 0},
        }
        for i in range(60)
    ]
    await host.ok(batch([gpu(u)], samples, inference=rows))
    await api.rollup(t0 + timedelta(hours=1))
    ep = (await api.ok("GET", "/api/v1/inference/endpoints"))[0]
    q = f"start={t0.isoformat().replace('+00:00', 'Z')}&end={(t0 + timedelta(hours=1)).isoformat().replace('+00:00', 'Z')}"
    s = (await api.ok("GET", f"/api/v1/inference/endpoints/{ep['id']}/series?{q}"))["summary"]
    # p95 rank 6840 of 7200 falls in (0.25, 0.5]: 0.25 + 0.25 * (6840 - 6480) / 720 = 0.375
    assert s["ttft_p95_s"] == pytest.approx(0.375)
    assert s["generation_tokens_per_s"] == pytest.approx(200.0)
    assert s["requests_per_s"] == pytest.approx(2.0)
    assert s["gpu_cost_nusd"] == 2_000_000_000
    assert s["nusd_per_million_tokens"] == round(2_000_000_000 * 1e6 / 4_320_000)


async def test_9_a_server_without_ttft_reports_null_not_zero(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    row = {
        "endpoint": "sum",
        "kind": "tgi",
        "url": "http://tgi/metrics",
        "gpu_uuids": [u],
        "ts": now().isoformat(),
        "interval_s": 5,
        "up": True,
        "requests": 3,
        "ttft": None,
    }
    await host.ok(batch([gpu(u)], [sample(u, now())], inference=[row]))
    ep = (await api.ok("GET", "/api/v1/inference/endpoints"))[0]
    assert ep["stats_24h"]["ttft_p95_s"] is None
    assert ep["stats_24h"]["kv_cache_avg"] is None


# 10. Driver failure is graceful.


async def test_10_a_driver_failure_shows_the_reason_and_the_gpu_as_lost(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    await host.ok(batch([gpu(u)], [sample(u, now())]))
    problem = {"code": "nvml_init_failed", "message": "NVML could not start (Driver Not Loaded)"}
    await host.ok(batch([], [], status="degraded", problems=[problem]))
    await api.sql("UPDATE gpus SET last_seen_at = now() - interval '2 minutes'")
    h = await api.ok("GET", f"/api/v1/hosts/{host.host_id}")
    assert h["status"] == "online" and h["agent_status"] == "degraded"
    assert h["problems"][0]["code"] == "nvml_init_failed"
    assert (await api.ok("GET", "/api/v1/gpus"))[0]["status"] == "lost"
    await api.evaluate_alerts()
    lost = [e for e in await api.ok("GET", "/api/v1/alerts/events") if e["kind"] == "gpu_lost"]
    assert len(lost) == 1


# 11. Observe only.


async def test_11_agents_can_only_reach_ingest_and_get_no_commands(api: Api) -> None:
    host = await api.host()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api.app), base_url="http://t"
    ) as c:
        for path in ("/api/v1/hosts", "/api/v1/gpus", "/api/v1/alerts/rules"):
            r = await c.get(path, headers={"authorization": f"Bearer {host.token}"})
            assert r.status_code == 401
    u = host.uuids[0]
    reply = await host.ok(batch([gpu(u)], [sample(u, now())]))
    assert set(reply) == {
        "accepted",
        "duplicate",
        "samples",
        "processes",
        "inference",
        "dropped",
        "next_in_s",
    }
    ingest = [p for p in api.app.openapi()["paths"] if p.startswith("/ingest")]
    assert sorted(ingest) == ["/ingest/v1/batches", "/ingest/v1/enroll"]
    for path in api.app.openapi()["paths"]:
        assert not any(word in path for word in ("kill", "exec", "command", "terminate", "restart"))


# 12. Private by default is covered by unit tests over settings and sources
# (tests/unit/test_privacy.py); a viewer can read but never change anything.


async def test_12_a_viewer_reads_but_cannot_change(api: Api) -> None:
    await api.ok(
        "POST",
        "/api/v1/users",
        {"email": "v@example.test", "name": "V", "password": "Viewer-Pass-123", "role": "viewer"},
    )
    viewer = await login(api.app, {"email": "v@example.test", "password": "Viewer-Pass-123"})
    assert (await viewer.get("/api/v1/hosts")).status_code == 200
    r = await viewer.post(
        "/api/v1/rates", json={"scope": "model", "gpu_model": A100, "usd_per_hour": "1"}
    )
    assert r.status_code == 403
    await viewer.aclose()
