"""``gpuwatch-agent run | check``."""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from datetime import UTC, datetime
from typing import Any

from gpuwatch_agent import __version__
from gpuwatch_agent.agent import Agent, build_collector, machine_id
from gpuwatch_agent.client import SendError
from gpuwatch_agent.collectors import CollectorUnavailableError
from gpuwatch_agent.config import AgentConfig


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "msg": record.getMessage(),
        }
        for key in ("host_id", "error", "spooled"):
            if hasattr(record, key):
                base[key] = getattr(record, key)
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base)


def _run(cfg: AgentConfig) -> None:
    agent = Agent(cfg)
    stopping = {"now": False}

    def stop(*_: Any) -> None:
        stopping["now"] = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopping["now"]:
        try:
            agent.ensure_enrolled()
            break
        except SendError as exc:
            logging.getLogger("gpuwatch_agent").warning(
                "waiting to enrol", extra={"error": str(exc)}
            )
            time.sleep(5)
    if cfg.sim_backfill_days and not stopping["now"]:
        sent = agent.backfill(cfg.sim_backfill_days)
        if sent:
            logging.getLogger("gpuwatch_agent").info(
                f"backfilled {sent} hours of simulated history"
            )
    agent.run(stop=lambda: stopping["now"])


def _check(cfg: AgentConfig) -> int:
    """Read the collector once and print what would be sent (no server needed)."""
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    collector = build_collector(cfg, machine_id(cfg))
    try:
        reading = collector.read(datetime.now(UTC), cfg.interval_s)
    except CollectorUnavailableError as exc:
        print(f"collector {cfg.collector}: unavailable: {exc.message}")
        return 2
    finally:
        collector.close()
    print(f"gpuwatch-agent {__version__}, collector {cfg.collector}")
    print(f"driver {reading.driver_version or 'unknown'}, CUDA {reading.cuda_version or 'unknown'}")
    for gpu, s in zip(reading.gpus, reading.samples, strict=False):
        missing = [k for k, v in vars(s).items() if v is None and k not in ("xid",)]
        print(f"GPU {gpu.index}: {gpu.name} ({gpu.uuid})")
        print(
            f"  util {s.util_gpu}%  mem {s.mem_used_mib}/{s.mem_total_mib} MiB  "
            f"temp {s.temp_c} C  power {s.power_w} W"
        )
        print(f"  not available on this GPU: {', '.join(missing) or 'none'}")
    procs = reading.processes
    print(
        f"processes: {len(procs)}" + ("" if procs else " (none, or the driver does not list them)")
    )
    for problem in reading.problems:
        print(f"problem: {problem.code}: {problem.message}")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="gpuwatch-agent", description="Euron Open GPUWatch agent")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="collect and send forever (configured by GPUWATCH_* env)")
    sub.add_parser("check", help="read the GPUs once and print what was found")
    args = parser.parse_args(argv)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    # One line per batch every few seconds is noise; failures are logged by the agent.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    cfg = AgentConfig.from_env()
    if args.command == "check":
        sys.exit(_check(cfg))
    _run(cfg)
