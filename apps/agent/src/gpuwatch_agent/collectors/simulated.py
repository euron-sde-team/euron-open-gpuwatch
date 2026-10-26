"""Simulated GPUs for the demo and the tests (``GPUWATCH_COLLECTOR=simulated``).

Readings come from ``gpuwatch_agent.sim``: deterministic scenarios, sent through the same
batch format and ingest API as real readings. Hosts enrolled with a simulated token are
badged as simulated in the dashboard.
"""

from __future__ import annotations

from datetime import datetime

from gpuwatch_agent import sim
from gpuwatch_agent.model import GpuInfo, GpuSample, ProcessSample, Reading

DRIVER = "550.127.05"
CUDA = "12.4"


class SimulatedCollector:
    name = "simulated"

    def __init__(self, machine: str, profile: str) -> None:
        if profile not in sim.PROFILES:
            raise ValueError(f"unknown simulation profile {profile!r} ({', '.join(sim.PROFILES)})")
        self.machine = machine
        self.specs = sim.PROFILES[profile]()

    def inventory(self) -> list[GpuInfo]:
        return [
            GpuInfo(
                uuid=sim.gpu_uuid(self.machine, s.index),
                index=s.index,
                name=s.name,
                memory_total_mib=s.memory_mib,
                power_limit_w=s.power_limit_w,
                pci_bus_id=f"00000000:{0x1B + s.index * 0x10:02X}:00.0",
                mig_mode=False if s.name.startswith("NVIDIA H100") else None,
            )
            for s in self.specs
        ]

    def read(self, now: datetime, interval_s: float) -> Reading:
        reading = Reading(gpus=self.inventory(), driver_version=DRIVER, cuda_version=CUDA)
        t = now.timestamp()
        for spec, info in zip(self.specs, reading.gpus, strict=True):
            r = sim.read(self.machine, spec, t)
            reading.samples.append(
                GpuSample(
                    gpu_uuid=info.uuid,
                    ts=now,
                    interval_s=interval_s,
                    util_gpu=r.util,
                    util_mem=round(r.util * 0.62, 1),
                    mem_used_mib=r.mem_used,
                    mem_total_mib=spec.memory_mib,
                    temp_c=r.temp,
                    power_w=r.power,
                    power_limit_w=spec.power_limit_w,
                    fan_pct=r.fan,
                    sm_clock_mhz=r.sm_clock,
                    mem_clock_mhz=r.mem_clock,
                    pstate=r.pstate,
                    throttle_reasons=r.throttle,
                    pcie_rx_kbps=r.pcie_rx,
                    pcie_tx_kbps=r.pcie_tx,
                    ecc_uncorrected=r.ecc,
                    xid=r.state.xid,
                    procs=len(r.state.procs),
                )
            )
            for p in r.state.procs:
                reading.processes.append(
                    ProcessSample(
                        gpu_uuid=info.uuid,
                        ts=now,
                        pid=p.pid,
                        name=p.name,
                        username=p.username,
                        container_id=p.container_id,
                        mem_used_mib=p.mem_mib,
                        sm_util=round(p.sm, 1) if spec.process_sm and p.sm is not None else None,
                    )
                )
        return reading

    def close(self) -> None:
        return None
