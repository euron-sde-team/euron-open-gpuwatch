# The Agent

`gpuwatch-agent` runs on each GPU machine, reads the GPUs, the processes on them and local
inference servers, and pushes one batch per interval to the API. It is observe only: no
inbound port, no command channel, nothing it receives is ever run. Code:
[`apps/agent/src/gpuwatch_agent`](../../apps/agent/src/gpuwatch_agent). Installation and
configuration are in the [agent guide](../guides/agent.md).

- [The loop](#the-loop)
- [Collectors](#collectors)
- [Process enrichment](#process-enrichment)
- [Inference servers](#inference-servers)
- [The spool](#the-spool)
- [Enrolment and re-enrolment](#enrolment-and-re-enrolment)
- [Degraded, not dead](#degraded-not-dead)
- [Simulated hosts](#simulated-hosts)
- [Tests](#tests)

## The loop

[`agent.py`](../../apps/agent/src/gpuwatch_agent/agent.py), `Agent.run()`:

1. Enrol if there is no host token (retrying every 5 s until the API answers).
2. Simulated hosts only: send the backfill once ([Simulated hosts](#simulated-hosts)).
3. Every `GPUWATCH_INTERVAL_S` (5 s):
   1. `collect(now)`: read the collector; the reading's `interval_s` is the time since the
      previous reading, at least 0.5 s and at most three intervals, so a pause never
      attributes hours to one sample.
   2. Scrape the configured inference servers.
   3. Build a batch with a fresh `batch_id` (UUID4).
   4. `deliver()`: send it; on a retryable failure, write it to the spool.
   5. After a successful send, `replay()` up to 20 spooled batches, oldest first.
4. Any exception in one interval is logged and the loop continues.

`SIGTERM` and `SIGINT` stop the loop after the current interval. Logs are JSON lines on
stdout.

## Collectors

One Protocol, `Collector.read(now, interval_s) -> Reading`, with one implementation per
source ([`collectors/`](../../apps/agent/src/gpuwatch_agent/collectors)). Adding a source
means adding a module, not editing the loop.

### `nvml` (default)

[`collectors/nvml.py`](../../apps/agent/src/gpuwatch_agent/collectors/nvml.py), through the
official `nvidia-ml-py` bindings. NVML is initialised once; an XID event set is created
and each GPU registers for critical XID events.

Every NVML call is wrapped individually: `NVML_ERROR_NOT_SUPPORTED` or any other error for
one field yields `None` for that field only ("Not available", never 0). The exceptions:

- `NVML_ERROR_GPU_IS_LOST` for a GPU: the GPU is left out of the reading and a `gpu_lost`
  problem is reported, so the server marks it lost.
- `nvmlInit` failing (no driver, no library, the container has no GPU access): the
  collector raises `CollectorUnavailableError("nvml_init_failed", ...)` and the agent
  reports degraded ([Degraded, not dead](#degraded-not-dead)).
- `nvmlDeviceGetCount` failing: `nvml_count_failed`, same handling.

The field-to-call mapping is in the [agent guide](../guides/agent.md#compatibility-matrix).
XID events are drained with `nvmlEventSetWait_v2(timeout 0)` once per reading; the latest
code per GPU is sent once in that interval's sample.

### `dcgm`

[`collectors/dcgm.py`](../../apps/agent/src/gpuwatch_agent/collectors/dcgm.py) reads an
existing DCGM exporter's `/metrics` (`GPUWATCH_DCGM_URL`) instead of opening NVML a second
time: the right choice on clusters that already run the NVIDIA GPU Operator. Each series
with a `UUID` label maps to a GPU; field names follow dcgm-exporter's default counters
(`DCGM_FI_DEV_GPU_UTIL`, `DCGM_FI_DEV_FB_USED`, `DCGM_FI_DEV_POWER_USAGE`,
`DCGM_FI_DEV_CLOCK_THROTTLE_REASONS` or `DCGM_FI_DEV_CLOCKS_EVENT_REASONS`,
`DCGM_FI_DEV_ECC_DBE_VOL_TOTAL`, `DCGM_FI_DEV_XID_ERRORS`, ...). Total memory is used plus
free plus reserved. A field the exporter is not configured to export is `None`. The
exporter shows the last XID code, which the collector reports once, when it changes.
**DCGM exporter does not list processes**, so on these hosts `procs` is NULL and busy time
is attributed as `(unattributed)`. An unreachable exporter is `dcgm_unreachable`; one
that lists no GPUs is `dcgm_no_gpus`.

### `simulated`

[`collectors/simulated.py`](../../apps/agent/src/gpuwatch_agent/collectors/simulated.py)
produces readings from [`sim.py`](../../apps/agent/src/gpuwatch_agent/sim.py): deterministic
functions of (machine, GPU, time), sent through the same batch format and ingest API.

## Process enrichment

NVML returns compute and graphics processes per GPU with their memory
(`nvmlDeviceGetComputeRunningProcesses`, `nvmlDeviceGetGraphicsRunningProcesses`), and SM
shares since the last call (`nvmlDeviceGetProcessUtilization`, with the timestamp of the
previous sample per GPU). A process present in the processes list but absent from a
utilization sample set used no SM time (0); when the driver gives no utilization samples
at all, `sm_util` is `None`. When both process calls fail, the driver does not list
processes in this environment and `procs` is `None` (not 0).

[`procinfo.py`](../../apps/agent/src/gpuwatch_agent/procinfo.py) resolves each pid from
`/proc/<pid>`:

- **name** from `comm` (or `pid <n>` when unreadable);
- **user** from the `Uid:` line of `status`, mapped through the password database (the
  numeric uid if unknown);
- **container id**: the first 64-hex id in `cgroup` (Docker, containerd, CRI-O,
  Kubernetes), kept as its first 12 characters.

In a container the agent needs `--pid=host`, or the GPU's pids do not exist in its pid
namespace and every process shows as `pid <n>`. Reading other users' `status` and
`cgroup` may need `CAP_SYS_PTRACE` or root.

## Inference servers

[`inference.py`](../../apps/agent/src/gpuwatch_agent/inference.py) scrapes each target in
`GPUWATCH_INFERENCE` (`name=vllm|tgi,url[,gpu_index+gpu_index]`, several separated by
`;`). Metric names, newest first where they changed between versions:

| Field | vLLM | TGI |
| ----- | ---- | --- |
| requests | `vllm:request_success_total` | `tgi_request_success` |
| prompt tokens | `vllm:prompt_tokens_total` | `tgi_request_input_length_sum` |
| generated tokens | `vllm:generation_tokens_total` | `tgi_request_generated_tokens_sum` |
| running | `vllm:num_requests_running` | `tgi_batch_current_size` |
| waiting | `vllm:num_requests_waiting` | `tgi_queue_size` |
| KV cache use | `vllm:kv_cache_usage_perc`, `vllm:gpu_cache_usage_perc` | not exposed |
| time to first token | `vllm:time_to_first_token_seconds` | not exposed |
| inter-token latency | `vllm:inter_token_latency_seconds`, `vllm:time_per_output_token_seconds` | `tgi_request_mean_time_per_token_duration` |
| end-to-end latency | `vllm:e2e_request_latency_seconds` | `tgi_request_duration` |

Servers expose cumulative counters and cumulative histogram buckets. The agent keeps the
previous scrape per endpoint and sends **per-interval deltas**:

- The first scrape after start (or after the server was unreachable) only primes the
  counters: counter and histogram fields are `None` for that interval.
- If any counter went down, the server restarted: the new values are the deltas since the
  restart (the previous snapshot is ignored).
- Histogram buckets are converted from cumulative to non-cumulative counts per bucket, so
  the server can sum them exactly across intervals and hours.
- Metrics the server does not expose are `None`; gauges are sent as read.
- An unreachable server is sent as `up: false`.
- `gpu_uuids` comes from the configured GPU indexes, resolved against the GPUs in the same
  reading; the model comes from a `model_name` or `model` label.

The API computes p50 and p95 from the merged buckets with PromQL's
`histogram_quantile` interpolation, and cost per million tokens from the bound GPUs' cost.

## The spool

[`spool.py`](../../apps/agent/src/gpuwatch_agent/spool.py) keeps batches the server could
not take in `<GPUWATCH_STATE_DIR>/spool/`:

- One JSON file per batch, named `<time_ns>-<batch_id>.json`, written to a temporary file
  and renamed, so a crash never leaves half a batch.
- Bounded by `GPUWATCH_SPOOL_MAX_MB` (200 MB): past it, the oldest files are deleted first.
- Replayed oldest first, up to 20 per interval after a successful send. A replay stops at
  the first retryable failure to keep the order. A batch the server refuses permanently
  (422, other 4xx) is dropped and logged. An unreadable file is deleted so it cannot block
  the queue.

What is retryable (`client.py`): connection errors, timeouts, 429 and 5xx. A 401 with
`invalid_host_token` or `host_revoked` triggers re-enrolment and keeps the batch. Any other
4xx means this batch will never be accepted and it is not spooled.

The batch id makes replays idempotent on the server; see
[ingest-and-rollups.md](ingest-and-rollups.md#idempotency).

## Enrolment and re-enrolment

- The enrolment token comes from `GPUWATCH_ENROLMENT_TOKEN` or the file named by
  `GPUWATCH_ENROLMENT_TOKEN_FILE`.
- The machine id is `GPUWATCH_MACHINE_ID`, else `/etc/machine-id`, else
  `/var/lib/dbus/machine-id`, else a random id stored in the state directory. Re-enrolling
  the same machine id keeps the host and its history on the server.
- `POST /ingest/v1/enroll` returns the host token, which is written to
  `<state dir>/host-token` with mode 0600 and used as `Authorization: Bearer gwh_...`.
- If the server answers 401 `invalid_host_token` (the token was rotated by another
  enrolment of the same machine) or `host_revoked`, the agent deletes its token, enrols
  again with its enrolment token, and resends the batch. A revoked host therefore comes
  back only if its enrolment token is still usable; revoke the token too to keep it out.
- Without any enrolment token, the agent logs what to do ("create one in GPUWatch, Hosts,
  Add a host") and keeps retrying.

## Degraded, not dead

A collector that cannot read at all raises `CollectorUnavailableError(code, message)`.
The agent catches it, sends a batch with no GPUs, `status: degraded` and the problem, and
tries again next interval. Partial failures (one GPU lost, one read failed) are sent as
problems alongside the readings of the healthy GPUs. The host page shows the reasons; the
GPUs that stopped reporting turn `lost`, and the built-in "GPU lost" alert fires
(acceptance criterion 10).

## Simulated hosts

For the demo and the tests, `GPUWATCH_COLLECTOR=simulated` with a profile:

| Profile | GPUs | Scenarios |
| ------- | ---- | --------- |
| `training` | 8 x NVIDIA H100 80GB HBM3 | GPUs 0 to 5 train from 01:00 to 22:00 UTC, then hold their weights idle while waiting for evaluation until 23:30, then sit empty; GPU 3 runs hot in the afternoon; GPU 5 reports an XID every other day. GPUs 6 and 7 hold notebook kernels all the time, busy only in weekday bursts |
| `inference` | 2 x NVIDIA L40S, 2 x NVIDIA L4 | A vLLM chat model with business-hours traffic and preallocated KV cache memory, a TGI summarizer at low utilization, a batch scoring job 15 minutes an hour, a spare card that never runs anything |
| `workstation` | 1 x NVIDIA GeForce RTX 4090 | A developer card used on weekdays, often left with a model loaded overnight, that draws more than its power limit when busy (power capped) |

Fields a real driver would not report on that hardware stay `None` (fan speed on passively
cooled data centre cards, ECC and per-process SM share on the consumer card). With
`GPUWATCH_SIM_BACKFILL_DAYS` set, the agent first sends that many days of history, one
hour per batch at one-minute resolution, including inference rows from the same traffic
model the mock vLLM server serves live, and writes a `backfilled` marker so it runs once
per state directory. The server accepts the old rows only because the host was enrolled
with a simulated token ([security.md](security.md#the-agent-trust-boundary)).

`gpuwatch-mock-vllm` ([`mockvllm.py`](../../apps/agent/src/gpuwatch_agent/mockvllm.py))
serves `/metrics` (vLLM names), `/tgi/metrics` (TGI names) and `/health`, with counters and
histograms that grow with the same traffic model, so GPU utilization and serving metrics
move together.

## Tests

| Behaviour | Test |
| --------- | ---- |
| NVML reads every supported field and leaves the rest null | `apps/agent/tests/test_collectors.py::test_nvml_reads_every_supported_field_and_leaves_the_rest_null` |
| No process utilization: SM share null; no process listing: procs null | `test_collectors.py::test_nvml_without_process_utilization_leaves_sm_share_null`, `test_nvml_when_the_driver_does_not_list_processes` |
| A lost GPU is left out and reported; NVML init failure is unavailable, not a crash | `test_collectors.py::test_a_lost_gpu_is_left_out_and_reported`, `test_nvml_init_failure_is_unavailable_not_a_crash` |
| XID events go to their GPU once | `test_collectors.py::test_xid_events_are_attributed_to_their_gpu_once` |
| DCGM exporter output maps to samples | `test_collectors.py::test_dcgm_exporter_output_maps_to_samples` |
| Process details from /proc | `test_collectors.py::test_process_details_from_proc` |
| Counter deltas, restarts, TGI without TTFT, unreachable servers, the mock server through the real scraper | `apps/agent/tests/test_inference.py` |
| Enrols once, spools and replays in order, refused batches dropped, re-enrolment, degraded collector, capped interval, backfill once, bounded spool | `apps/agent/tests/test_agent.py` |
| The agent never runs or kills anything, and listens nowhere | `test_agent.py::test_observe_only_the_agent_never_runs_or_kills_anything` |

The NVML tests run against [`tests/fakenvml.py`](../../apps/agent/tests/fakenvml.py), a fake
of the `pynvml` module with the same function names, return shapes (named tuples, bytes or
str, milliwatts, bytes of memory) and error behaviour (`NOT_SUPPORTED`, `GPU_IS_LOST`,
`DRIVER_NOT_LOADED`, `TIMEOUT`). No real GPU was available while building 0.1.0.
