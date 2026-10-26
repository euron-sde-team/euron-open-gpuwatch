"""Prometheus histogram arithmetic on per-interval bucket counts.

Buckets are ``{"<upper bound>": count}`` with non-cumulative counts per interval (the agent
converts the server's cumulative buckets). Sums of such maps are exact; quantiles use the
same linear interpolation as PromQL's ``histogram_quantile``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

Buckets = dict[str, float]


def _bound(key: str) -> float:
    return math.inf if key in ("+Inf", "inf", "Inf") else float(key)


def merge(maps: Iterable[dict[str, Any] | None]) -> Buckets | None:
    """Sum bucket maps; None when no input had the histogram at all."""
    out: Buckets = {}
    seen = False
    for m in maps:
        if m is None:
            continue
        seen = True
        for k, v in m.items():
            out[k] = out.get(k, 0.0) + float(v)
    return out if seen else None


def count(b: Buckets | None) -> float:
    return sum(b.values()) if b else 0.0


def quantile(q: float, b: Buckets | None) -> float | None:
    """The q-quantile in the histogram's unit, or None without observations."""
    if not b:
        return None
    items = sorted(((_bound(k), v) for k, v in b.items()), key=lambda kv: kv[0])
    total = sum(v for _, v in items)
    if total <= 0:
        return None
    rank = q * total
    cumulative = 0.0
    lower = 0.0
    for upper, n in items:
        if cumulative + n >= rank and n > 0:
            if math.isinf(upper):
                return lower  # in the open-ended bucket: the best bound known
            return lower + (upper - lower) * (rank - cumulative) / n
        cumulative += n
        if not math.isinf(upper):
            lower = upper
    return lower
