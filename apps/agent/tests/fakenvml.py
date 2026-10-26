"""A fake of the ``pynvml`` module (nvidia-ml-py), faithful to its calling conventions.

There is no NVIDIA GPU on the build machine, so the NVML collector is tested against this:
same function names, same return shapes (named tuples, bytes or str, milliwatts, bytes of
memory), and the same error behaviour (``NVMLError`` subclasses with ``.value`` codes:
NOT_SUPPORTED for fields a GPU lacks, GPU_IS_LOST for a card that fell off the bus,
DRIVER_NOT_LOADED from ``nvmlInit``, TIMEOUT from an empty event set).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

NVML_SUCCESS = 0
NVML_ERROR_NOT_SUPPORTED = 3
NVML_ERROR_NO_PERMISSION = 4
NVML_ERROR_NOT_FOUND = 6
NVML_ERROR_DRIVER_NOT_LOADED = 9
NVML_ERROR_TIMEOUT = 10
NVML_ERROR_GPU_IS_LOST = 15

NVML_TEMPERATURE_GPU = 0
NVML_CLOCK_SM = 1
NVML_CLOCK_MEM = 2
NVML_PCIE_UTIL_TX_BYTES = 0
NVML_PCIE_UTIL_RX_BYTES = 1
NVML_MEMORY_ERROR_TYPE_UNCORRECTED = 1
NVML_VOLATILE_ECC = 0
nvmlEventTypeXidCriticalError = 8


class NVMLError(Exception):
    def __init__(self, value: int) -> None:
        super().__init__(f"NVML error {value}")
        self.value = value


def _missing() -> NVMLError:
    return NVMLError(NVML_ERROR_NOT_SUPPORTED)


@dataclass
class FakeGpu:
    uuid: str
    name: str = "NVIDIA A100-SXM4-80GB"
    total: int = 80 * 1024**3
    used: int = 20 * 1024**3
    util: tuple[int, int] = (73, 41)
    temp: int | None = 61
    power_mw: int | None = 245_000
    limit_mw: int | None = 400_000
    fan: int | None = None  # passively cooled: not supported
    sm_clock: int = 1410
    mem_clock: int = 1593
    pstate: int = 0
    throttle: int | None = 0x4
    pcie: tuple[int, int] | None = (12_000, 3_000)
    ecc: int | None = 0
    bus: bytes = b"00000000:3B:00.0"
    mig: tuple[int, int] | None = (0, 0)
    compute: list[Any] | None = field(default_factory=list)
    graphics: list[Any] | None = field(default_factory=list)
    proc_util: list[Any] | None = None
    lost: bool = False


class FakeNvml:
    """Module-like object: pass it to ``NvmlCollector(nvml=...)``."""

    NVMLError = NVMLError

    def __init__(self, gpus: list[FakeGpu], *, init_error: int | None = None) -> None:
        self.gpus = gpus
        self.init_error = init_error
        self.events: list[Any] = []
        self.calls: list[str] = []
        self.initialised = False
        for name, value in globals().items():
            if name.startswith(("NVML_", "nvmlEventType")):
                setattr(self, name, value)

    # library
    def nvmlInit(self) -> None:
        if self.init_error is not None:
            raise NVMLError(self.init_error)
        self.initialised = True

    def nvmlShutdown(self) -> None:
        self.initialised = False

    def nvmlSystemGetDriverVersion(self) -> bytes:
        return b"550.127.05"

    def nvmlSystemGetCudaDriverVersion_v2(self) -> int:
        return 12040

    def nvmlDeviceGetCount(self) -> int:
        return len(self.gpus)

    def nvmlDeviceGetHandleByIndex(self, i: int) -> FakeGpu:
        return self.gpus[i]

    def _g(self, h: FakeGpu) -> FakeGpu:
        if h.lost:
            raise NVMLError(NVML_ERROR_GPU_IS_LOST)
        return h

    # device
    def nvmlDeviceGetUUID(self, h: FakeGpu) -> str:
        return self._g(h).uuid

    def nvmlDeviceGetName(self, h: FakeGpu) -> bytes:
        return self._g(h).name.encode()

    def nvmlDeviceGetMemoryInfo(self, h: FakeGpu) -> Any:
        g = self._g(h)
        return SimpleNamespace(total=g.total, used=g.used, free=g.total - g.used)

    def nvmlDeviceGetUtilizationRates(self, h: FakeGpu) -> Any:
        g = self._g(h)
        return SimpleNamespace(gpu=g.util[0], memory=g.util[1])

    def nvmlDeviceGetTemperature(self, h: FakeGpu, sensor: int) -> int:
        g = self._g(h)
        if g.temp is None:
            raise _missing()
        return g.temp

    def nvmlDeviceGetPowerUsage(self, h: FakeGpu) -> int:
        g = self._g(h)
        if g.power_mw is None:
            raise _missing()
        return g.power_mw

    def nvmlDeviceGetEnforcedPowerLimit(self, h: FakeGpu) -> int:
        g = self._g(h)
        if g.limit_mw is None:
            raise _missing()
        return g.limit_mw

    def nvmlDeviceGetFanSpeed(self, h: FakeGpu) -> int:
        g = self._g(h)
        if g.fan is None:
            raise _missing()
        return g.fan

    def nvmlDeviceGetClockInfo(self, h: FakeGpu, clock: int) -> int:
        g = self._g(h)
        return g.sm_clock if clock == NVML_CLOCK_SM else g.mem_clock

    def nvmlDeviceGetPerformanceState(self, h: FakeGpu) -> int:
        return self._g(h).pstate

    def nvmlDeviceGetCurrentClocksEventReasons(self, h: FakeGpu) -> int:
        g = self._g(h)
        if g.throttle is None:
            raise _missing()
        return g.throttle

    def nvmlDeviceGetPcieThroughput(self, h: FakeGpu, counter: int) -> int:
        g = self._g(h)
        if g.pcie is None:
            raise _missing()
        return g.pcie[0] if counter == NVML_PCIE_UTIL_RX_BYTES else g.pcie[1]

    def nvmlDeviceGetTotalEccErrors(self, h: FakeGpu, kind: int, counter: int) -> int:
        g = self._g(h)
        if g.ecc is None:
            raise _missing()
        return g.ecc

    def nvmlDeviceGetPciInfo(self, h: FakeGpu) -> Any:
        return SimpleNamespace(busId=self._g(h).bus)

    def nvmlDeviceGetMigMode(self, h: FakeGpu) -> Any:
        g = self._g(h)
        if g.mig is None:
            raise _missing()
        return list(g.mig)

    def nvmlDeviceGetComputeRunningProcesses(self, h: FakeGpu) -> list[Any]:
        g = self._g(h)
        if g.compute is None:
            raise _missing()
        return g.compute

    def nvmlDeviceGetGraphicsRunningProcesses(self, h: FakeGpu) -> list[Any]:
        g = self._g(h)
        if g.graphics is None:
            raise _missing()
        return g.graphics

    def nvmlDeviceGetProcessUtilization(self, h: FakeGpu, since: int) -> list[Any]:
        g = self._g(h)
        if not g.proc_util:
            raise NVMLError(NVML_ERROR_NOT_FOUND)  # no samples in the window
        return g.proc_util

    # events
    def nvmlEventSetCreate(self) -> str:
        return "set"

    def nvmlEventSetFree(self, s: str) -> None:
        return None

    def nvmlDeviceRegisterEvents(self, h: FakeGpu, kind: int, s: str) -> None:
        return None

    def nvmlEventSetWait_v2(self, s: str, timeout_ms: int) -> Any:
        if not self.events:
            raise NVMLError(NVML_ERROR_TIMEOUT)
        return self.events.pop(0)


def proc(pid: int, mem_bytes: int | None) -> Any:
    return SimpleNamespace(pid=pid, usedGpuMemory=mem_bytes)


def util_sample(pid: int, sm: int, ts: int = 1_000) -> Any:
    return SimpleNamespace(pid=pid, smUtil=sm, timeStamp=ts)
