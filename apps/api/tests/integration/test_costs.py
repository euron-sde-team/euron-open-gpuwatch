"""Rates, workload rules, cost summaries, series and CSV reports."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from tests.integration.conftest import Api, batch, gpu, now, process, sample

pytestmark = pytest.mark.integration
A100 = "NVIDIA A100-SXM4-80GB"


def _iso(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


async def _hour_of_work(
    api: Api, *, name: str = "python3", hours: int = 1, gpus: int = 1
) -> tuple[datetime, list[str]]:
    host = await api.host(labels={"site": "dc-1"}, gpus=gpus)
    start = now().replace(minute=0, second=0) - timedelta(hours=hours + 1)
    samples, procs = [], []
    for u in host.uuids:
        for i in range(hours * 60):
            ts = start + timedelta(minutes=i)
            samples.append(sample(u, ts, interval=60, util_gpu=70.0, procs=1))
            procs.append(process(u, ts, 10, name, mem_used_mib=5000.0))
    await host.ok(batch([gpu(u, i) for i, u in enumerate(host.uuids)], samples, procs))
    await api.rollup(start + timedelta(hours=hours))
    return start, host.uuids


async def test_rates_apply_most_specific_first(api: Api) -> None:
    start, (u,) = await _hour_of_work(api)
    gid = await api.gpu_id(u)
    host_id = (await api.ok("GET", f"/api/v1/gpus/{gid}"))["host_id"]
    await api.set_rate(A100, "3.00")
    assert (await api.ok("GET", f"/api/v1/gpus/{gid}"))["rate_scope"] == "model"
    await api.ok(
        "POST", "/api/v1/rates", {"scope": "host", "host_id": host_id, "usd_per_hour": "2.00"}
    )
    assert (await api.ok("GET", f"/api/v1/gpus/{gid}"))["nusd_per_hour"] == 2_000_000_000
    gpu_rate = await api.ok(
        "POST",
        "/api/v1/rates",
        {"scope": "gpu", "gpu_id": gid, "usd_per_hour": "1.50", "note": "reserved"},
    )
    g = await api.ok("GET", f"/api/v1/gpus/{gid}")
    assert g["rate_scope"] == "gpu" and g["nusd_per_hour"] == 1_500_000_000
    q = f"start={_iso(start)}&end={_iso(start + timedelta(hours=1))}"
    assert (await api.ok("GET", f"/api/v1/costs?group_by=gpu&{q}"))["total_nusd"] == 1_500_000_000
    await api.ok("PATCH", f"/api/v1/rates/{gpu_rate['id']}", {"usd_per_hour": "1.25"})
    assert (await api.ok("GET", f"/api/v1/costs?group_by=gpu&{q}"))["total_nusd"] == 1_250_000_000
    rates = await api.ok("GET", "/api/v1/rates")
    assert [r["scope"] for r in rates] == ["model", "host", "gpu"]
    assert all(r["gpus_covered"] == (1 if r["scope"] == "gpu" else 0) for r in rates)
    await api.ok("DELETE", f"/api/v1/rates/{gpu_rate['id']}")
    assert (await api.ok("GET", f"/api/v1/gpus/{gid}"))["rate_scope"] == "host"


async def test_rate_validation_and_conflicts(api: Api) -> None:
    await api.set_rate(A100, "1")
    dup = await api.client.post(
        "/api/v1/rates", json={"scope": "model", "gpu_model": A100, "usd_per_hour": "2"}
    )
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "rate_exists"
    for bad in (
        {"scope": "host", "usd_per_hour": "1"},
        {"scope": "model", "gpu_model": "X", "usd_per_hour": "-1"},
    ):
        assert (await api.client.post("/api/v1/rates", json=bad)).status_code == 422
    missing = await api.client.post(
        "/api/v1/rates",
        json={
            "scope": "host",
            "host_id": "00000000-0000-0000-0000-000000000000",
            "usd_per_hour": "1",
        },
    )
    assert missing.status_code == 404


async def test_without_a_rate_hours_are_reported_unpriced(api: Api) -> None:
    start, _ = await _hour_of_work(api)
    s = await api.ok(
        "GET", f"/api/v1/costs?start={_iso(start)}&end={_iso(start + timedelta(hours=1))}"
    )
    assert s["total_nusd"] == 0 and s["unpriced_gpu_hours"] == pytest.approx(1.0)


async def test_workload_rules_map_processes_and_apply_retroactively(api: Api) -> None:
    await api.set_rate(A100, "1.00")
    start, _ = await _hour_of_work(api, name="train.py")
    q = f"group_by=workload&start={_iso(start)}&end={_iso(start + timedelta(hours=1))}"
    assert [r["key"] for r in (await api.ok("GET", f"/api/v1/costs?{q}"))["rows"]] == ["train.py"]
    bad = await api.client.post(
        "/api/v1/workload-rules", json={"workload": "x", "process_pattern": "("}
    )
    assert bad.status_code == 422
    empty = await api.client.post("/api/v1/workload-rules", json={"workload": "x"})
    assert empty.status_code == 422
    rule = await api.ok(
        "POST",
        "/api/v1/workload-rules",
        {
            "workload": "llm-training",
            "team": "Research",
            "process_pattern": "train",
            "host_label": "site=dc-1",
        },
    )
    await api.ok("POST", "/api/v1/workload-rules/apply")
    await api.rollup()
    rows = (await api.ok("GET", f"/api/v1/costs?{q}"))["rows"]
    assert [r["key"] for r in rows] == ["llm-training"]
    teams = (
        await api.ok(
            "GET",
            f"/api/v1/costs?group_by=team&start={_iso(start)}&end={_iso(start + timedelta(hours=1))}",
        )
    )["rows"]
    assert teams[0]["label"] == "Research"
    edited = await api.ok(
        "PUT",
        f"/api/v1/workload-rules/{rule['id']}",
        {
            **{k: rule[k] for k in ("workload", "team", "process_pattern")},
            "host_label": "site=elsewhere",
        },
    )
    assert edited["host_label"] == "site=elsewhere"
    await api.ok("DELETE", f"/api/v1/workload-rules/{rule['id']}")
    assert await api.ok("GET", "/api/v1/workload-rules") == []


async def test_cost_series_buckets_by_hour_or_day(api: Api) -> None:
    await api.set_rate(A100, "2.00")
    start, _ = await _hour_of_work(api, hours=2)
    hourly = await api.ok(
        "GET",
        f"/api/v1/costs/series?group_by=gpu&start={_iso(start)}&end={_iso(start + timedelta(hours=2))}",
    )
    assert hourly["interval"] == "hour" and len(hourly["points"]) == 2
    assert sum(sum(p["values"].values()) for p in hourly["points"]) == 4_000_000_000
    daily = await api.ok(
        "GET",
        f"/api/v1/costs/series?group_by=gpu&start={_iso(start - timedelta(days=5))}&end={_iso(start + timedelta(hours=2))}",
    )
    assert daily["interval"] == "day"
    assert sum(sum(p["values"].values()) for p in daily["points"]) == 4_000_000_000


async def test_cost_ranges_are_validated(api: Api) -> None:
    t = now()
    assert (
        await api.client.get(f"/api/v1/costs?start={_iso(t)}&end={_iso(t - timedelta(hours=1))}")
    ).status_code == 400
    assert (
        await api.client.get(f"/api/v1/costs?start={_iso(t - timedelta(days=500))}&end={_iso(t)}")
    ).status_code == 400


async def test_reports_export_a_csv(api: Api) -> None:
    await api.set_rate(A100, "1.00")
    start, _ = await _hour_of_work(api, gpus=2)
    report = await api.ok(
        "POST",
        "/api/v1/reports",
        {
            "group_by": "gpu",
            "start": start.isoformat(),
            "end": (start + timedelta(hours=1)).isoformat(),
            "note": "October",
        },
    )
    assert report["rows"] == 2 and report["total_nusd"] == 2_000_000_000
    assert (await api.ok("GET", "/api/v1/reports"))[0]["id"] == report["id"]
    r = await api.client.get(f"/api/v1/reports/{report['id']}/download")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'attachment; filename="gpuwatch-costs-by-gpu-' in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0] == "gpu,cost_usd,idle_cost_usd,gpu_hours,share_pct"
    assert lines[-1].startswith("TOTAL,2.000000")
