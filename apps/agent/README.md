# GPUWatch agent

Collects NVIDIA GPU metrics on one machine and sends them to a Euron Open GPUWatch server.
Observe only: it opens no port, accepts no commands, and never starts or stops a process.

```bash
docker run -d --name gpuwatch-agent --restart unless-stopped \
  --gpus all --pid=host \
  -e GPUWATCH_URL=https://gpuwatch.example.com \
  -e GPUWATCH_ENROLMENT_TOKEN=gwe_... \
  -v gpuwatch-agent:/var/lib/gpuwatch-agent \
  gpuwatch-agent:local run
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `GPUWATCH_URL` | `http://localhost:4430` | The GPUWatch API |
| `GPUWATCH_ENROLMENT_TOKEN` (or `_FILE`) | none | From Hosts, Add a host; exchanged once for a host token |
| `GPUWATCH_COLLECTOR` | `nvml` | `nvml`, `dcgm` (reads `GPUWATCH_DCGM_URL`) or `simulated` |
| `GPUWATCH_INTERVAL_S` | `5` | Seconds between readings |
| `GPUWATCH_LABELS` | none | `key=value,key=value` attached to the host |
| `GPUWATCH_INFERENCE` | none | `name=vllm\|tgi,url,gpu_index+gpu_index;...` |
| `GPUWATCH_STATE_DIR` | `/var/lib/gpuwatch-agent` | Host token, spool, machine id |

`gpuwatch-agent check` reads the GPUs once and prints what it found, including which metrics
this hardware does not report. See `docs/guides/agent.md` in the repository for the full
guide and the compatibility matrix.
