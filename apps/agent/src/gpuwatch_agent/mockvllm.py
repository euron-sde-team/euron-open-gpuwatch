"""A vLLM- and TGI-compatible ``/metrics`` endpoint for the demo and the tests.

Counters and histogram buckets grow with the same traffic model the simulated inference
host follows (``sim.traffic``), so GPU utilization and serving metrics move together. Metric
names follow vLLM's and TGI's documented Prometheus metrics.

    gpuwatch-mock-vllm --port 4450     # /metrics (vLLM), /tgi/metrics (TGI), /health
"""

from __future__ import annotations

import argparse
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from gpuwatch_agent import sim

VLLM_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
TGI_MODEL = "google/flan-t5-xl"


class Counters:
    """Cumulative state of one server, advanced to "now" on every scrape."""

    def __init__(self, endpoint: str, clock: Callable[[], float] = time.time) -> None:
        self.endpoint = endpoint
        self.clock = clock
        self.at = clock()
        self.requests = 0.0
        self.prompt = 0.0
        self.generation = 0.0
        self.ttft: dict[str, float] = {}
        self.itl: dict[str, float] = {}
        self.e2e: dict[str, float] = {}
        self.lock = threading.Lock()
        self.last = sim.traffic(endpoint, self.at)

    def advance(self) -> sim.Traffic:
        with self.lock:
            now = self.clock()
            dt = max(0.0, now - self.at)
            tr = sim.traffic(self.endpoint, now)
            n = tr.rps * dt
            self.requests += n
            self.prompt += n * tr.prompt_per_req
            self.generation += n * tr.gen_per_req
            if tr.ttft_median:
                _add(self.ttft, sim.buckets(n, tr.ttft_median, sim.TTFT_BUCKETS))
            _add(self.itl, sim.buckets(n * tr.gen_per_req, tr.itl_median, sim.ITL_BUCKETS))
            _add(self.e2e, sim.buckets(n, tr.e2e_median, sim.E2E_BUCKETS))
            self.at = now
            self.last = tr
            return tr


def _add(into: dict[str, float], delta: dict[str, float]) -> None:
    for k, v in delta.items():
        into[k] = into.get(k, 0.0) + v


def _histogram(name: str, labels: str, buckets: dict[str, float], total_sum: float) -> list[str]:
    lines = [f"# TYPE {name} histogram"]
    cumulative = 0.0
    keys = [*sorted((k for k in buckets if k != "+Inf"), key=float), "+Inf"]
    for k in keys:
        cumulative += buckets.get(k, 0.0)
        lines.append(f'{name}_bucket{{{labels},le="{k}"}} {round(cumulative)}')
    lines.append(f"{name}_sum{{{labels}}} {total_sum:.3f}")
    lines.append(f"{name}_count{{{labels}}} {round(cumulative)}")
    return lines


def vllm_text(c: Counters) -> str:
    tr = c.advance()
    labels = f'model_name="{VLLM_MODEL}"'
    lines = [
        "# TYPE vllm:num_requests_running gauge",
        f"vllm:num_requests_running{{{labels}}} {tr.running:.0f}",
        "# TYPE vllm:num_requests_waiting gauge",
        f"vllm:num_requests_waiting{{{labels}}} {tr.waiting:.0f}",
        "# TYPE vllm:kv_cache_usage_perc gauge",
        f"vllm:kv_cache_usage_perc{{{labels}}} {tr.kv_cache or 0:.4f}",
        "# TYPE vllm:request_success counter",
        f'vllm:request_success_total{{{labels},finished_reason="stop"}} {round(c.requests * 0.93)}',
        f'vllm:request_success_total{{{labels},finished_reason="length"}} '
        f"{round(c.requests * 0.07)}",
        "# TYPE vllm:prompt_tokens counter",
        f"vllm:prompt_tokens_total{{{labels}}} {round(c.prompt)}",
        "# TYPE vllm:generation_tokens counter",
        f"vllm:generation_tokens_total{{{labels}}} {round(c.generation)}",
    ]
    lines += _histogram(
        "vllm:time_to_first_token_seconds",
        labels,
        c.ttft,
        c.requests * tr.ttft_median if tr.ttft_median else 0,
    )
    lines += _histogram(
        "vllm:inter_token_latency_seconds", labels, c.itl, c.generation * tr.itl_median
    )
    lines += _histogram(
        "vllm:e2e_request_latency_seconds", labels, c.e2e, c.requests * tr.e2e_median
    )
    return "\n".join(lines) + "\n"


def tgi_text(c: Counters) -> str:
    tr = c.advance()
    lines = [
        "# TYPE tgi_request_success counter",
        f"tgi_request_success {round(c.requests)}",
        "# TYPE tgi_queue_size gauge",
        f"tgi_queue_size {tr.waiting:.0f}",
        "# TYPE tgi_batch_current_size gauge",
        f"tgi_batch_current_size {tr.running:.0f}",
        "# TYPE tgi_request_input_length histogram",
        f'tgi_request_input_length_bucket{{le="+Inf"}} {round(c.requests)}',
        f"tgi_request_input_length_sum {round(c.prompt)}",
        f"tgi_request_input_length_count {round(c.requests)}",
        "# TYPE tgi_request_generated_tokens histogram",
        f'tgi_request_generated_tokens_bucket{{le="+Inf"}} {round(c.requests)}',
        f"tgi_request_generated_tokens_sum {round(c.generation)}",
        f"tgi_request_generated_tokens_count {round(c.requests)}",
    ]
    lines += [
        line.replace("{,", "{")
        for line in _histogram(
            "tgi_request_mean_time_per_token_duration", "", c.itl, c.generation * tr.itl_median
        )
    ]
    lines += [
        line.replace("{,", "{")
        for line in _histogram("tgi_request_duration", "", c.e2e, c.requests * tr.e2e_median)
    ]
    return "\n".join(lines).replace("{}", "") + "\n"


def make_handler(vllm: Counters, tgi: Counters) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/metrics":
                body = vllm_text(vllm).encode()
            elif self.path == "/tgi/metrics":
                body = tgi_text(tgi).encode()
            elif self.path == "/health":
                body = b"ok"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("content-type", "text/plain; version=0.0.4")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            return None

    return Handler


def serve(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(Counters("chat"), Counters("summarizer")))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="gpuwatch-mock-vllm")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=4450)
    args = p.parse_args(argv)
    server = serve(args.host, args.port)
    print(f"mock vLLM on :{args.port} (/metrics, /tgi/metrics)", flush=True)
    server.serve_forever()
