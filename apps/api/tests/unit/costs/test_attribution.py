"""Attribution and exact splitting: every second and every nano-dollar lands somewhere."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from gpuwatch.costs.attribution import (
    UNATTRIBUTED,
    Proc,
    Rule,
    Sample,
    attribute,
    classify,
    compile_rules,
)
from gpuwatch.costs.models import IDLE_WORKLOAD, WorkloadRule
from gpuwatch.costs.rates import pick, seconds_cost
from gpuwatch.costs.service import split

G = uuid.uuid4()
H = uuid.uuid4()
T0 = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


def proc(
    pid: int,
    name: str,
    sm: float | None = None,
    mem: float | None = None,
    user: str | None = None,
    container: str | None = None,
) -> Proc:
    return Proc(pid, name, user, container, mem, sm)


def rule(**kw: object) -> WorkloadRule:
    base: dict[str, object] = {
        "priority": 100,
        "workload": "w",
        "team": None,
        "process_pattern": None,
        "container_prefix": None,
        "username": None,
        "host_label": None,
        "enabled": True,
    }
    base.update(kw)
    return WorkloadRule(**base)


def test_split_is_exact_and_proportional() -> None:
    assert split(10, [1, 1, 1]) == [4, 3, 3]
    assert split(0, [1, 2]) == [0, 0]
    assert split(7, [0, 0]) == [0, 0]
    rng = random.Random(7)
    for _ in range(500):
        total = rng.randint(0, 10**12)
        weights = [rng.random() for _ in range(rng.randint(1, 9))]
        parts = split(total, weights)
        assert sum(parts) == total
        exact = [total * w / sum(weights) for w in weights]
        assert all(abs(p - e) < 1 for p, e in zip(parts, exact, strict=True))


def test_samples_split_by_sm_share_then_memory_then_equally() -> None:
    by_sm = attribute(
        [Sample(G, H, T0, 60.0, 90.0)],
        {(G, T0): [proc(1, "a", sm=30), proc(2, "b", sm=10)]},
        [],
        {},
        5.0,
    )
    assert by_sm[(G, T0, "a")][2] == pytest.approx(45.0) and by_sm[(G, T0, "b")][
        2
    ] == pytest.approx(15.0)
    by_mem = attribute(
        [Sample(G, H, T0, 60.0, 90.0)],
        {(G, T0): [proc(1, "a", mem=3000), proc(2, "b", mem=1000)]},
        [],
        {},
        5.0,
    )
    assert by_mem[(G, T0, "a")][2] == pytest.approx(45.0)
    equal = attribute(
        [Sample(G, H, T0, 60.0, 90.0)], {(G, T0): [proc(1, "a"), proc(2, "b")]}, [], {}, 5.0
    )
    assert equal[(G, T0, "a")][2] == pytest.approx(30.0)


def test_empty_gpus_are_idle_unless_busy() -> None:
    usage = attribute(
        [
            Sample(G, H, T0, 60.0, 0.0),
            Sample(G, H, T0 + timedelta(minutes=1), 60.0, 95.0),
            Sample(G, H, T0 + timedelta(minutes=2), 60.0, None),
        ],
        {},
        [],
        {},
        5.0,
    )
    assert usage[(G, T0, IDLE_WORKLOAD)][2:] == [120.0, 120.0]
    assert usage[(G, T0, UNATTRIBUTED)][2:] == [60.0, 0.0]


def test_held_idle_time_is_counted_inside_the_workload() -> None:
    t = [T0 + timedelta(minutes=i) for i in range(3)]
    samples = [
        Sample(G, H, t[0], 60.0, 1.0),
        Sample(G, H, t[1], 60.0, 80.0),
        Sample(G, H, t[2], 60.0, 2.0),
    ]
    procs = {(G, ts): [proc(1, "vllm")] for ts in t}
    usage = attribute(samples, procs, [], {}, 5.0)
    assert usage[(G, T0, "vllm")][2:] == [180.0, 120.0]


def test_seconds_add_up_per_gpu_hour() -> None:
    rng = random.Random(3)
    samples, procs = [], {}
    for i in range(500):
        ts = T0 + timedelta(seconds=17 * i)
        samples.append(Sample(G, H, ts, rng.uniform(1, 30), rng.choice([None, 0.0, 3.0, 60.0])))
        procs[(G, ts)] = [
            proc(p, rng.choice("abc"), sm=rng.choice([None, 0.0, 12.0]))
            for p in range(rng.randint(0, 3))
        ]
    usage = attribute(samples, procs, [], {}, 5.0)
    for hour in {s.ts.replace(minute=0, second=0) for s in samples}:
        expected = sum(s.interval_s for s in samples if s.ts.replace(minute=0, second=0) == hour)
        got = sum(v[2] for (g, b, _w), v in usage.items() if b == hour)
        assert got == pytest.approx(expected)


def test_rules_match_on_every_set_condition_in_priority_order() -> None:
    rules = compile_rules(
        [
            rule(priority=20, workload="any-python", process_pattern="^python"),
            rule(
                priority=10,
                workload="prod-train",
                team="ML",
                process_pattern="^python",
                host_label="env=prod",
            ),
            rule(
                priority=5, workload="never", process_pattern="(", enabled=True
            ),  # invalid: skipped
            rule(priority=1, workload="off", process_pattern="python", enabled=False),
            rule(priority=30, workload="svc", username="svc", container_prefix="abc"),
        ]
    )
    assert [r.workload for r in rules] == ["prod-train", "any-python", "svc"]
    assert classify(proc(1, "python3"), rules, {"env": "prod"}) == ("prod-train", "ML")
    assert classify(proc(1, "python3"), rules, {"env": "dev"}) == ("any-python", None)
    assert classify(proc(1, "x", user="svc", container="abc123"), rules, {}) == ("svc", None)
    assert classify(proc(1, "x", user="svc", container="zzz"), rules, {}) == ("x", None)


def test_rule_host_label_parsing() -> None:
    (r,) = compile_rules([rule(host_label="site = dc 1 ", process_pattern=".")])
    assert isinstance(r, Rule) and r.host_label == ("site", "dc 1")


def test_rate_precedence_and_cost() -> None:
    g, h = uuid.uuid4(), uuid.uuid4()
    assert pick(g, h, "L4", {g: 1}, {h: 2}, {"L4": 3}).scope == "gpu"  # type: ignore[union-attr]
    assert pick(g, h, "L4", {}, {h: 2}, {"L4": 3}).nusd_per_hour == 2  # type: ignore[union-attr]
    assert pick(g, h, "L4", {}, {}, {"L4": 3}).scope == "model"  # type: ignore[union-attr]
    assert pick(g, h, "L4", {}, {}, {}) is None
    assert seconds_cost(1800, 3_000_000_000) == 1_500_000_000


def test_overlapping_samples_never_bill_more_than_an_hour_per_gpu_hour() -> None:
    # Two agents report the same GPU during a rollout: 2 x 720 samples of 5 s in one hour.
    samples = [
        Sample(G, H, T0 + timedelta(seconds=5 * i), 5.0, 90.0) for i in range(720) for _ in (0, 1)
    ]
    procs = {(G, s.ts): [proc(1, "python3", sm=90)] for s in samples}
    usage = attribute(samples, procs, [], {}, 5.0)
    assert sum(row[2] for row in usage.values()) == pytest.approx(3600.0)


def test_processes_without_a_utilization_reading_are_working_not_held_idle() -> None:
    s = Sample(G, H, T0, 60.0, None)
    working = attribute([s], {(G, T0): [proc(1, "python3", mem=4096)]}, [], {}, 5.0)
    assert [(k[2], row[2], row[3]) for k, row in working.items()] == [("python3", 60.0, 0.0)]
    empty = attribute([s], {}, [], {}, 5.0)
    assert [(k[2], row[3]) for k, row in empty.items()] == [(IDLE_WORKLOAD, 60.0)]
