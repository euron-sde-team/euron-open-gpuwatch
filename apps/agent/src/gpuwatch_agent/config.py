"""Agent configuration, from the environment only (``GPUWATCH_*``)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class InferenceTarget:
    """``name=kind,url,gpu_index[+gpu_index...]``, several separated by ``;``."""

    name: str
    kind: str
    url: str
    gpu_indexes: tuple[int, ...] = ()


def parse_inference(raw: str) -> list[InferenceTarget]:
    out = []
    for item in filter(None, (p.strip() for p in raw.split(";"))):
        name, _, rest = item.partition("=")
        parts = [p.strip() for p in rest.split(",")]
        if not name or len(parts) < 2 or parts[0] not in ("vllm", "tgi"):
            raise ValueError(
                f"GPUWATCH_INFERENCE entry {item!r}: use name=vllm|tgi,url[,gpu_index+gpu_index]"
            )
        indexes = tuple(int(i) for i in parts[2].split("+") if i) if len(parts) > 2 else ()
        out.append(InferenceTarget(name.strip(), parts[0], parts[1], indexes))
    return out


def parse_labels(raw: str) -> dict[str, str]:
    labels = {}
    for item in filter(None, (p.strip() for p in raw.split(","))):
        k, _, v = item.partition("=")
        if k.strip():
            labels[k.strip()] = v.strip()
    return labels


@dataclass(frozen=True)
class AgentConfig:
    url: str
    enrolment_token: str | None
    state_dir: Path
    collector: str = "nvml"
    interval_s: float = 5.0
    dcgm_url: str = "http://localhost:9400/metrics"
    labels: dict[str, str] = field(default_factory=dict)
    inference: list[InferenceTarget] = field(default_factory=list)
    machine_id: str | None = None
    hostname: str | None = None
    sim_profile: str = "workstation"
    sim_backfill_days: int = 0
    spool_max_mb: int = 200
    timeout_s: float = 15.0

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> AgentConfig:
        e = dict(os.environ if env is None else env)
        token = e.get("GPUWATCH_ENROLMENT_TOKEN") or None
        token_file = e.get("GPUWATCH_ENROLMENT_TOKEN_FILE")
        if not token and token_file and Path(token_file).exists():
            token = Path(token_file).read_text().strip() or None
        collector = e.get("GPUWATCH_COLLECTOR", "nvml")
        if collector not in ("nvml", "dcgm", "simulated"):
            raise ValueError("GPUWATCH_COLLECTOR must be nvml, dcgm or simulated")
        interval = float(e.get("GPUWATCH_INTERVAL_S", "5"))
        if not 1 <= interval <= 300:
            raise ValueError("GPUWATCH_INTERVAL_S must be between 1 and 300")
        return cls(
            url=e.get("GPUWATCH_URL", "http://localhost:4430").rstrip("/"),
            enrolment_token=token,
            state_dir=Path(e.get("GPUWATCH_STATE_DIR", "/var/lib/gpuwatch-agent")),
            collector=collector,
            interval_s=interval,
            dcgm_url=e.get("GPUWATCH_DCGM_URL", "http://localhost:9400/metrics"),
            labels=parse_labels(e.get("GPUWATCH_LABELS", "")),
            inference=parse_inference(e.get("GPUWATCH_INFERENCE", "")),
            machine_id=e.get("GPUWATCH_MACHINE_ID") or None,
            hostname=e.get("GPUWATCH_HOSTNAME") or None,
            sim_profile=e.get("GPUWATCH_SIM_PROFILE", "workstation"),
            sim_backfill_days=int(e.get("GPUWATCH_SIM_BACKFILL_DAYS", "0")),
            spool_max_mb=int(e.get("GPUWATCH_SPOOL_MAX_MB", "200")),
            timeout_s=float(e.get("GPUWATCH_TIMEOUT_S", "15")),
        )
