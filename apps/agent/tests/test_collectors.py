"""Collectors: NVML (against a faithful fake), DCGM exporter output, and the simulator."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from gpuwatch_agent import sim
from gpuwatch_agent.collectors import CollectorUnavailableError
from gpuwatch_agent.collectors.dcgm import parse_exporter
from gpuwatch_agent.collectors.nvml import NvmlCollector
from gpuwatch_agent.collectors.simulated import SimulatedCollector
from gpuwatch_agent.procinfo import ProcInfo, container_id, lookup
from tests.fakenvml import NVML_ERROR_DRIVER_NOT_LOADED, FakeGpu, FakeNvml, proc, util_sample

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
GIB = 1024**3


def names(pid: int) -> ProcInfo:
    return ProcInfo({1: "python3", 2: "vllm"}.get(pid, f"pid {pid}"), "ml", "abc123def456")


def test_nvml_reads_every_supported_field_and_leaves_the_rest_null() -> None:
    gpu = FakeGpu(
        "GPU-1111",
        compute=[proc(1, 10 * GIB), proc(2, 6 * GIB)],
        proc_util=[util_sample(1, 55), util_sample(2, 20)],
    )
    reading = NvmlCollector(nvml=FakeNvml([gpu]), lookup=names).read(NOW, 5.0)
    assert reading.driver_version == "550.127.05" and reading.cuda_version == "12.4"
    (info,) = reading.gpus
    assert info.uuid == "GPU-1111" and info.name == "NVIDIA A100-SXM4-80GB"
    assert (
        info.memory_total_mib == 81_920
        and info.power_limit_w == 400
        and info.pci_bus_id == "00000000:3B:00.0"
    )
    assert info.mig_mode is False
    (s,) = reading.samples
    assert (s.util_gpu, s.util_mem, s.temp_c, s.power_w) == (73.0, 41.0, 61.0, 245.0)
    assert s.mem_used_mib == 20_480 and s.throttle_reasons == 0x4
    assert s.pcie_rx_kbps == 12_000 and s.pcie_tx_kbps == 3_000
    assert s.fan_pct is None  # not supported on this card: null, not 0
    assert s.procs == 2
    p = {x.pid: x for x in reading.processes}
    assert p[1].name == "python3" and p[1].mem_used_mib == 10_240 and p[1].sm_util == 55.0
    assert p[2].sm_util == 20.0 and p[1].container_id == "abc123def456"
    assert reading.problems == []


def test_nvml_without_process_utilization_leaves_sm_share_null() -> None:
    gpu = FakeGpu("GPU-2222", compute=[proc(1, None)], proc_util=None)
    reading = NvmlCollector(nvml=FakeNvml([gpu]), lookup=names).read(NOW, 5.0)
    (p,) = reading.processes
    assert p.sm_util is None and p.mem_used_mib is None


def test_nvml_when_the_driver_does_not_list_processes() -> None:
    gpu = FakeGpu("GPU-3333", compute=None, graphics=None)
    (s,) = NvmlCollector(nvml=FakeNvml([gpu])).read(NOW, 5.0).samples
    assert s.procs is None


def test_a_lost_gpu_is_left_out_and_reported() -> None:
    good, lost = FakeGpu("GPU-good"), FakeGpu("GPU-lost", lost=True)
    reading = NvmlCollector(nvml=FakeNvml([good, lost])).read(NOW, 5.0)
    assert [g.uuid for g in reading.gpus] == ["GPU-good"]
    assert reading.problems[0].code == "gpu_lost" and "GPU 1" in reading.problems[0].message


def test_nvml_init_failure_is_unavailable_not_a_crash() -> None:
    collector = NvmlCollector(nvml=FakeNvml([], init_error=NVML_ERROR_DRIVER_NOT_LOADED))
    with pytest.raises(CollectorUnavailableError) as exc:
        collector.read(NOW, 5.0)
    assert exc.value.code == "nvml_init_failed" and "--gpus all" in exc.value.message


def test_xid_events_are_attributed_to_their_gpu_once() -> None:
    nvml = FakeNvml([FakeGpu("GPU-x0"), FakeGpu("GPU-x1")])
    collector = NvmlCollector(nvml=nvml)
    collector.read(NOW, 5.0)  # registers the handles
    from types import SimpleNamespace

    nvml.events.append(SimpleNamespace(device=nvml.gpus[1], eventData=79))
    reading = collector.read(NOW, 5.0)
    assert [s.xid for s in reading.samples] == [None, 79]
    assert [s.xid for s in collector.read(NOW, 5.0).samples] == [None, None]
    collector.close()
    assert nvml.initialised is False


DCGM = """# HELP DCGM_FI_DEV_SM_CLOCK SM clock frequency (in MHz).
# TYPE DCGM_FI_DEV_SM_CLOCK gauge
DCGM_FI_DEV_SM_CLOCK{gpu="0",UUID="GPU-aaaa",pci_bus_id="00000000:07:00.0",device="nvidia0",modelName="NVIDIA A100-SXM4-80GB",Hostname="node1",DCGM_FI_DRIVER_VERSION="535.104.12"} 1410
DCGM_FI_DEV_SM_CLOCK{gpu="1",UUID="GPU-bbbb",pci_bus_id="00000000:0F:00.0",device="nvidia1",modelName="NVIDIA A100-SXM4-80GB",Hostname="node1",DCGM_FI_DRIVER_VERSION="535.104.12"} 210
# TYPE DCGM_FI_DEV_GPU_UTIL gauge
DCGM_FI_DEV_GPU_UTIL{gpu="0",UUID="GPU-aaaa",modelName="NVIDIA A100-SXM4-80GB"} 97
DCGM_FI_DEV_GPU_UTIL{gpu="1",UUID="GPU-bbbb",modelName="NVIDIA A100-SXM4-80GB"} 0
# TYPE DCGM_FI_DEV_FB_USED gauge
DCGM_FI_DEV_FB_USED{gpu="0",UUID="GPU-aaaa",modelName="NVIDIA A100-SXM4-80GB"} 61000
DCGM_FI_DEV_FB_USED{gpu="1",UUID="GPU-bbbb",modelName="NVIDIA A100-SXM4-80GB"} 0
# TYPE DCGM_FI_DEV_FB_FREE gauge
DCGM_FI_DEV_FB_FREE{gpu="0",UUID="GPU-aaaa",modelName="NVIDIA A100-SXM4-80GB"} 19920
DCGM_FI_DEV_FB_FREE{gpu="1",UUID="GPU-bbbb",modelName="NVIDIA A100-SXM4-80GB"} 80920
# TYPE DCGM_FI_DEV_FB_RESERVED gauge
DCGM_FI_DEV_FB_RESERVED{gpu="0",UUID="GPU-aaaa",modelName="NVIDIA A100-SXM4-80GB"} 1000
# TYPE DCGM_FI_DEV_GPU_TEMP gauge
DCGM_FI_DEV_GPU_TEMP{gpu="0",UUID="GPU-aaaa",modelName="NVIDIA A100-SXM4-80GB"} 64
# TYPE DCGM_FI_DEV_POWER_USAGE gauge
DCGM_FI_DEV_POWER_USAGE{gpu="0",UUID="GPU-aaaa",modelName="NVIDIA A100-SXM4-80GB"} 312.5
# TYPE DCGM_FI_DEV_CLOCK_THROTTLE_REASONS gauge
DCGM_FI_DEV_CLOCK_THROTTLE_REASONS{gpu="0",UUID="GPU-aaaa",modelName="NVIDIA A100-SXM4-80GB"} 4
# TYPE DCGM_FI_DEV_XID_ERRORS gauge
DCGM_FI_DEV_XID_ERRORS{gpu="0",UUID="GPU-aaaa",modelName="NVIDIA A100-SXM4-80GB",err_code="0",err_msg="No Error"} 0
DCGM_FI_DEV_XID_ERRORS{gpu="1",UUID="GPU-bbbb",modelName="NVIDIA A100-SXM4-80GB",err_code="48",err_msg="DBE"} 48
"""


def test_dcgm_exporter_output_maps_to_samples() -> None:
    last_xid: dict[str, int] = {}
    reading = parse_exporter(DCGM, NOW, 5.0, last_xid)
    assert reading.driver_version == "535.104.12"
    a, b = reading.samples
    assert (a.util_gpu, a.sm_clock_mhz, a.temp_c, a.power_w, a.throttle_reasons) == (
        97.0,
        1410.0,
        64.0,
        312.5,
        4,
    )
    assert a.mem_used_mib == 61000 and a.mem_total_mib == 61000 + 19920 + 1000
    assert b.temp_c is None and b.power_w is None  # not exported for this GPU: null
    assert a.procs is None  # DCGM exporter does not list processes
    assert b.xid == 48 and a.xid is None
    assert parse_exporter(DCGM, NOW, 5.0, last_xid).samples[1].xid is None  # reported once
    assert [g.index for g in reading.gpus] == [0, 1]


def test_the_simulator_is_deterministic_and_realistic() -> None:
    a = SimulatedCollector("train-node-01", "training").read(NOW, 5.0)
    b = SimulatedCollector("train-node-01", "training").read(NOW, 5.0)
    assert [s.util_gpu for s in a.samples] == [s.util_gpu for s in b.samples]
    assert len(a.gpus) == 8 and a.gpus[0].uuid == sim.gpu_uuid("train-node-01", 0)
    assert all(s.fan_pct is None for s in a.samples)  # H100 SXM: no fan reading
    ws = SimulatedCollector("dev-ws", "workstation").read(NOW, 5.0)
    assert ws.samples[0].ecc_uncorrected is None  # consumer card: no ECC
    assert all(p.sm_util is None for p in ws.processes)
    infer = SimulatedCollector("infer-node-01", "inference").read(NOW, 5.0)
    assert {g.name for g in infer.gpus} == {"NVIDIA L40S", "NVIDIA L4"}
    with pytest.raises(ValueError, match="unknown simulation profile"):
        SimulatedCollector("x", "nope")


def test_simulated_scenarios_show_the_problems_they_claim() -> None:
    day = datetime(2026, 10, 26, tzinfo=UTC).timestamp()  # a Monday
    specs = {s.index: s for s in sim.PROFILES["training"]()}
    hot = sim.read("t", specs[3], day + 14 * 3600)
    assert hot.temp >= 85 and hot.throttle & sim.THROTTLE_SW_THERMAL
    gap = sim.read("t", specs[0], day + 22.5 * 3600)
    assert gap.util < 5 and gap.state.procs  # weights loaded, no work
    night = sim.read("t", specs[6], day + 2 * 3600)
    assert night.util < 5 and night.state.procs  # notebook kept overnight
    chat_peak, chat_night = (
        sim.traffic("chat", day + 15 * 3600),
        sim.traffic("chat", day + 3 * 3600),
    )
    assert chat_peak.waiting > 0 and chat_peak.kv_cache and chat_peak.kv_cache > 0.9
    assert chat_night.waiting == 0
    assert sim.traffic("summarizer", day).ttft_median is None  # TGI: no TTFT


def test_process_details_from_proc(tmp_path: Path) -> None:
    pid = tmp_path / "4242"
    pid.mkdir()
    (pid / "comm").write_text("python3\n")
    (pid / "status").write_text("Name:\tpython3\nUid:\t0\t0\t0\t0\n")
    (pid / "cgroup").write_text("0::/system.slice/docker-" + "a" * 64 + ".scope\n")
    info = lookup(4242, tmp_path)
    assert info.name == "python3" and info.username == "root" and info.container_id == "a" * 12
    assert lookup(999, tmp_path).name == "pid 999"
    assert container_id("0::/kubepods/besteffort/pod1/" + "b" * 64) == "b" * 12
    assert container_id("0::/user.slice") is None
