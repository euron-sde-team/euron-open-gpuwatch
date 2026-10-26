"""Reads an existing NVIDIA DCGM exporter (``dcgm-exporter``) instead of NVML.

For clusters that already run DCGM exporter (Kubernetes GPU operator): GPUWatch reuses it
rather than opening NVML a second time. Field names follow dcgm-exporter's default
counters; a field the exporter is not configured to export is ``None``. DCGM exporter does
not list processes, so attribution on these hosts shows ``(unattributed)`` while busy.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from gpuwatch_agent import promtext
from gpuwatch_agent.collectors import CollectorUnavailableError
from gpuwatch_agent.model import GpuInfo, GpuSample, Reading

# dcgm-exporter field -> (sample attribute, scale)
FIELDS: dict[str, tuple[str, float]] = {
    "DCGM_FI_DEV_GPU_UTIL": ("util_gpu", 1.0),
    "DCGM_FI_DEV_MEM_COPY_UTIL": ("util_mem", 1.0),
    "DCGM_FI_DEV_FB_USED": ("mem_used_mib", 1.0),
    "DCGM_FI_DEV_GPU_TEMP": ("temp_c", 1.0),
    "DCGM_FI_DEV_POWER_USAGE": ("power_w", 1.0),
    "DCGM_FI_DEV_SM_CLOCK": ("sm_clock_mhz", 1.0),
    "DCGM_FI_DEV_MEM_CLOCK": ("mem_clock_mhz", 1.0),
    "DCGM_FI_DEV_FAN_SPEED": ("fan_pct", 1.0),
    "DCGM_FI_DEV_PCIE_RX_THROUGHPUT": ("pcie_rx_kbps", 1.0),
    "DCGM_FI_DEV_PCIE_TX_THROUGHPUT": ("pcie_tx_kbps", 1.0),
    "DCGM_FI_DEV_POWER_MGMT_LIMIT": ("power_limit_w", 1.0),
}
INT_FIELDS = {
    "DCGM_FI_DEV_CLOCK_THROTTLE_REASONS": "throttle_reasons",
    "DCGM_FI_DEV_CLOCKS_EVENT_REASONS": "throttle_reasons",
    "DCGM_FI_DEV_ECC_DBE_VOL_TOTAL": "ecc_uncorrected",
    "DCGM_FI_DEV_PSTATE": "pstate",
}


def parse_exporter(
    text: str, now: datetime, interval_s: float, last_xid: dict[str, int]
) -> Reading:
    reading = Reading()
    gpus: dict[str, GpuSample] = {}
    info: dict[str, GpuInfo] = {}
    free: dict[str, float] = {}
    reserved: dict[str, float] = {}
    for s in promtext.parse(text):
        uuid = s.labels.get("UUID") or s.labels.get("uuid")
        if not uuid:
            continue
        if uuid not in gpus:
            gpus[uuid] = GpuSample(gpu_uuid=uuid, ts=now, interval_s=interval_s)
            info[uuid] = GpuInfo(
                uuid=uuid,
                index=int(s.labels.get("gpu", len(info))),
                name=s.labels.get("modelName", "NVIDIA GPU"),
                pci_bus_id=s.labels.get("pci_bus_id"),
            )
            reading.driver_version = reading.driver_version or s.labels.get(
                "DCGM_FI_DRIVER_VERSION"
            )
        sample = gpus[uuid]
        if s.name in FIELDS:
            attr, scale = FIELDS[s.name]
            setattr(sample, attr, s.value * scale)
        elif s.name in INT_FIELDS:
            setattr(sample, INT_FIELDS[s.name], int(s.value))
        elif s.name == "DCGM_FI_DEV_FB_FREE":
            free[uuid] = s.value
        elif s.name == "DCGM_FI_DEV_FB_RESERVED":
            reserved[uuid] = s.value
        elif s.name == "DCGM_FI_DEV_XID_ERRORS":
            # The exporter shows the last XID code; report it once, when it changes.
            code = int(s.value)
            if code and last_xid.get(uuid) != code:
                sample.xid = code
            last_xid[uuid] = code
    for uuid, sample in gpus.items():
        if sample.mem_used_mib is not None and uuid in free:
            total = sample.mem_used_mib + free[uuid] + reserved.get(uuid, 0.0)
            sample.mem_total_mib = total
            info[uuid].memory_total_mib = total
        info[uuid].power_limit_w = sample.power_limit_w
        reading.gpus.append(info[uuid])
        reading.samples.append(sample)
    reading.gpus.sort(key=lambda g: g.index)
    return reading


class DcgmCollector:
    name = "dcgm"

    def __init__(self, url: str, client: httpx.Client | None = None) -> None:
        self.url = url
        self._client = client or httpx.Client(timeout=5.0)
        self._last_xid: dict[str, int] = {}

    def read(self, now: datetime, interval_s: float) -> Reading:
        try:
            response = self._client.get(self.url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CollectorUnavailableError(
                "dcgm_unreachable", f"Cannot read DCGM exporter at {self.url} ({exc})"
            ) from exc
        reading = parse_exporter(response.text, now, interval_s, self._last_xid)
        if not reading.gpus:
            raise CollectorUnavailableError(
                "dcgm_no_gpus", f"DCGM exporter at {self.url} lists no GPUs"
            )
        return reading

    def close(self) -> None:
        self._client.close()
