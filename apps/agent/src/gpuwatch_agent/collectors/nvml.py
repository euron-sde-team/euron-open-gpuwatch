"""NVIDIA Management Library (NVML) collector, through the official ``nvidia-ml-py`` bindings.

Every NVML call can fail on its own: a field the GPU does not support (fan speed on a
passively cooled data centre card, ECC on a consumer card) comes back as ``None`` and is
shown as "Not available", never as 0. A GPU that fell off the bus (``GPU_IS_LOST``) is left
out of the reading and reported as a problem, so the server marks it lost. If NVML cannot
start at all (no driver, no library), the collector raises ``CollectorUnavailableError`` and the
agent keeps running in a degraded state, retrying.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from datetime import datetime
from typing import Any

from gpuwatch_agent import procinfo
from gpuwatch_agent.collectors import CollectorUnavailableError
from gpuwatch_agent.model import GpuInfo, GpuSample, Problem, ProcessSample, Reading

MIB = 1024 * 1024


def _load() -> Any:
    try:
        import pynvml
    except ImportError as exc:  # pragma: no cover - a dependency of the package
        raise CollectorUnavailableError("nvml_missing", "nvidia-ml-py is not installed") from exc
    return pynvml


class NvmlCollector:
    name = "nvml"

    def __init__(
        self,
        nvml: Any | None = None,
        lookup: Callable[[int], procinfo.ProcInfo] = procinfo.lookup,
    ) -> None:
        self.nvml = nvml or _load()
        self._lookup = lookup
        self._started = False
        self._events: Any = None
        self._handles: dict[int, Any] = {}
        # Per GPU: the timestamp NVML wants for "process utilization since".
        self._last_proc_ts: dict[str, int] = {}

    # ── lifecycle ────────────────────────────────────────────────────────────

    def _start(self) -> None:
        if self._started:
            return
        n = self.nvml
        try:
            n.nvmlInit()
        except n.NVMLError as exc:
            raise CollectorUnavailableError(
                "nvml_init_failed",
                f"NVML could not start ({exc}). Is the NVIDIA driver installed and the GPU "
                "visible to this process (--gpus all in Docker)?",
            ) from exc
        self._started = True
        self._handles = {}
        self._events = self._try(n.nvmlEventSetCreate)

    def close(self) -> None:
        if self._started:
            with contextlib.suppress(Exception):
                if self._events is not None:
                    self.nvml.nvmlEventSetFree(self._events)
                self.nvml.nvmlShutdown()
        self._started = False

    def _try(self, fn: Callable[..., Any], *args: Any) -> Any:
        """Call NVML; ``None`` when the value is not supported or cannot be read."""
        try:
            return fn(*args)
        except self.nvml.NVMLError as exc:
            if self._is_lost(exc):
                raise
            return None

    def _is_lost(self, exc: Exception) -> bool:
        lost = getattr(self.nvml, "NVML_ERROR_GPU_IS_LOST", 15)
        return getattr(exc, "value", None) == lost

    # ── reading ──────────────────────────────────────────────────────────────

    def _versions(self, reading: Reading) -> None:
        n = self.nvml
        driver = self._try(n.nvmlSystemGetDriverVersion)
        reading.driver_version = driver.decode() if isinstance(driver, bytes) else driver
        cuda = self._try(n.nvmlSystemGetCudaDriverVersion_v2)
        if isinstance(cuda, int) and cuda > 0:
            reading.cuda_version = f"{cuda // 1000}.{(cuda % 1000) // 10}"

    def read(self, now: datetime, interval_s: float) -> Reading:
        self._start()
        n = self.nvml
        reading = Reading()
        self._versions(reading)
        try:
            count = n.nvmlDeviceGetCount()
        except n.NVMLError as exc:
            raise CollectorUnavailableError(
                "nvml_count_failed", f"NVML cannot list GPUs ({exc})"
            ) from exc
        xids = self._drain_xids()
        for index in range(count):
            try:
                self._read_gpu(index, now, interval_s, reading, xids)
            except n.NVMLError as exc:
                if self._is_lost(exc):
                    self._handles.pop(index, None)
                    reading.problems.append(
                        Problem("gpu_lost", f"GPU {index} is lost (fell off the bus); reset it")
                    )
                else:
                    reading.problems.append(Problem("gpu_read_failed", f"GPU {index}: {exc}"))
        return reading

    def _handle(self, index: int) -> Any:
        if index not in self._handles:
            handle = self.nvml.nvmlDeviceGetHandleByIndex(index)
            self._handles[index] = handle
            if self._events is not None:
                xid_type = getattr(self.nvml, "nvmlEventTypeXidCriticalError", 8)
                self._try(self.nvml.nvmlDeviceRegisterEvents, handle, xid_type, self._events)
        return self._handles[index]

    def _drain_xids(self) -> dict[str, int]:
        """XID errors since the last read, by GPU UUID (the latest code wins)."""
        out: dict[str, int] = {}
        if self._events is None:
            return out
        n = self.nvml
        while True:
            try:
                event = n.nvmlEventSetWait_v2(self._events, 0)
            except n.NVMLError:
                return out  # timeout: no more events
            uuid = self._try(n.nvmlDeviceGetUUID, event.device)
            if uuid is not None:
                out[uuid.decode() if isinstance(uuid, bytes) else uuid] = int(event.eventData)

    def _read_gpu(
        self, index: int, now: datetime, interval_s: float, reading: Reading, xids: dict[str, int]
    ) -> None:
        n = self.nvml
        h = self._handle(index)
        raw_uuid = n.nvmlDeviceGetUUID(h)
        uuid = raw_uuid.decode() if isinstance(raw_uuid, bytes) else str(raw_uuid)
        raw_name = self._try(n.nvmlDeviceGetName, h) or f"GPU {index}"
        name = raw_name.decode() if isinstance(raw_name, bytes) else str(raw_name)
        mem = self._try(n.nvmlDeviceGetMemoryInfo, h)
        util = self._try(n.nvmlDeviceGetUtilizationRates, h)
        power_mw = self._try(n.nvmlDeviceGetPowerUsage, h)
        limit_mw = self._try(n.nvmlDeviceGetEnforcedPowerLimit, h)
        pci = self._try(n.nvmlDeviceGetPciInfo, h)
        mig = self._try(n.nvmlDeviceGetMigMode, h)
        throttle = self._try(
            getattr(n, "nvmlDeviceGetCurrentClocksEventReasons", None)
            or n.nvmlDeviceGetCurrentClocksThrottleReasons,
            h,
        )
        procs = self._processes(h, uuid, now)
        bus = getattr(pci, "busId", None)
        reading.gpus.append(
            GpuInfo(
                uuid=uuid,
                index=index,
                name=name,
                memory_total_mib=mem.total / MIB if mem else None,
                power_limit_w=limit_mw / 1000 if limit_mw is not None else None,
                pci_bus_id=(bus.decode() if isinstance(bus, bytes) else bus),
                mig_mode=bool(mig[0]) if isinstance(mig, (list, tuple)) else None,
            )
        )
        reading.samples.append(
            GpuSample(
                gpu_uuid=uuid,
                ts=now,
                interval_s=interval_s,
                util_gpu=float(util.gpu) if util is not None else None,
                util_mem=float(util.memory) if util is not None else None,
                mem_used_mib=mem.used / MIB if mem else None,
                mem_total_mib=mem.total / MIB if mem else None,
                temp_c=_float(self._try(n.nvmlDeviceGetTemperature, h, n.NVML_TEMPERATURE_GPU)),
                power_w=power_mw / 1000 if power_mw is not None else None,
                power_limit_w=limit_mw / 1000 if limit_mw is not None else None,
                fan_pct=_float(self._try(n.nvmlDeviceGetFanSpeed, h)),
                sm_clock_mhz=_float(self._try(n.nvmlDeviceGetClockInfo, h, n.NVML_CLOCK_SM)),
                mem_clock_mhz=_float(self._try(n.nvmlDeviceGetClockInfo, h, n.NVML_CLOCK_MEM)),
                pstate=self._try(n.nvmlDeviceGetPerformanceState, h),
                throttle_reasons=int(throttle) if throttle is not None else None,
                pcie_rx_kbps=_float(
                    self._try(n.nvmlDeviceGetPcieThroughput, h, n.NVML_PCIE_UTIL_RX_BYTES)
                ),
                pcie_tx_kbps=_float(
                    self._try(n.nvmlDeviceGetPcieThroughput, h, n.NVML_PCIE_UTIL_TX_BYTES)
                ),
                ecc_uncorrected=self._try(
                    n.nvmlDeviceGetTotalEccErrors,
                    h,
                    n.NVML_MEMORY_ERROR_TYPE_UNCORRECTED,
                    n.NVML_VOLATILE_ECC,
                ),
                xid=xids.get(uuid),
                procs=len(procs) if procs is not None else None,
            )
        )
        reading.processes.extend(procs or [])

    def _processes(self, h: Any, uuid: str, now: datetime) -> list[ProcessSample] | None:
        """Compute and graphics processes with their memory and SM share. ``None`` when the
        driver does not list processes here (some containers, vGPU)."""
        n = self.nvml
        compute = self._try(n.nvmlDeviceGetComputeRunningProcesses, h)
        graphics = self._try(n.nvmlDeviceGetGraphicsRunningProcesses, h)
        if compute is None and graphics is None:
            return None
        seen: dict[int, float | None] = {}
        for p in list(compute or []) + list(graphics or []):
            used = getattr(p, "usedGpuMemory", None)
            # NVML reports None (or a sentinel) when memory per process is not available.
            mib = used / MIB if isinstance(used, int) and 0 <= used < 2**62 else None
            prev = seen.get(int(p.pid))
            seen[int(p.pid)] = mib if prev is None else max(prev, mib or 0.0)
        sm: dict[int, float] = {}
        since = self._last_proc_ts.get(uuid, 0)
        samples = self._try(n.nvmlDeviceGetProcessUtilization, h, since)
        if samples:
            for s in samples:
                sm[int(s.pid)] = float(s.smUtil)
            self._last_proc_ts[uuid] = max(int(s.timeStamp) for s in samples)
        out = []
        for pid, mib in seen.items():
            info = self._lookup(pid)
            out.append(
                ProcessSample(
                    gpu_uuid=uuid,
                    ts=now,
                    pid=pid,
                    name=info.name,
                    username=info.username,
                    container_id=info.container_id,
                    mem_used_mib=mib,
                    # Listed in a utilization sample set but absent: it used no SM time.
                    sm_util=sm.get(pid, 0.0) if samples else None,
                )
            )
        return out


def _float(value: Any) -> float | None:
    return float(value) if value is not None else None
