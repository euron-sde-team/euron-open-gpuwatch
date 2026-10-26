# The agent

`gpuwatch-agent` runs on each machine with NVIDIA GPUs. It reads the GPUs through NVML (or
an existing DCGM exporter), the processes on them, and local vLLM or TGI servers, and sends
one batch every 5 seconds to your GPUWatch API. It needs **outbound HTTPS only**: it opens
no port, accepts no commands, and never starts or stops a process. How it works inside is
in [architecture/agent.md](../architecture/agent.md).

- [Before you start](#before-you-start)
- [Install with Docker](#install-with-docker)
- [Install with Python](#install-with-python)
- [DCGM exporter mode](#dcgm-exporter-mode)
- [Inference endpoints](#inference-endpoints)
- [Labels](#labels)
- [State directory](#state-directory)
- [Check what the agent sees](#check-what-the-agent-sees)
- [Compatibility matrix](#compatibility-matrix)
- [Configuration reference](#configuration-reference)

## Before you start

1. In the dashboard, open **Hosts**, **Add a host**, and create an enrolment token. It is
   shown once. Give it an expiry and, for a rollout, a machine limit. Labels on the token
   are added to every host enrolled with it.
2. Make sure the machine can reach the API: locally `http://<your machine>:4430`; on AWS
   the deployment URL (the ALB forwards `/ingest/*` to the API).
3. The NVIDIA driver must be installed on the machine (`nvidia-smi` works).

## Install with Docker

Requirements: Docker and the
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html),
which mounts the host driver's `libnvidia-ml.so` into containers started with `--gpus`.
The image does not contain NVML itself.

```bash
docker build -f infra/docker/agent.Dockerfile -t gpuwatch-agent apps/agent

docker run -d --name gpuwatch-agent --restart unless-stopped \
  --gpus all --pid=host \
  -e GPUWATCH_URL=https://gpuwatch.example.com \
  -e GPUWATCH_ENROLMENT_TOKEN=gwe_... \
  -v gpuwatch-agent:/var/lib/gpuwatch-agent \
  gpuwatch-agent run
```

- `--gpus all` gives the container access to every GPU through the toolkit. The image sets
  `NVIDIA_DRIVER_CAPABILITIES=utility`, which is all NVML needs.
- `--pid=host` lets the agent see the host's process table, so GPU process ids resolve to
  names, users and container ids. Without it, processes show as `pid <n>`.
- The container runs as UID 10001. To read process details of other users' processes
  (`/proc/<pid>/status` and `cgroup`), add `--cap-add SYS_PTRACE` or run with `--user 0`;
  without it, those details may be missing.
- The volume keeps the host token, the spool and the machine id across restarts.
- On machines where `/etc/machine-id` is not visible in the container, set
  `GPUWATCH_MACHINE_ID` to a stable value so a recreated container keeps the same host.

The dashboard's "Add a host" dialog prints this command with your URL and token filled in.

## Install with Python

Python 3.10 to 3.13 on the GPU machine. From a checkout of this repository:

```bash
pip install ./apps/agent          # or: uv tool install ./apps/agent

GPUWATCH_URL=https://gpuwatch.example.com \
GPUWATCH_ENROLMENT_TOKEN=gwe_... \
GPUWATCH_STATE_DIR=$HOME/.gpuwatch-agent \
gpuwatch-agent run
```

`nvidia-ml-py` is installed as a dependency; it loads the driver's `libnvidia-ml` at
runtime. Run it under systemd or another supervisor so it restarts. A minimal unit:

```ini
[Unit]
Description=GPUWatch agent
After=network-online.target

[Service]
Environment=GPUWATCH_URL=https://gpuwatch.example.com
Environment=GPUWATCH_ENROLMENT_TOKEN_FILE=/etc/gpuwatch/enrolment-token
Environment=GPUWATCH_STATE_DIR=/var/lib/gpuwatch-agent
ExecStart=/usr/local/bin/gpuwatch-agent run
Restart=always

[Install]
WantedBy=multi-user.target
```

## DCGM exporter mode

Where NVIDIA's DCGM exporter already runs (for example with the NVIDIA GPU Operator on
Kubernetes), the agent can read it instead of opening NVML a second time:

```bash
docker run -d --name gpuwatch-agent --restart unless-stopped \
  -e GPUWATCH_URL=https://gpuwatch.example.com \
  -e GPUWATCH_ENROLMENT_TOKEN=gwe_... \
  -e GPUWATCH_COLLECTOR=dcgm \
  -e GPUWATCH_DCGM_URL=http://dcgm-exporter:9400/metrics \
  -v gpuwatch-agent:/var/lib/gpuwatch-agent \
  gpuwatch-agent run
```

No `--gpus` is needed in this mode. The exporter must export the fields you want to see
(its default counters cover utilization, memory, temperature, power, clocks and XID; ECC,
PCIe and throttle reasons depend on the counters file). DCGM exporter does not list
processes, so busy time on these hosts is attributed as `(unattributed)` rather than to a
workload.

## Inference endpoints

To see serving metrics and cost per million tokens next to the GPUs, list the inference
servers on the machine in `GPUWATCH_INFERENCE`:

```
GPUWATCH_INFERENCE=name=kind,url[,gpu_index+gpu_index];name=kind,url[,...]
```

- `name`: how the endpoint appears in GPUWatch (unique per host).
- `kind`: `vllm` or `tgi`.
- `url`: the server's Prometheus endpoint, as reachable from the agent.
- GPU indexes (optional): the GPUs the server runs on, joined by `+`. They bind the
  endpoint to those GPUs for cost per token and utilization.

Examples:

```bash
# one vLLM server on GPU 0
GPUWATCH_INFERENCE="llama-chat=vllm,http://localhost:8000/metrics,0"
# a tensor-parallel vLLM on GPUs 0 and 1, and TGI on GPU 2
GPUWATCH_INFERENCE="chat=vllm,http://localhost:8000/metrics,0+1;summarizer=tgi,http://localhost:8080/metrics,2"
```

The agent sends per-interval deltas of the servers' counters and histograms. TGI exposes no
time-to-first-token histogram and no KV cache gauge, so those show as "Not available".
An endpoint that does not answer is shown as down.

## Labels

```bash
GPUWATCH_LABELS="role=training,site=dc-1,team=research"
```

Labels are `key=value` pairs (keys: letters, digits, `_`, `.`, `-`). They are sent at
enrolment and merged with the enrolment token's labels; admins can edit them later on the
host. Labels scope alert rules (`scope_label`, for example `role=training`) and workload
rules (`host_label`).

## State directory

`GPUWATCH_STATE_DIR` (default `/var/lib/gpuwatch-agent`) holds:

| File | What it is |
| ---- | ---------- |
| `host-token` | The host token from enrolment (mode 0600). Delete it to force re-enrolment |
| `spool/` | Batches waiting for the API, one JSON file each, bounded by `GPUWATCH_SPOOL_MAX_MB` |
| `machine-id` | A generated machine id, only when neither `GPUWATCH_MACHINE_ID` nor `/etc/machine-id` is available |
| `backfilled` | Marker for simulated hosts after their one-time backfill |

Keep it on persistent storage. Losing it means re-enrolling (which keeps the host if the
machine id is unchanged) and losing unsent batches.

## Check what the agent sees

```bash
docker run --rm --gpus all --pid=host gpuwatch-agent check
# or, installed with pip:
gpuwatch-agent check
```

`check` reads the collector once and prints the driver and CUDA versions, each GPU with its
utilization, memory, temperature and power, **the metrics this GPU does not report**, the
processes found, and any problem. It needs no server and sends nothing. Exit code 2 means
the collector is unavailable (for example `nvml_init_failed`). Please include its output
when you report a compatibility issue.

## Compatibility matrix

**Honest status for 0.1.0:** the agent has been verified with simulated hardware and with a
faithful fake of the NVML Python module
([`apps/agent/tests/fakenvml.py`](../../apps/agent/tests/fakenvml.py)) that reproduces
nvidia-ml-py's function names, return shapes and error codes, and the DCGM collector with
recorded exporter output. **It has not yet been verified on a real NVIDIA GPU.** Real-GPU
verification (running `gpuwatch-agent check` and a live session on data centre and consumer
cards) is pending; reports are welcome.

### Where each field comes from

| Field | NVML call (`nvml` collector) | DCGM exporter field (`dcgm` collector) |
| ----- | ---------------------------- | -------------------------------------- |
| Inventory: UUID, name, index | `nvmlDeviceGetHandleByIndex`, `nvmlDeviceGetUUID`, `nvmlDeviceGetName` | `UUID`, `modelName`, `gpu` labels |
| Driver version, CUDA version | `nvmlSystemGetDriverVersion`, `nvmlSystemGetCudaDriverVersion_v2` | `DCGM_FI_DRIVER_VERSION` label (driver only) |
| GPU and memory utilization | `nvmlDeviceGetUtilizationRates` | `DCGM_FI_DEV_GPU_UTIL`, `DCGM_FI_DEV_MEM_COPY_UTIL` |
| Memory used and total | `nvmlDeviceGetMemoryInfo` | `DCGM_FI_DEV_FB_USED` (+ `FB_FREE`, `FB_RESERVED` for the total) |
| Temperature | `nvmlDeviceGetTemperature(NVML_TEMPERATURE_GPU)` | `DCGM_FI_DEV_GPU_TEMP` |
| Power draw and limit | `nvmlDeviceGetPowerUsage`, `nvmlDeviceGetEnforcedPowerLimit` | `DCGM_FI_DEV_POWER_USAGE`, `DCGM_FI_DEV_POWER_MGMT_LIMIT` |
| Fan speed | `nvmlDeviceGetFanSpeed` | `DCGM_FI_DEV_FAN_SPEED` |
| SM and memory clocks | `nvmlDeviceGetClockInfo(NVML_CLOCK_SM / NVML_CLOCK_MEM)` | `DCGM_FI_DEV_SM_CLOCK`, `DCGM_FI_DEV_MEM_CLOCK` |
| Performance state | `nvmlDeviceGetPerformanceState` | `DCGM_FI_DEV_PSTATE` |
| Throttle reasons | `nvmlDeviceGetCurrentClocksEventReasons` (or `...ThrottleReasons` on older bindings) | `DCGM_FI_DEV_CLOCKS_EVENT_REASONS` or `DCGM_FI_DEV_CLOCK_THROTTLE_REASONS` |
| PCIe throughput | `nvmlDeviceGetPcieThroughput` (RX, TX) | `DCGM_FI_DEV_PCIE_RX_THROUGHPUT`, `DCGM_FI_DEV_PCIE_TX_THROUGHPUT` |
| Uncorrected ECC errors | `nvmlDeviceGetTotalEccErrors(UNCORRECTED, VOLATILE)` | `DCGM_FI_DEV_ECC_DBE_VOL_TOTAL` |
| XID errors | XID critical error events (`nvmlDeviceRegisterEvents`, `nvmlEventSetWait_v2`) | `DCGM_FI_DEV_XID_ERRORS` (last code, reported when it changes) |
| PCI bus id, MIG mode | `nvmlDeviceGetPciInfo`, `nvmlDeviceGetMigMode` | `pci_bus_id` label (MIG mode: not read) |
| Processes and their memory | `nvmlDeviceGetComputeRunningProcesses`, `nvmlDeviceGetGraphicsRunningProcesses` | not available |
| Per-process SM share | `nvmlDeviceGetProcessUtilization` | not available |
| Process name, user, container | `/proc/<pid>/comm`, `status`, `cgroup` | not available |

Every field is read on its own: a field that fails is `null` ("Not available"), the rest of
the reading still arrives.

### Fields that are typically unavailable

From NVIDIA's documentation of the calls above, not from measurements on real cards:

| Card class | Typically not available |
| ---------- | ----------------------- |
| Passively cooled data centre GPUs (A100, H100, L4, ...) | Fan speed (no fan on the card) |
| Consumer GeForce cards | Uncorrected ECC errors (no ECC memory or ECC off); per-process SM share; often per-process memory on Windows WDDM |
| Workstation cards with ECC off | ECC counters |
| MIG-enabled GPUs | Device utilization and per-process data at the parent GPU level (MIG instance metrics are on the roadmap) |
| vGPU guests and some containers | The process list (attribution then shows busy time as unattributed), sometimes power and clocks |
| Older drivers and bindings | `nvmlDeviceGetCurrentClocksEventReasons` (the agent falls back to the throttle reasons call), `nvmlSystemGetCudaDriverVersion_v2` |

The simulated hosts in the demo reproduce the first two rows: the H100 and L4 report no fan
speed, and the GeForce RTX 4090 reports no ECC and no
per-process SM share.

## Configuration reference

Every `GPUWATCH_*` variable is listed in
[configuration.md](configuration.md#agent). Problems such as "NVML init failed" or
processes shown as `pid N` are covered in [troubleshooting.md](troubleshooting.md).
