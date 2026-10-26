"""The fleet's GPU metrics in Prometheus text format, appended to ``/metrics``.

Computed on scrape from the live view, one series per GPU with recent data. A metric the
GPU does not report is left out (Prometheus reads absence as unknown), never written as 0.
"""

from __future__ import annotations

from gpuwatch.core.container import Container
from gpuwatch.fleet import service as fleet_service

_GAUGES = (
    ("gpuwatch_gpu_utilization_percent", "GPU utilization", "util_gpu", 1.0),
    ("gpuwatch_gpu_memory_utilization_percent", "Memory bandwidth utilization", "util_mem", 1.0),
    ("gpuwatch_gpu_memory_used_bytes", "Memory in use", "mem_used_mib", 1024.0 * 1024.0),
    ("gpuwatch_gpu_memory_total_bytes", "Memory on the card", "mem_total_mib", 1024.0 * 1024.0),
    ("gpuwatch_gpu_temperature_celsius", "Temperature", "temp_c", 1.0),
    ("gpuwatch_gpu_power_watts", "Power draw", "power_w", 1.0),
    ("gpuwatch_gpu_fan_percent", "Fan speed", "fan_pct", 1.0),
    ("gpuwatch_gpu_sm_clock_hertz", "SM clock", "sm_clock_mhz", 1e6),
    ("gpuwatch_gpu_processes", "Processes on the GPU", "procs", 1.0),
)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


async def exposition(container: Container) -> str:
    async with container.db.sessionmaker() as session:
        gpus = await fleet_service.list_gpus(session, container)
    lines = [
        "# HELP gpuwatch_gpu_up 1 when the GPU is reporting, 0 when lost or its host is offline",
        "# TYPE gpuwatch_gpu_up gauge",
    ]
    labelled = []
    for g in gpus:
        labels = (
            f'host="{_escape(g.host_name)}",gpu="{g.index}",uuid="{_escape(g.uuid)}",'
            f'model="{_escape(g.name)}"'
        )
        labelled.append((labels, g))
        lines.append(f"gpuwatch_gpu_up{{{labels}}} {1 if g.status == 'ok' else 0}")
    for name, help_text, field, scale in _GAUGES:
        lines += [f"# HELP {name} {help_text}", f"# TYPE {name} gauge"]
        for labels, g in labelled:
            value = (g.live or {}).get(field)
            if value is not None and g.status == "ok":
                lines.append(f"{name}{{{labels}}} {float(value) * scale:g}")
    return "\n".join(lines) + "\n"
