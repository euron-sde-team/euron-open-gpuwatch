"""Inference server scraping: vLLM and TGI ``/metrics`` to per-interval deltas.

Servers expose cumulative counters and cumulative histogram buckets. The agent keeps the
previous scrape and sends the difference, so the server can sum rows exactly. A counter
that went down means the server restarted: the new value is the delta since the restart.
Metrics a server does not expose are ``None`` (TGI has no time-to-first-token histogram
and no KV cache gauge), shown as "Not available", never as 0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from gpuwatch_agent import promtext
from gpuwatch_agent.config import InferenceTarget

# Field -> metric names, newest first (names changed between server versions).
VLLM = {
    "requests": ("vllm:request_success_total",),
    "prompt_tokens": ("vllm:prompt_tokens_total",),
    "generation_tokens": ("vllm:generation_tokens_total",),
    "running": ("vllm:num_requests_running",),
    "waiting": ("vllm:num_requests_waiting",),
    "kv_cache_usage": ("vllm:kv_cache_usage_perc", "vllm:gpu_cache_usage_perc"),
    "ttft": ("vllm:time_to_first_token_seconds",),
    "itl": ("vllm:inter_token_latency_seconds", "vllm:time_per_output_token_seconds"),
    "e2e": ("vllm:e2e_request_latency_seconds",),
}
TGI = {
    "requests": ("tgi_request_success",),
    "prompt_tokens": ("tgi_request_input_length_sum",),
    "generation_tokens": ("tgi_request_generated_tokens_sum",),
    "running": ("tgi_batch_current_size",),
    "waiting": ("tgi_queue_size",),
    "itl": ("tgi_request_mean_time_per_token_duration",),
    "e2e": ("tgi_request_duration",),
}
COUNTERS = ("requests", "prompt_tokens", "generation_tokens")
GAUGES = ("running", "waiting", "kv_cache_usage")
HISTOGRAMS = ("ttft", "itl", "e2e")


@dataclass
class Snapshot:
    counters: dict[str, float] = field(default_factory=dict)
    gauges: dict[str, float] = field(default_factory=dict)
    # field -> cumulative bucket counts by upper bound (as written by the server)
    histograms: dict[str, dict[str, float]] = field(default_factory=dict)
    model: str | None = None


def _sum_named(
    samples: dict[str, list[promtext.Sample]], names: tuple[str, ...], suffix: str = ""
) -> float | None:
    for name in names:
        rows = samples.get(name + suffix)
        if rows:
            return sum(r.value for r in rows)
    return None


def _buckets(
    samples: dict[str, list[promtext.Sample]], names: tuple[str, ...]
) -> dict[str, float] | None:
    for name in names:
        rows = samples.get(name + "_bucket")
        if rows:
            out: dict[str, float] = {}
            for r in rows:
                le = r.labels.get("le", "+Inf")
                out[le] = out.get(le, 0.0) + r.value
            return out
    return None


def snapshot(kind: str, text: str) -> Snapshot:
    table = VLLM if kind == "vllm" else TGI
    parsed = promtext.parse(text)
    samples = promtext.by_name(parsed)
    snap = Snapshot()
    for f in COUNTERS:
        names = table.get(f)
        if names:
            # prometheus_client strips "_total" from family names but keeps it on samples.
            value = _sum_named(samples, names)
            if value is None and not names[0].endswith(("_sum", "_total")):
                value = _sum_named(samples, names, "_total")
            if value is not None:
                snap.counters[f] = value
    for f in GAUGES:
        names = table.get(f)
        value = _sum_named(samples, names) if names else None
        if value is not None:
            snap.gauges[f] = value
    for f in HISTOGRAMS:
        names = table.get(f)
        b = _buckets(samples, names) if names else None
        if b is not None:
            snap.histograms[f] = b
    for s in parsed:
        model = s.labels.get("model_name") or s.labels.get("model")
        if model:
            snap.model = model
            break
    return snap


def _bound(le: str) -> float:
    return math.inf if le in ("+Inf", "inf", "Inf") else float(le)


def delta(prev: Snapshot | None, cur: Snapshot) -> dict[str, Any]:
    """Per-interval fields for one scrape. The first scrape only primes the counters."""
    out: dict[str, Any] = {f: cur.gauges.get(f) for f in GAUGES}
    if prev is None:
        out.update(dict.fromkeys((*COUNTERS, *HISTOGRAMS)))
        return out
    reset = any(cur.counters.get(f, 0.0) < prev.counters.get(f, 0.0) for f in cur.counters)
    for f in COUNTERS:
        if f not in cur.counters:
            out[f] = None
            continue
        before = 0.0 if reset else prev.counters.get(f, 0.0)
        out[f] = max(0.0, cur.counters[f] - before)
    for f in HISTOGRAMS:
        now_b = cur.histograms.get(f)
        if now_b is None:
            out[f] = None
            continue
        before_b = {} if reset else prev.histograms.get(f, {})
        cumulative = sorted(
            ((le, max(0.0, v - before_b.get(le, 0.0))) for le, v in now_b.items()),
            key=lambda kv: _bound(kv[0]),
        )
        buckets: dict[str, float] = {}
        last = 0.0
        for le, c in cumulative:
            buckets[le] = max(0.0, c - last)
            last = max(last, c)
        out[f] = buckets
    return out


class InferenceScraper:
    def __init__(self, targets: list[InferenceTarget], client: httpx.Client | None = None) -> None:
        self.targets = targets
        self._client = client or httpx.Client(timeout=4.0)
        self._prev: dict[str, Snapshot] = {}

    def scrape(
        self, now: datetime, interval_s: float, uuid_for_index: dict[int, str]
    ) -> list[dict[str, Any]]:
        rows = []
        for t in self.targets:
            row: dict[str, Any] = {
                "endpoint": t.name,
                "kind": t.kind,
                "url": t.url,
                "gpu_uuids": [uuid_for_index[i] for i in t.gpu_indexes if i in uuid_for_index],
                "ts": now.isoformat(),
                "interval_s": interval_s,
            }
            try:
                response = self._client.get(t.url)
                response.raise_for_status()
                cur = snapshot(t.kind, response.text)
            except (httpx.HTTPError, ValueError):
                self._prev.pop(t.name, None)
                rows.append({**row, "up": False})
                continue
            row.update(delta(self._prev.get(t.name), cur))
            row["model"] = cur.model
            row["up"] = True
            self._prev[t.name] = cur
            rows.append(row)
        return rows

    def close(self) -> None:
        self._client.close()
