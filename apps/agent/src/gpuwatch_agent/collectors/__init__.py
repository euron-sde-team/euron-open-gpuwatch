"""Collectors: one Protocol, one implementation per source (NVML, DCGM exporter, simulated).

Adding a source (AMD ROCm SMI, for instance) means adding a module here, not editing the
agent loop.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from gpuwatch_agent.model import Reading


class CollectorUnavailableError(Exception):
    """The source cannot be read at all (driver missing, exporter down). The agent keeps
    running, reports itself degraded with this message, and retries."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Collector(Protocol):
    name: str

    def read(self, now: datetime, interval_s: float) -> Reading: ...

    def close(self) -> None: ...
