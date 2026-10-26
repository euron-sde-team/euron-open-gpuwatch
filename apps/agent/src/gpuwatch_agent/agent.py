"""The agent loop.

Every interval: read the collector, scrape inference servers, send one batch. If the server
cannot take it, the batch goes to the disk spool and is replayed (oldest first) once the
server answers again. The agent never opens a port and never runs anything it receives:
the only thing the server can tell it is how long to wait.
"""

from __future__ import annotations

import logging
import os
import platform
import socket
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from gpuwatch_agent import __version__, sim
from gpuwatch_agent.client import Client, SendError
from gpuwatch_agent.collectors import Collector, CollectorUnavailableError
from gpuwatch_agent.config import AgentConfig
from gpuwatch_agent.inference import InferenceScraper
from gpuwatch_agent.model import Problem, Reading, to_json
from gpuwatch_agent.spool import Spool

log = logging.getLogger("gpuwatch_agent")
REPLAY_PER_TICK = 20
# After a refused enrolment (revoked machine, expired token), wait this long before asking again.
ENROL_BACKOFF_S = 300.0


def machine_id(cfg: AgentConfig) -> str:
    if cfg.machine_id:
        return cfg.machine_id
    for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        try:
            value = path.read_text().strip()
        except OSError:
            continue
        if value:
            return value
    stored = cfg.state_dir / "machine-id"
    if stored.exists():
        return stored.read_text().strip()
    value = uuid.uuid4().hex
    stored.write_text(value)
    return value


def build_collector(cfg: AgentConfig, machine: str) -> Collector:
    if cfg.collector == "simulated":
        from gpuwatch_agent.collectors.simulated import SimulatedCollector

        return SimulatedCollector(machine, cfg.sim_profile)
    if cfg.collector == "dcgm":
        from gpuwatch_agent.collectors.dcgm import DcgmCollector

        return DcgmCollector(cfg.dcgm_url)
    from gpuwatch_agent.collectors.nvml import NvmlCollector

    return NvmlCollector()


class Agent:
    def __init__(
        self,
        cfg: AgentConfig,
        collector: Collector | None = None,
        client: Client | None = None,
        scraper: InferenceScraper | None = None,
    ) -> None:
        self.cfg = cfg
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        self.machine = machine_id(cfg)
        self.hostname = cfg.hostname or socket.gethostname()
        self.collector = collector or build_collector(cfg, self.machine)
        self.client = client or Client(cfg.url, cfg.timeout_s)
        self.scraper = scraper or (InferenceScraper(cfg.inference) if cfg.inference else None)
        self.spool = Spool(cfg.state_dir / "spool", cfg.spool_max_mb * 1024 * 1024)
        self._token_file = cfg.state_dir / "host-token"
        self._last_read: datetime | None = None
        self._uuid_for_index: dict[int, str] = {}
        self._enrol_retry_at = 0.0
        if self._token_file.exists():
            self.client.token = self._token_file.read_text().strip() or None

    # ── enrolment ────────────────────────────────────────────────────────────

    def enrol(self) -> None:
        if not self.cfg.enrolment_token:
            raise SendError(
                "No host token and no GPUWATCH_ENROLMENT_TOKEN: create one in GPUWatch, "
                "Hosts, Add a host",
                retry=True,
            )
        if time.monotonic() < self._enrol_retry_at:
            raise SendError("enrolment was refused; trying again later", retry=False)
        try:
            result = self.client.enrol(
                self.cfg.enrolment_token, self.machine, self.hostname, self.cfg.labels
            )
        except SendError as exc:
            if not exc.retry:
                # Refused (a revoked machine, an expired token): ask again in a while
                # rather than on every interval.
                self._enrol_retry_at = time.monotonic() + ENROL_BACKOFF_S
                log.error("enrolment refused", extra={"error": str(exc)})
            raise
        # Created owner-only, so the token is never readable by others, even briefly.
        fd = os.open(self._token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(result.host_token)
        os.chmod(self._token_file, 0o600)
        log.info("enrolled", extra={"host_id": result.host_id})

    def ensure_enrolled(self) -> None:
        if not self.client.token:
            self.enrol()

    # ── one interval ─────────────────────────────────────────────────────────

    def collect(self, now: datetime) -> dict[str, Any]:
        interval = self.cfg.interval_s
        if self._last_read is not None:
            # The reading stands for the time since the last one (capped, so a long pause
            # never attributes hours to one sample).
            interval = min(
                max((now - self._last_read).total_seconds(), 0.5), 3 * self.cfg.interval_s
            )
        self._last_read = now
        status = "ok"
        try:
            reading = self.collector.read(now, interval)
        except CollectorUnavailableError as exc:
            reading = Reading(problems=[Problem(exc.code, exc.message)])
        if reading.problems:
            status = "degraded"
        self._uuid_for_index = {g.index: g.uuid for g in reading.gpus}
        inference = self.scraper.scrape(now, interval, self._uuid_for_index) if self.scraper else []
        return self.batch(reading, status, inference)

    def batch(
        self, reading: Reading, status: str, inference: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "batch_id": str(uuid.uuid4()),
            "agent": {
                "version": __version__,
                "collector": self.collector.name,
                "hostname": self.hostname,
                "os": f"{platform.system()} {platform.release()}"[:120],
                "kernel": platform.version()[:120],
                "driver_version": reading.driver_version,
                "cuda_version": reading.cuda_version,
                "interval_s": self.cfg.interval_s,
                "status": status,
                "problems": to_json(reading.problems),
            },
            "gpus": to_json(reading.gpus),
            "samples": to_json(reading.samples),
            "processes": to_json(reading.processes),
            "inference": to_json(inference),
        }

    def deliver(self, batch: dict[str, Any]) -> bool:
        """Send one batch; spool it if the server may take it later. True when accepted."""
        try:
            self.ensure_enrolled()
            self.client.send(batch)
            return True
        except SendError as exc:
            if exc.reenrol:
                self.client.token = None
                self._token_file.unlink(missing_ok=True)
                try:
                    self.enrol()
                    self.client.send(batch)
                    return True
                except SendError as again:
                    exc = again
            if exc.retry:
                self.spool.put(batch)
                log.warning(
                    "batch spooled", extra={"error": str(exc), "spooled": len(self.spool.pending())}
                )
            else:
                log.error("batch refused", extra={"error": str(exc)})
            return False

    def replay(self) -> int:
        sent = 0
        for path in self.spool.pending()[:REPLAY_PER_TICK]:
            batch = self.spool.load(path)
            if batch is None:
                continue
            try:
                self.client.send(batch)
            except SendError as exc:
                if exc.retry:
                    return sent  # still unavailable: keep the order, try next tick
                log.error("spooled batch refused, dropping", extra={"error": str(exc)})
            self.spool.drop(path)
            sent += 1
        return sent

    def tick(self, now: datetime | None = None) -> bool:
        ok = self.deliver(self.collect(now or datetime.now(UTC)))
        if ok:
            self.replay()
        return ok

    # ── simulated history ────────────────────────────────────────────────────

    def backfill(self, days: int, step_s: int = 60, now: datetime | None = None) -> int:
        """Send ``days`` of simulated history, one hour per batch (simulated hosts only).
        Runs once per state directory; returns the number of batches sent."""
        marker = self.cfg.state_dir / "backfilled"
        if marker.exists() or self.cfg.collector != "simulated" or days <= 0:
            return 0
        self.ensure_enrolled()
        end = (now or datetime.now(UTC)).replace(second=0, microsecond=0)
        t = end - timedelta(days=days)
        sent = 0
        while t < end - timedelta(minutes=5):
            hour_end = min(t + timedelta(hours=1), end - timedelta(minutes=5))
            reading = Reading()
            inference: list[dict[str, Any]] = []
            while t < hour_end:
                part = self.collector.read(t, float(step_s))
                if not reading.gpus:
                    reading.gpus = part.gpus
                    reading.driver_version, reading.cuda_version = (
                        part.driver_version,
                        part.cuda_version,
                    )
                reading.samples += part.samples
                reading.processes += part.processes
                inference += simulated_inference(self.cfg, part, t, step_s)
                t += timedelta(seconds=step_s)
            batch = self.batch(reading, "ok", inference)
            while True:
                try:
                    self.client.send(batch)
                    break
                except SendError as exc:
                    if not exc.retry:
                        raise
                    time.sleep(2)
            sent += 1
        marker.write_text(end.isoformat())
        return sent

    def run(self, stop: Any = None) -> None:
        """Loop until ``stop()`` is true (forever by default)."""
        while not (stop and stop()):
            started = time.monotonic()
            try:
                self.tick()
            except Exception:  # never let one bad interval stop monitoring
                log.exception("tick failed")
            time.sleep(max(0.0, self.cfg.interval_s - (time.monotonic() - started)))


def simulated_inference(
    cfg: AgentConfig, reading: Reading, t: datetime, step_s: int
) -> list[dict[str, Any]]:
    """Per-interval inference rows for simulated history, from the same traffic model the
    mock server serves live."""
    uuids = {g.index: g.uuid for g in reading.gpus}
    rows = []
    ts = t.timestamp()
    for target in cfg.inference:
        name = "summarizer" if target.kind == "tgi" else "chat"
        tr = sim.traffic(name, ts)
        requests = tr.rps * step_s
        rows.append(
            {
                "endpoint": target.name,
                "kind": target.kind,
                "url": target.url,
                "model": "meta-llama/Llama-3.1-8B-Instruct"
                if target.kind == "vllm"
                else "google/flan-t5-xl",
                "gpu_uuids": [uuids[i] for i in target.gpu_indexes if i in uuids],
                "ts": t.isoformat(),
                "interval_s": float(step_s),
                "up": True,
                "requests": round(requests, 3),
                "prompt_tokens": round(requests * tr.prompt_per_req, 1),
                "generation_tokens": round(requests * tr.gen_per_req, 1),
                "running": round(tr.running, 2),
                "waiting": round(tr.waiting, 2),
                "kv_cache_usage": round(tr.kv_cache, 4) if tr.kv_cache is not None else None,
                "ttft": sim.buckets(requests, tr.ttft_median, sim.TTFT_BUCKETS)
                if tr.ttft_median
                else None,
                "itl": sim.buckets(requests * tr.gen_per_req, tr.itl_median, sim.ITL_BUCKETS),
                "e2e": sim.buckets(requests, tr.e2e_median, sim.E2E_BUCKETS),
            }
        )
    return rows
