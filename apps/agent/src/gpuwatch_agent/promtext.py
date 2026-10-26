"""Prometheus text exposition parsing (DCGM exporter, vLLM, TGI)."""

from __future__ import annotations

from dataclasses import dataclass

from prometheus_client.parser import text_string_to_metric_families


@dataclass(frozen=True)
class Sample:
    name: str
    labels: dict[str, str]
    value: float


def parse(text: str) -> list[Sample]:
    out = []
    for family in text_string_to_metric_families(text):
        for s in family.samples:
            out.append(Sample(s.name, dict(s.labels), float(s.value)))
    return out


def by_name(samples: list[Sample]) -> dict[str, list[Sample]]:
    out: dict[str, list[Sample]] = {}
    for s in samples:
        out.setdefault(s.name, []).append(s)
    return out
