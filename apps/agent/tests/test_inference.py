"""Inference scraping: vLLM and TGI text to per-interval deltas, resets, missing metrics."""

from __future__ import annotations

import threading
from datetime import UTC, datetime

import httpx
import pytest

from gpuwatch_agent import mockvllm, sim
from gpuwatch_agent.config import InferenceTarget
from gpuwatch_agent.inference import InferenceScraper, delta, snapshot

VLLM_1 = """# TYPE vllm:request_success counter
vllm:request_success_total{model_name="m",finished_reason="stop"} 90
vllm:request_success_total{model_name="m",finished_reason="length"} 10
# TYPE vllm:prompt_tokens counter
vllm:prompt_tokens_total{model_name="m"} 50000
# TYPE vllm:generation_tokens counter
vllm:generation_tokens_total{model_name="m"} 9000
# TYPE vllm:num_requests_running gauge
vllm:num_requests_running{model_name="m"} 7
# TYPE vllm:num_requests_waiting gauge
vllm:num_requests_waiting{model_name="m"} 2
# TYPE vllm:gpu_cache_usage_perc gauge
vllm:gpu_cache_usage_perc{model_name="m"} 0.81
# TYPE vllm:time_to_first_token_seconds histogram
vllm:time_to_first_token_seconds_bucket{model_name="m",le="0.1"} 60
vllm:time_to_first_token_seconds_bucket{model_name="m",le="0.5"} 95
vllm:time_to_first_token_seconds_bucket{model_name="m",le="+Inf"} 100
vllm:time_to_first_token_seconds_sum{model_name="m"} 12.5
vllm:time_to_first_token_seconds_count{model_name="m"} 100
"""
VLLM_2 = (
    VLLM_1.replace("} 90", "} 120")
    .replace("} 50000", "} 65000")
    .replace("} 9000", "} 12000")
    .replace('le="0.1"} 60', 'le="0.1"} 70')
    .replace('le="0.5"} 95', 'le="0.5"} 120')
    .replace('le="+Inf"} 100', 'le="+Inf"} 130')
)
TGI = """# TYPE tgi_request_success counter
tgi_request_success 40
# TYPE tgi_queue_size gauge
tgi_queue_size 0
# TYPE tgi_batch_current_size gauge
tgi_batch_current_size 3
# TYPE tgi_request_input_length histogram
tgi_request_input_length_bucket{le="+Inf"} 40
tgi_request_input_length_sum 12000
tgi_request_input_length_count 40
# TYPE tgi_request_generated_tokens histogram
tgi_request_generated_tokens_bucket{le="+Inf"} 40
tgi_request_generated_tokens_sum 4000
tgi_request_generated_tokens_count 40
"""


def test_vllm_snapshot_reads_counters_gauges_histograms_and_model() -> None:
    s = snapshot("vllm", VLLM_1)
    assert s.counters == {"requests": 100.0, "prompt_tokens": 50000.0, "generation_tokens": 9000.0}
    assert s.gauges == {"running": 7.0, "waiting": 2.0, "kv_cache_usage": 0.81}
    assert s.histograms["ttft"] == {"0.1": 60.0, "0.5": 95.0, "+Inf": 100.0}
    assert s.model == "m"


def test_deltas_between_scrapes_are_non_cumulative() -> None:
    first, second = snapshot("vllm", VLLM_1), snapshot("vllm", VLLM_2)
    primed = delta(None, first)
    assert primed["requests"] is None and primed["running"] == 7.0  # first scrape only primes
    d = delta(first, second)
    assert (
        d["requests"] == 30.0 and d["prompt_tokens"] == 15000.0 and d["generation_tokens"] == 3000.0
    )
    # cumulative bucket deltas 10, 25, 30 become per-bucket counts 10, 15, 5
    assert d["ttft"] == {"0.1": 10.0, "0.5": 15.0, "+Inf": 5.0}
    assert d["itl"] is None and d["e2e"] is None


def test_a_server_restart_counts_from_zero() -> None:
    before = snapshot("vllm", VLLM_2)
    after = snapshot("vllm", VLLM_1.replace("} 90", "} 3").replace("} 10\n", "} 0\n"))
    d = delta(before, after)
    assert d["requests"] == 3.0
    assert d["ttft"] == {"0.1": 60.0, "0.5": 35.0, "+Inf": 5.0}


def test_tgi_has_no_ttft_or_kv_cache() -> None:
    s = snapshot("tgi", TGI)
    assert s.counters == {"requests": 40.0, "prompt_tokens": 12000.0, "generation_tokens": 4000.0}
    d = delta(s, snapshot("tgi", TGI.replace("success 40", "success 50")))
    assert d["requests"] == 10.0 and d["ttft"] is None and d["kv_cache_usage"] is None


def test_scraper_marks_unreachable_servers_down() -> None:
    target = InferenceTarget("chat", "vllm", "http://127.0.0.1:9/metrics", (0,))
    scraper = InferenceScraper([target], client=httpx.Client(timeout=0.5))
    (row,) = scraper.scrape(datetime.now(UTC), 5.0, {0: "GPU-x"})
    assert row["up"] is False and row["gpu_uuids"] == ["GPU-x"]


@pytest.fixture
def mock_server() -> str:  # type: ignore[misc]
    server = mockvllm.serve("127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_the_mock_server_round_trips_through_the_real_scraper(mock_server: str) -> None:
    scraper = InferenceScraper(
        [
            InferenceTarget("chat", "vllm", f"{mock_server}/metrics", (0,)),
            InferenceTarget("sum", "tgi", f"{mock_server}/tgi/metrics", (1,)),
        ]
    )
    t = datetime.now(UTC)
    scraper.scrape(t, 5.0, {0: "GPU-a", 1: "GPU-b"})
    import time

    time.sleep(1.1)
    chat, summ = scraper.scrape(t, 5.0, {0: "GPU-a", 1: "GPU-b"})
    assert chat["up"] and chat["model"] == mockvllm.VLLM_MODEL
    assert chat["requests"] is not None and chat["ttft"] is not None
    assert summ["up"] and summ["ttft"] is None and summ["kv_cache_usage"] is None
    assert httpx.get(f"{mock_server}/health").text == "ok"
    assert httpx.get(f"{mock_server}/nope").status_code == 404


def test_simulated_buckets_conserve_the_count() -> None:
    b = sim.buckets(1000.0, 0.2, sim.TTFT_BUCKETS)
    assert sum(b.values()) == pytest.approx(1000.0)
    assert b["+Inf"] < 1.0
