"""Deterministic scenarios for the demo and the tests.

Everything is a pure function of (machine, GPU, time), so a 30-day backfill and the live feed
tell one consistent story, and two runs produce identical data. Scenarios model what real
fleets do: a training job with a nightly checkpoint gap, notebooks that keep a model loaded
overnight, an inference server with diurnal traffic that queues at peak, an oversized card
and a spare one, a workstation that hits its power cap. Fields a real driver would not
report on that hardware stay ``None`` (fan speed on passively cooled data centre cards, ECC
and per-process SM share on a consumer card).
"""

from __future__ import annotations

import hashlib
import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

THROTTLE_IDLE = 0x1
THROTTLE_SW_POWER_CAP = 0x4
THROTTLE_SW_THERMAL = 0x20

_NAMESPACE = uuid.UUID("6f1c3c3e-2b7a-4c1e-9d55-1f0e2a7b9c11")


def noise(*key: object) -> float:
    """A stable pseudo-random number in [0, 1) for a key."""
    digest = hashlib.blake2b(repr(key).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2**64


def gpu_uuid(machine: str, index: int) -> str:
    return f"GPU-{uuid.uuid5(_NAMESPACE, f'{machine}:{index}')}"


def _hour(t: float) -> float:
    return (t % 86400) / 3600


def _weekday(t: float) -> int:
    return datetime.fromtimestamp(t, UTC).weekday()


def _day(t: float) -> int:
    return int(t // 86400)


@dataclass(frozen=True)
class Proc:
    pid: int
    name: str
    username: str
    container_id: str | None
    mem_mib: float
    sm: float | None


@dataclass(frozen=True)
class State:
    util: float
    mem_mib: float
    procs: tuple[Proc, ...] = ()
    temp_bias: float = 0.0
    xid: int | None = None
    # Above 1: draws more than its limit allows when busy, so the driver caps power.
    power_pull: float = 1.0


@dataclass(frozen=True)
class GpuSpec:
    index: int
    name: str
    memory_mib: float
    power_limit_w: float
    idle_w: float
    boost_mhz: float
    mem_mhz: float
    fan: bool
    ecc: bool
    process_sm: bool
    behave: Callable[[float], State] = field(compare=False)


# ── inference load ───────────────────────────────────────────────────────────


def chat_load(t: float) -> float:
    """Share of peak traffic for the chat model: business-hours bell, quieter weekends."""
    h = _hour(t)
    bell = math.exp(-(((h - 15.0) / 3.6) ** 2))
    load = 0.12 + 0.86 * bell
    if _weekday(t) >= 5:
        load *= 0.45
    load += (noise("chat", int(t // 60)) - 0.5) * 0.08
    return min(1.0, max(0.03, load))


def summarizer_load(t: float) -> float:
    h = _hour(t)
    load = 0.1 + 0.5 * math.exp(-(((h - 11.0) / 4.0) ** 2))
    if _weekday(t) >= 5:
        load *= 0.4
    return min(1.0, max(0.02, load + (noise("sum", int(t // 60)) - 0.5) * 0.05))


# ── profiles ─────────────────────────────────────────────────────────────────

_TRAIN_CONTAINER = "a3f9c2d17b04"


def _training_job(index: int) -> Callable[[float], State]:
    def behave(t: float) -> State:
        h = _hour(t)
        n = noise("train", index, int(t // 5))
        if 1.0 <= h < 22.0:
            util = 93 + 6 * n
            mem = 74_200 + 900 * noise("train-mem", index, int(t // 600))
            hot = 16.0 if index == 3 and 12.0 <= h < 17.0 else 0.0
            procs = (Proc(41_200 + index, "python3", "ml", _TRAIN_CONTAINER, mem, util),)
            xid = 13 if index == 5 and _day(t) % 2 == 0 and int(t % 86400) // 60 == 4 * 60 else None
            return State(util, mem, procs, temp_bias=hot, xid=xid)
        if 22.0 <= h < 23.5:
            # Checkpoint written; the job waits for evaluation with weights still loaded.
            mem = 71_800.0
            return State(
                1.5 * n, mem, (Proc(41_200 + index, "python3", "ml", _TRAIN_CONTAINER, mem, 0.0),)
            )
        return State(0.0, 0.0)

    return behave


def _notebook(index: int, user: str) -> Callable[[float], State]:
    def behave(t: float) -> State:
        h = _hour(t)
        mem = 31_000 + 400 * noise("nb-mem", index, _day(t))
        working = _weekday(t) < 5 and 9.0 <= h < 18.0
        burst = working and noise("nb", index, int(t // 900)) > 0.55
        n = noise("nb-u", index, int(t // 5))
        util = 45 + 30 * n if burst else 1.0 * n
        return State(util, mem, (Proc(52_000 + index, "ipykernel", user, None, mem, util),))

    return behave


def _vllm(t: float) -> State:
    load = chat_load(t)
    util = min(99.0, 16 + 80 * load + 4 * (noise("vllm", int(t // 5)) - 0.5))
    mem = 41_460.0  # vLLM preallocates ~90% of memory for the KV cache
    return State(util, mem, (Proc(7_301, "vllm", "svc-llm", "5c1e0a9b3f22", mem, util),))


def _summarizer(t: float) -> State:
    load = summarizer_load(t)
    util = 5 + 11 * load + 2 * noise("tgi", int(t // 5))
    mem = 14_200.0
    return State(util, mem, (Proc(7_402, "text-generation", "svc-llm", "9d04b6e2a1c7", mem, util),))


def _scoring(t: float) -> State:
    minute = int(t % 3600) // 60
    if 10 <= minute < 25:
        util = 82 + 8 * noise("score", int(t // 5))
        mem = 9_800.0
        return State(
            util, mem, (Proc(8_800 + _day(t) % 50, "score-worker", "batch", None, mem, util),)
        )
    return State(0.0, 0.0)


def _spare(_: float) -> State:
    return State(0.0, 0.0)


def _workstation(t: float) -> State:
    h = _hour(t)
    working_day = _weekday(t) < 5 and 8.5 <= h < 18.5
    # A night runs 18:30 to 08:30; after a weekday, the model stays loaded two nights in three.
    night_of = int((t - 18.5 * 3600) // 86400)
    in_night = h >= 18.5 or h < 8.5
    night_after_weekday = _weekday(night_of * 86400 + 43200) < 5
    left_loaded = noise("ws-night", night_of) < 0.66
    if not (working_day or (in_night and night_after_weekday and left_loaded)):
        return State(0.0, 0.0)
    mem = 18_400.0
    burst = working_day and 9.0 <= h < 18.0 and noise("ws", int(t // 600)) > 0.5
    util = (60 + 35 * noise("ws-u", int(t // 5))) if burst else 0.4 * noise("ws-i", int(t // 5))
    return State(util, mem, (Proc(23_117, "ipykernel", "dana", None, mem, None),), power_pull=1.2)


H100 = {
    "name": "NVIDIA H100 80GB HBM3",
    "memory_mib": 81_559.0,
    "power_limit_w": 700.0,
    "idle_w": 72.0,
    "boost_mhz": 1980.0,
    "mem_mhz": 2619.0,
    "fan": False,
    "ecc": True,
    "process_sm": True,
}
L40S = {
    "name": "NVIDIA L40S",
    "memory_mib": 46_068.0,
    "power_limit_w": 350.0,
    "idle_w": 36.0,
    "boost_mhz": 2520.0,
    "mem_mhz": 9001.0,
    "fan": True,
    "ecc": True,
    "process_sm": True,
}
L4 = {
    "name": "NVIDIA L4",
    "memory_mib": 23_034.0,
    "power_limit_w": 72.0,
    "idle_w": 16.0,
    "boost_mhz": 2040.0,
    "mem_mhz": 6251.0,
    "fan": False,
    "ecc": True,
    "process_sm": True,
}
RTX4090 = {
    "name": "NVIDIA GeForce RTX 4090",
    "memory_mib": 24_564.0,
    "power_limit_w": 450.0,
    "idle_w": 21.0,
    "boost_mhz": 2520.0,
    "mem_mhz": 10501.0,
    "fan": True,
    "ecc": False,
    "process_sm": False,
}


def _spec(index: int, model: dict[str, object], behave: Callable[[float], State]) -> GpuSpec:
    return GpuSpec(index=index, behave=behave, **model)  # type: ignore[arg-type]


PROFILES: dict[str, Callable[[], list[GpuSpec]]] = {
    "training": lambda: [
        *(_spec(i, H100, _training_job(i)) for i in range(6)),
        _spec(6, H100, _notebook(6, "li")),
        _spec(7, H100, _notebook(7, "dana")),
    ],
    "inference": lambda: [
        _spec(0, L40S, _vllm),
        _spec(1, L40S, _summarizer),
        _spec(2, L4, _scoring),
        _spec(3, L4, _spare),
    ],
    "workstation": lambda: [_spec(0, RTX4090, _workstation)],
}


@dataclass(frozen=True)
class Reading:
    util: float
    mem_used: float
    temp: float
    power: float
    fan: float | None
    sm_clock: float
    mem_clock: float
    pstate: int
    throttle: int
    pcie_rx: float
    pcie_tx: float
    ecc: int | None
    state: State


def read(machine: str, spec: GpuSpec, t: float) -> Reading:
    """The physical readings that follow from a GPU's state at time ``t``."""
    st = spec.behave(t)
    n = noise(machine, spec.index, "phys", int(t // 5))
    load = st.util / 100
    power = (
        spec.idle_w
        + (spec.power_limit_w - spec.idle_w) * (load**0.9) * (0.86 + 0.1 * n) * st.power_pull
    )
    throttle = 0
    if power >= spec.power_limit_w * 0.97:
        power = spec.power_limit_w * (0.97 + 0.03 * n)
        throttle |= THROTTLE_SW_POWER_CAP
    temp = 31 + 41 * load + st.temp_bias + 2.5 * (n - 0.5)
    if temp >= 85:
        throttle |= THROTTLE_SW_THERMAL
    if st.util < 5:
        throttle |= THROTTLE_IDLE
    slowed = 0.12 if throttle & (THROTTLE_SW_POWER_CAP | THROTTLE_SW_THERMAL) else 0.0
    sm_clock = 210.0 if st.util < 5 else spec.boost_mhz * (1 - slowed) * (0.97 + 0.03 * n)
    ecc_base = 0 if spec.ecc else None
    return Reading(
        util=round(st.util, 1),
        mem_used=round(st.mem_mib + (420.0 if st.mem_mib else 0.0), 1),
        temp=round(temp, 1),
        power=round(power, 1),
        fan=round(30 + 55 * load + 5 * n, 1) if spec.fan else None,
        sm_clock=round(sm_clock),
        mem_clock=spec.mem_mhz if st.util >= 5 else 405.0,
        pstate=8 if st.util < 5 else 0,
        throttle=throttle,
        pcie_rx=round(load * 9_800_000 * (0.5 + n), 0),
        pcie_tx=round(load * 2_400_000 * (0.5 + n), 0),
        ecc=ecc_base,
        state=st,
    )


# ── inference metrics model ──────────────────────────────────────────────────

TTFT_BUCKETS = (
    0.001,
    0.005,
    0.01,
    0.02,
    0.04,
    0.06,
    0.08,
    0.1,
    0.25,
    0.5,
    0.75,
    1.0,
    2.5,
    5.0,
    7.5,
    10.0,
)
ITL_BUCKETS = (0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 2.5)
E2E_BUCKETS = (0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 2.5, 5.0, 10.0, 15.0, 20.0, 30.0, 40.0, 50.0, 60.0)


@dataclass(frozen=True)
class Traffic:
    """Rates at one moment. Latencies are log-normal medians (seconds)."""

    rps: float
    prompt_per_req: float
    gen_per_req: float
    ttft_median: float | None
    itl_median: float
    e2e_median: float
    running: float
    waiting: float
    kv_cache: float | None


def traffic(endpoint: str, t: float) -> Traffic:
    if endpoint == "summarizer":
        load = summarizer_load(t)
        rps = 1.0 + 9.0 * load
        itl = 0.018 + 0.01 * load
        e2e = 120 * itl + 0.15
        return Traffic(rps, 1_400, 120, None, itl, e2e, min(32, rps * e2e), 0.0, None)
    load = chat_load(t)
    rps = 0.4 + 22.0 * load
    pressure = max(0.0, load - 0.82)
    ttft = 0.07 + 0.25 * load + 18.0 * pressure**2
    itl = 0.021 + 0.03 * load
    e2e = ttft + 230 * itl
    waiting = 120.0 * pressure
    kv = min(0.99, 0.22 + 0.76 * load)
    return Traffic(rps, 860, 230, ttft, itl, e2e, min(256, rps * e2e), waiting, kv)


def _cdf(x: float, median: float, sigma: float = 0.5) -> float:
    return 0.5 * (1 + math.erf((math.log(x) - math.log(median)) / (sigma * math.sqrt(2))))


def buckets(count: float, median: float, bounds: tuple[float, ...]) -> dict[str, float]:
    """Expected non-cumulative bucket counts of ``count`` log-normal observations."""
    out: dict[str, float] = {}
    prev = 0.0
    for b in bounds:
        c = _cdf(b, median)
        out[_le(b)] = count * (c - prev)
        prev = c
    out["+Inf"] = count * (1 - prev)
    return out


def _le(b: float) -> str:
    return repr(float(b))
