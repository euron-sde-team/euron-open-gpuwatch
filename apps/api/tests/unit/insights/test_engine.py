"""The insights engine on exact inputs: every rule, its threshold and its arithmetic."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from gpuwatch.costs.rates import seconds_cost
from gpuwatch.insights import engine
from gpuwatch.insights.engine import (
    CatalogEntry,
    EndpointContext,
    EndpointMinute,
    GpuContext,
    Minute,
)
from gpuwatch.insights.settings import InsightSettings

T0 = datetime(2026, 10, 20, 0, 0, tzinfo=UTC)
CFG = InsightSettings()
WINDOW = (T0, T0 + timedelta(days=7))


def ctx(
    rate: int | None = 2_000_000_000, mem: float = 81_920.0, holders: tuple[str, ...] = ()
) -> GpuContext:
    return GpuContext(
        uuid.uuid4(), uuid.uuid4(), "NVIDIA A100-SXM4-80GB", "GPU 0 on n1", mem, rate, holders
    )


def minute(
    i: int, util: float | None = 0.0, mem: float = 0.0, procs: int | None = 0, **kw: object
) -> Minute:
    values: dict[str, object] = {
        "bucket": T0 + timedelta(minutes=i),
        "seconds": 60.0,
        "util_avg": util,
        "util_max": util,
        "mem_used_max": mem,
        "mem_total": 81_920.0,
        "procs_max": procs,
        "busy_s": None,
        "throttle_power_s": None,
        "throttle_thermal_s": None,
        "throttle_hw_s": None,
        "ecc_max": None,
        "xid_count": 0,
    }
    values.update(kw)
    return Minute(**values)  # type: ignore[arg-type]


def test_idle_runs_need_contiguous_minutes_of_the_minimum_length() -> None:
    minutes = [minute(i) for i in range(29)] + [minute(i) for i in range(40, 80)]
    runs = engine.idle_runs(minutes, lambda m: True, 30)
    assert len(runs) == 1 and runs[0][0] == T0 + timedelta(minutes=40) and runs[0][2] == 40 * 60


def test_a_gap_in_data_ends_a_run() -> None:
    minutes = [minute(i) for i in range(20)] + [minute(i) for i in range(21, 41)]
    assert engine.idle_runs(minutes, lambda m: True, 30) == []


def test_idle_with_a_model_loaded_costs_rate_times_idle_time() -> None:
    gpu = ctx(holders=("vllm",))
    minutes = [minute(i, util=1.0, mem=40_000.0, procs=1) for i in range(90)]
    (f,) = engine.idle_findings(gpu, minutes, CFG, WINDOW)
    assert f.kind == "idle_loaded" and f.fingerprint == f"idle_loaded:{gpu.id}"
    assert f.evidence["idle_seconds"] == 5400
    assert f.evidence["cost_nusd"] == seconds_cost(5400, 2_000_000_000) == 3_000_000_000
    assert "vllm" in f.summary and "$3.00" in f.summary
    assert f.est_monthly_nusd is None  # less than a day of data: no extrapolation
    assert f.severity == "warning"  # 100% of monitored time


def test_the_monthly_estimate_scales_to_30_days() -> None:
    gpu = ctx()
    minutes = [
        minute(i, util=2.0 if i % 1440 < 360 else 80.0, procs=0 if i % 1440 < 360 else 1)
        for i in range(2 * 1440)
    ]
    found = {f.kind: f for f in engine.idle_findings(gpu, minutes, CFG, WINDOW)}
    f = found["idle_empty"]
    assert f.evidence["idle_hours"] == pytest.approx(12.0)
    assert f.est_monthly_nusd == round(f.evidence["cost_nusd"] * 30 / 2)
    assert f.severity == "warning"  # 25% of the time


def test_no_rate_means_no_cost_but_still_a_finding() -> None:
    (f,) = engine.idle_findings(ctx(rate=None), [minute(i) for i in range(60)], CFG, WINDOW)
    assert f.evidence["cost_nusd"] is None and f.est_monthly_nusd is None
    assert "Set a rate" in f.summary


def test_unknown_utilization_is_never_idle() -> None:
    assert engine.idle_findings(ctx(), [minute(i, util=None) for i in range(60)], CFG, WINDOW) == []


def test_underused_needs_enough_busy_time_at_low_utilization() -> None:
    gpu = ctx()
    low = [minute(i, util=20.0, procs=1) for i in range(7 * 60)]
    f = engine.underused_finding(gpu, low, CFG, WINDOW)
    assert f is not None and f.evidence["avg_util"] == pytest.approx(20.0)
    assert engine.underused_finding(gpu, low[: 5 * 60], CFG, WINDOW) is None
    busy = [minute(i, util=80.0, procs=1) for i in range(7 * 60)]
    assert engine.underused_finding(gpu, busy, CFG, WINDOW) is None


def test_oversized_suggests_a_cheaper_card_that_fits_from_your_own_rates() -> None:
    gpu = ctx(rate=2_000_000_000, mem=81_920.0)
    minutes = [minute(i, util=50.0, mem=16_000.0, procs=1) for i in range(1440)]
    catalog = [
        CatalogEntry("NVIDIA L4", 23_034.0, 600_000_000),
        CatalogEntry("NVIDIA T4", 15_360.0, 300_000_000),
    ]
    f = engine.oversized_finding(gpu, minutes, CFG, WINDOW, catalog)
    assert f is not None
    assert f.evidence["candidate"]["model"] == "NVIDIA L4"  # the T4 is too small for 16 GiB x 1.25
    assert f.est_monthly_nusd == (2_000_000_000 - 600_000_000) * 730
    assert engine.oversized_finding(gpu, minutes[:600], CFG, WINDOW, catalog) is None  # < a day


def test_throttling_names_the_dominant_reason() -> None:
    gpu = ctx()
    minutes = [
        minute(
            i,
            util=95.0,
            procs=1,
            busy_s=60.0,
            throttle_power_s=6.0,
            throttle_thermal_s=30.0,
            throttle_hw_s=0.0,
        )
        for i in range(60)
    ]
    f = engine.throttle_finding(gpu, minutes, CFG, WINDOW)
    assert f is not None and f.evidence["main_reason"] == "thermal"
    assert f.severity == "critical"  # thermal at 50% of busy time
    assert "thermal limit" in f.title and "power cap 10%" in f.summary
    quiet = [
        minute(
            i,
            util=95.0,
            busy_s=60.0,
            throttle_power_s=1.0,
            throttle_thermal_s=0.0,
            throttle_hw_s=0.0,
        )
        for i in range(60)
    ]
    assert engine.throttle_finding(gpu, quiet, CFG, WINDOW) is None
    unknown = [minute(i, util=95.0, busy_s=60.0) for i in range(60)]
    assert engine.throttle_finding(gpu, unknown, CFG, WINDOW) is None


def test_memory_pressure_and_hardware_errors() -> None:
    gpu = ctx()
    full = [minute(i, util=90.0, mem=79_000.0, procs=1) for i in range(12)]
    assert engine.memory_pressure_finding(gpu, full, CFG, WINDOW) is not None
    assert engine.memory_pressure_finding(gpu, full[:5], CFG, WINDOW) is None
    ecc = [minute(0, ecc_max=3), minute(1, ecc_max=5, xid_count=1)]
    f = engine.errors_finding(gpu, ecc, WINDOW)
    assert (
        f is not None and f.evidence == {"ecc_new": 2, "xid_events": 1} and f.severity == "critical"
    )
    assert engine.errors_finding(gpu, [minute(0, ecc_max=3), minute(1, ecc_max=3)], WINDOW) is None


def test_health_rules_only_look_at_the_last_day() -> None:
    gpu = ctx()
    end = T0 + timedelta(days=7)
    old = [minute(i, util=90.0, mem=79_000.0, procs=1) for i in range(60)]  # day one
    found = engine.evaluate_gpu(gpu, old, CFG, (T0, end), [])
    assert not [f for f in found if f.kind == "memory_pressure"]


def test_inference_queueing_and_overprovisioning() -> None:
    ep = EndpointContext(
        uuid.uuid4(), uuid.uuid4(), "chat", "vllm", "llama", 12.0, 2_000_000.0, 1_000_000_000
    )
    minutes = [EndpointMinute(T0 + timedelta(minutes=i), 100.0, 4.0, 0.95) for i in range(20)]
    found = {f.kind: f for f in engine.inference_findings(ep, minutes, CFG, WINDOW)}
    assert found["inference_queueing"].evidence["minutes"] == 20
    over = found["inference_overprovisioned"]
    assert over.evidence["nusd_per_million_tokens"] == 500_000_000
    calm = [EndpointMinute(T0 + timedelta(minutes=i), 100.0, 0.0, 0.5) for i in range(20)]
    busy = EndpointContext(ep.id, ep.host_id, "chat", "vllm", None, 70.0, 1.0, None)
    assert engine.inference_findings(busy, calm, CFG, WINDOW) == []


def test_money_formatting() -> None:
    assert engine.usd(2_500_000_000) == "$2.50"
    assert engine.usd(1_234_567_890_000) == "$1,234.57"
    assert engine.usd(1_000_000) == "$0.0010"
    assert engine.hours(5400) == "1.5 h" and engine.hours(720_000) == "200 h"
