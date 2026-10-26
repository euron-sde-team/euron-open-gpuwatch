"""The agent wire contract: odd readings become NULL, structural errors are refused."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from gpuwatch.ingest.schemas import GpuSampleIn, InferenceIn

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def sample(**metrics: Any) -> GpuSampleIn:
    return GpuSampleIn.model_validate({"gpu_uuid": "GPU-1", "ts": NOW, "interval_s": 5, **metrics})


def test_readings_no_gpu_can_report_become_null_instead_of_refusing_the_batch() -> None:
    s = sample(power_w=1.7e308, util_gpu=250, temp_c=-300, sm_clock_mhz=math.inf, mem_used_mib=-1)
    assert (s.power_w, s.util_gpu, s.temp_c, s.sm_clock_mhz, s.mem_used_mib) == (None,) * 5
    assert sample(util_gpu=math.nan).util_gpu is None
    assert sample(xid=2**40).xid is None and sample(pstate=99).pstate is None


def test_plausible_readings_are_kept_as_sent() -> None:
    # NVML documents fan speeds above 100% on some boards.
    s = sample(fan_pct=110, power_w=699.5, temp_c=86.4, util_gpu=0, xid=79, pstate=0)
    assert (s.fan_pct, s.power_w, s.temp_c, s.util_gpu, s.xid, s.pstate) == (
        110,
        699.5,
        86.4,
        0,
        79,
        0,
    )


def test_structural_fields_are_still_refused() -> None:
    with pytest.raises(ValidationError):
        sample(interval_s=0)
    with pytest.raises(ValidationError):
        sample(util_gpu="high")
    # A timestamp without a zone is ambiguous; agents always send UTC.
    with pytest.raises(ValidationError):
        GpuSampleIn.model_validate(
            {"gpu_uuid": "GPU-1", "ts": "2026-10-26T12:00:00", "interval_s": 5}
        )


def inference(**fields: Any) -> InferenceIn:
    base = {"endpoint": "chat", "kind": "vllm", "url": "http://x/metrics", "ts": NOW}
    return InferenceIn.model_validate({**base, "interval_s": 5, "up": True, **fields})


def test_histogram_buckets_must_be_numbers_or_plus_inf() -> None:
    ok = inference(ttft={"0.1": 3, "1": 7, "+Inf": 9})
    assert ok.ttft == {"0.1": 3, "1": 7, "+Inf": 9}
    with pytest.raises(ValidationError):
        inference(ttft={"abc": 1})


def test_inference_gauges_out_of_range_become_null() -> None:
    i = inference(kv_cache_usage=1.5, running=math.nan, requests=12)
    assert (i.kv_cache_usage, i.running, i.requests) == (None, None, 12)
