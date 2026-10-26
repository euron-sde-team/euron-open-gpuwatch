"""History: rollups (including late data), retention, series, processes, the insights
workflow, the overview and the per-GPU explanation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from gpuwatch.telemetry import partitions, retention, rollups
from tests.integration.conftest import Api, batch, gpu, now, process, sample

pytestmark = pytest.mark.integration
A100 = "NVIDIA A100-SXM4-80GB"


def _iso(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


async def test_late_samples_are_rolled_up_exactly_once(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    start = now().replace(second=0) - timedelta(minutes=30)
    first = [
        sample(u, start + timedelta(seconds=10 * i), interval=10, util_gpu=40.0) for i in range(60)
    ]
    await host.ok(batch([gpu(u)], first))
    await api.rollup()
    # A spool replay: samples for the same minutes arrive after they were rolled up.
    late = [
        sample(u, start + timedelta(seconds=10 * i + 5), interval=5, util_gpu=80.0)
        for i in range(60)
    ]
    await host.ok(batch([gpu(u)], late))
    assert (await api.sql("SELECT count(*) FROM rollup_dirty"))[0][0] == 1
    await api.rollup()
    await api.rollup()  # idempotent
    rows = await api.sql("SELECT sum(samples), sum(seconds), avg(util_avg) FROM gpu_rollups_1m")
    assert rows[0][0] == 120 and rows[0][1] == pytest.approx(900.0)
    assert rows[0][2] == pytest.approx(60.0)
    assert (await api.sql("SELECT count(*) FROM rollup_dirty"))[0][0] == 0
    hours = await api.sql("SELECT sum(samples) FROM gpu_rollups_1h")
    assert hours[0][0] == 120


async def test_series_resolution_follows_the_range(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    start = now().replace(minute=0, second=0) - timedelta(hours=3)
    await host.ok(
        batch(
            [gpu(u)],
            [
                sample(u, start + timedelta(minutes=i), interval=60, util_gpu=float(i % 100))
                for i in range(180)
            ],
        )
    )
    await api.rollup()
    gid = await api.gpu_id(u)
    raw = await api.ok(
        "GET", f"/api/v1/gpus/{gid}/metrics?start={_iso(now() - timedelta(hours=2))}"
    )
    assert raw["resolution"] == "raw"
    minute = await api.ok(
        "GET", f"/api/v1/gpus/{gid}/metrics?start={_iso(start)}&end={_iso(now())}"
    )
    assert minute["resolution"] == "1m" and len(minute["points"]) == 180
    hourly = await api.ok(
        "GET", f"/api/v1/gpus/{gid}/metrics?start={_iso(start - timedelta(days=5))}"
    )
    assert hourly["resolution"] == "1h" and len(hourly["points"]) == 3
    bad = await api.client.get(
        f"/api/v1/gpus/{gid}/metrics?start={_iso(now())}&end={_iso(now() - timedelta(hours=1))}"
    )
    assert bad.status_code == 400
    fleet = await api.ok("GET", f"/api/v1/fleet/series?start={_iso(start)}&end={_iso(now())}")
    assert fleet["resolution"] == "1m" and fleet["points"][0]["gpus"] == 1


async def test_processes_and_workload_shares(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    t = now()
    await host.ok(
        batch(
            [gpu(u)],
            [sample(u, t - timedelta(minutes=2), interval=60, procs=2), sample(u, t, procs=2)],
            [
                process(u, t - timedelta(minutes=2), 1, "vllm", mem_used_mib=30000.0, sm_util=60.0),
                process(
                    u, t - timedelta(minutes=2), 2, "python3", mem_used_mib=10000.0, sm_util=20.0
                ),
                process(
                    u,
                    t,
                    1,
                    "vllm",
                    mem_used_mib=30000.0,
                    sm_util=60.0,
                    username="svc",
                    container_id="abc123def456",
                ),
                process(u, t, 2, "python3", mem_used_mib=10000.0, sm_util=20.0),
            ],
        )
    )
    await api.rollup(t + timedelta(minutes=2))
    gid = await api.gpu_id(u)
    p = await api.ok("GET", f"/api/v1/gpus/{gid}/processes")
    assert p["listed"] is True
    assert [x["name"] for x in p["current"]] == ["vllm", "python3"]
    assert p["current"][0]["container_id"] == "abc123def456"
    shares = {w["workload"]: w["share"] for w in p["workloads"]}
    assert shares["vllm"] == pytest.approx(0.75, abs=0.01)


async def test_a_gpu_without_process_listing_is_unattributed_while_busy(api: Api) -> None:
    await api.set_rate(A100, "1.00")
    host = await api.host()
    u = host.uuids[0]
    start = now().replace(minute=0, second=0) - timedelta(hours=2)
    await host.ok(
        batch(
            [gpu(u)],
            [
                sample(u, start + timedelta(minutes=i), interval=60, util_gpu=90.0, procs=None)
                for i in range(60)
            ],
        )
    )
    await api.rollup(start + timedelta(hours=1))
    s = await api.ok(
        "GET",
        f"/api/v1/costs?group_by=workload&start={_iso(start)}&end={_iso(start + timedelta(hours=1))}",
    )
    assert [r["key"] for r in s["rows"]] == ["(unattributed)"]
    assert s["idle_nusd"] == 0


async def test_retention_drops_only_rolled_up_partitions(api: Api) -> None:
    host = await api.host(simulated=True)
    u = host.uuids[0]
    old = now() - timedelta(days=10)
    await host.ok(batch([gpu(u)], [sample(u, old, interval=60), sample(u, now(), interval=60)]))
    days_before = {d for _, d in await partitions.existing(api.container.db.engine)}
    assert old.date() in days_before
    counts = await retention.run(api.container)
    assert "partitions" not in counts  # no watermark yet: nothing rolled up, nothing dropped
    await api.rollup()
    counts = await retention.run(api.container)
    assert counts["partitions"] >= 2  # both tables' old partition
    days_after = {d for _, d in await partitions.existing(api.container.db.engine)}
    assert old.date() not in days_after and now().date() in days_after
    assert (await api.sql("SELECT count(*) FROM gpu_rollups_1m"))[0][0] >= 2  # rollups survive


async def test_partitions_are_created_ahead(api: Api) -> None:
    await retention.ensure_partitions(api.container)
    days = {d for t, d in await partitions.existing(api.container.db.engine) if t == "gpu_samples"}
    today = datetime.now(UTC).date()
    assert {today + timedelta(days=d) for d in range(4)} <= days


async def test_insight_settings_change_what_counts_as_idle(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    start = now().replace(minute=0, second=0) - timedelta(hours=2)
    await host.ok(
        batch(
            [gpu(u)],
            [
                sample(
                    u,
                    start + timedelta(minutes=i),
                    interval=60,
                    util_gpu=8.0,
                    procs=0,
                    mem_used_mib=0.0,
                )
                for i in range(60)
            ],
        )
    )
    await api.rollup(start + timedelta(hours=1))
    await api.insights(start + timedelta(hours=1))
    assert not [i for i in await api.ok("GET", "/api/v1/insights") if i["kind"] == "idle_empty"]
    cfg = await api.ok("GET", "/api/v1/settings/insights")
    assert cfg["idle_util_pct"] == 5.0
    await api.ok("PUT", "/api/v1/settings/insights", {**cfg, "idle_util_pct": 10.0})
    await api.insights(start + timedelta(hours=1))
    found = [i for i in await api.ok("GET", "/api/v1/insights") if i["kind"] == "idle_empty"]
    assert len(found) == 1 and found[0]["evidence"]["idle_util_pct"] == 10.0
    bad = await api.client.put("/api/v1/settings/insights", json={**cfg, "idle_util_pct": 90})
    assert bad.status_code == 422


async def test_insights_can_be_acknowledged_dismissed_and_resolve_themselves(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    start = now().replace(minute=0, second=0) - timedelta(hours=2)
    await host.ok(
        batch(
            [gpu(u)],
            [
                sample(
                    u,
                    start + timedelta(minutes=i),
                    interval=60,
                    util_gpu=0.0,
                    procs=0,
                    mem_used_mib=0.0,
                )
                for i in range(60)
            ],
        )
    )
    await api.rollup(start + timedelta(hours=1))
    await api.insights(start + timedelta(hours=1))
    finding = (await api.ok("GET", "/api/v1/insights"))[0]
    acked = await api.ok(
        "POST", f"/api/v1/insights/{finding['id']}/actions", {"action": "acknowledge"}
    )
    assert acked["status"] == "acknowledged"
    await api.insights(start + timedelta(hours=1, minutes=5))
    assert (await api.ok("GET", "/api/v1/insights"))[0]["status"] == "acknowledged"  # kept
    await api.ok("POST", f"/api/v1/insights/{finding['id']}/actions", {"action": "dismiss"})
    assert (await api.ok("GET", "/api/v1/insights?status=dismissed"))[0]["id"] == finding["id"]
    # Eight days later the idle hour is out of the window: the finding resolves itself.
    await api.insights(start + timedelta(days=8))
    resolved = (await api.ok("GET", "/api/v1/insights"))[0]
    assert resolved["status"] == "resolved" and resolved["resolved_at"]
    r = await api.client.post(
        f"/api/v1/insights/{finding['id']}/actions", json={"action": "reopen"}
    )
    assert r.status_code == 404
    assert (await api.ok("POST", "/api/v1/insights/evaluate"))["ok"] is True


async def test_overview_and_explanation(api: Api) -> None:
    await api.set_rate(A100, "2.00")
    host = await api.host()
    u = host.uuids[0]
    t = now()
    start = t.replace(minute=0, second=0) - timedelta(hours=3)
    rows, procs = [], []
    for i in range(120):
        ts = start + timedelta(minutes=i)
        busy = i < 30
        rows.append(
            sample(
                u, ts, interval=60, util_gpu=95.0 if busy else 1.0, procs=1, mem_used_mib=30000.0
            )
        )
        procs.append(process(u, ts, 7, "vllm", mem_used_mib=30000.0))
    rows.append(sample(u, t, util_gpu=96.0, procs=1))
    await host.ok(batch([gpu(u)], rows, procs))
    await api.rollup(start + timedelta(hours=2))
    await api.insights(start + timedelta(hours=2))
    o = await api.ok("GET", "/api/v1/overview")
    assert o["hosts_online"] == 1 and o["gpus_reporting"] == 1 and o["rates_set"] is True
    assert o["util_now_avg"] == 96.0
    assert o["spend_7d_nusd"] > 0 and o["idle_7d_nusd"] > 0
    assert o["top_insights"] and o["top_insights"][0]["kind"] == "idle_loaded"
    e = await api.ok("GET", f"/api/v1/gpus/{await api.gpu_id(u)}/explain")
    assert e["headline"].startswith("Expensive because it sits idle")
    assert "vllm" in e["sentences"][0]
    # 90 of 120 minutes were held idle by vllm: three quarters of the cost.
    assert e["held_idle_nusd"] / e["cost_nusd"] == pytest.approx(0.75, abs=0.02)


async def test_rollup_runs_once_across_replicas(api: Api) -> None:
    import asyncio

    host = await api.host()
    u = host.uuids[0]
    await host.ok(batch([gpu(u)], [sample(u, now() - timedelta(minutes=10))]))
    results = await asyncio.gather(
        *(rollups.tick(api.container, now() + timedelta(minutes=5)) for _ in range(4))
    )
    assert sum(1 for r in results if r) == 1


async def test_the_worker_runs_every_job_on_its_schedule(api: Api) -> None:
    from gpuwatch import worker

    host = await api.host()
    await host.ok(
        batch([gpu(host.uuids[0])], [sample(host.uuids[0], now() - timedelta(minutes=5))])
    )
    schedule = worker.jobs(api.container)
    assert {j.name for j in schedule} == {
        "partitions",
        "rollup",
        "alerts",
        "notifications",
        "insights",
        "retention",
    }
    assert await worker.run_due(api.container, schedule, now=10_000.0) == len(schedule)
    assert await worker.run_due(api.container, schedule, now=10_001.0) == 0  # nothing due yet
    assert (
        await worker.run_due(api.container, schedule, now=10_010.0) >= 2
    )  # rollup + notifications


async def test_a_failing_job_never_stops_the_others(api: Api) -> None:
    from gpuwatch import worker

    async def boom(_: object) -> None:
        raise RuntimeError("broken job")

    ran: list[str] = []

    async def fine(_: object) -> None:
        ran.append("fine")

    schedule = [worker.Job("boom", 1, boom), worker.Job("fine", 1, fine)]
    assert await worker.run_due(api.container, schedule, now=5.0) == 2
    assert ran == ["fine"]
