# Troubleshooting

Symptoms, causes and fixes. Agent logs are JSON lines (`docker logs gpuwatch-agent`, or
`make logs SERVICE=agent-train` for the demo); API and worker logs via
`make logs SERVICE=api` or `SERVICE=worker`.

- [The agent cannot enrol](#the-agent-cannot-enrol)
- [NVML init failed](#nvml-init-failed)
- [Processes show as "pid N"](#processes-show-as-pid-n)
- [A GPU shows as lost](#a-gpu-shows-as-lost)
- [A host shows as disconnected](#a-host-shows-as-disconnected)
- [No costs: no rates](#no-costs-no-rates)
- [Busy time shows as "Unattributed"](#busy-time-shows-as-unattributed)
- [Alert email is not delivered](#alert-email-is-not-delivered)
- [webhook_url_blocked](#webhook_url_blocked)
- [The live view says "Refreshing every 5 s"](#the-live-view-says-refreshing-every-5-s)
- [Rows are dropped](#rows-are-dropped)
- [429 rate_limited or 413 payload_too_large from ingest](#429-rate_limited-or-413-payload_too_large-from-ingest)
- [Local stack problems](#local-stack-problems)

## The agent cannot enrol

The agent logs `waiting to enrol` with an `error` field and retries every 5 s.

| Error | Cause | Fix |
| ----- | ----- | --- |
| `cannot reach GPUWatch: ...` | Wrong `GPUWATCH_URL`, DNS, firewall, or the API is down | `curl $GPUWATCH_URL/healthz` from the machine. Locally the API is on port 4430 (not the dashboard's 4410); on AWS use the deployment URL over HTTPS. Allow egress to 443 |
| `401 This enrolment token is not valid...` | The token is mistyped, expired, revoked, or has reached its machine limit | Create a new token in Hosts, Add a host. The Enrolment tokens list shows which are usable |
| `No host token and no GPUWATCH_ENROLMENT_TOKEN...` | No token configured and no stored host token | Set `GPUWATCH_ENROLMENT_TOKEN` or `GPUWATCH_ENROLMENT_TOKEN_FILE` |
| `422 ...` on enrol | `GPUWATCH_MACHINE_ID` or labels have characters the API refuses | Machine ids: 8 to 128 of `A-Z a-z 0-9 . _ : -`; label keys: `A-Z a-z 0-9 _ . -` |

After a successful enrolment the agent logs `enrolled` with the `host_id`, and the host
appears in Hosts within one interval.

## NVML init failed

The host shows as degraded with `nvml_init_failed: NVML could not start (...)`, and
`gpuwatch-agent check` exits with code 2.

- **Docker:** the container has no GPU access. Run it with `--gpus all` and install the
  NVIDIA Container Toolkit on the host (`docker run --rm --gpus all ubuntu nvidia-smi`
  must work). The image does not contain `libnvidia-ml.so`; the toolkit mounts it.
- **pip install:** the NVIDIA driver is not installed or not loaded on this machine
  (`nvidia-smi` fails), or `libnvidia-ml.so.1` is not on the library path.
- **After a driver upgrade without a reboot:** NVML reports a driver/library version
  mismatch. Reboot or reload the kernel module.

The agent keeps running and retries every interval, so it recovers by itself once the
cause is fixed. With a DCGM exporter instead, the problems are `dcgm_unreachable` (check
`GPUWATCH_DCGM_URL`) or `dcgm_no_gpus`.

## Processes show as "pid N"

The agent found the process ids through NVML but could not read `/proc/<pid>`.

- In Docker, add `--pid=host`: without it, the host's GPU process ids do not exist in the
  container's pid namespace.
- With `--pid=host`, names may still be missing for other users' processes because the
  agent runs as UID 10001: add `--cap-add SYS_PTRACE` or run with `--user 0`.
- Workload rules match on names, so unresolved processes are attributed to `pid N`
  workloads until this is fixed. After fixing it, apply the rules to recent history
  (Costs, Workload rules).

## A GPU shows as lost

"Lost" means the host still reports but this GPU stopped appearing in its batches for
longer than `max(30 s, 3 x interval)`. The built-in "GPU lost" alert fires.

- The host page lists the agent's problems: `gpu_lost: GPU N is lost (fell off the bus);
  reset it` comes from NVML's `GPU_IS_LOST` (a hardware or driver fault: check `dmesg`
  for XID errors, reset the GPU or reboot).
- The GPU was removed, or is no longer visible to the agent (container started with
  specific `--gpus` devices, `CUDA_VISIBLE_DEVICES` style restrictions, MIG
  reconfiguration).
- If it was taken out of service on purpose, **Retire** it on the GPU page; the alert
  resolves. A retired GPU that reports again comes back by itself.

## A host shows as disconnected

No batch for `HOST_OFFLINE_AFTER_S` (60 s). The "Agent offline" alert fires. Check that the
agent runs, its logs (`batch spooled` means it cannot reach the API and is buffering to
disk), and the API's health. When it reconnects it replays the spool, and history fills in.
A host that was revoked shows as revoked instead, and its batches get `host_revoked`.

## No costs: no rates

Costs and cost figures in insights stay empty until a GPU has an hourly rate. GPUWatch
ships no prices.

- Add a rate in Costs, Rates: per GPU model (covers every GPU with that exact name), per
  host, or per GPU. The overview shows "unpriced GPU hours" while some GPUs have none.
- A model rate must match the GPU name exactly as the driver reports it (for example
  `NVIDIA H100 80GB HBM3`); the rate dialog offers the models in your fleet.
- Costs need at least one rolled-up hour of data; they appear a minute or two after the
  first samples.

## Busy time shows as "Unattributed"

The GPU was busy, but the driver listed no processes: common with the DCGM exporter
collector (it does not export processes), vGPU guests and some containers. Use the NVML
collector on the host with `--pid=host` where you need per-workload costs.

## Alert email is not delivered

- **`MAIL_MODE=log` (the default outside Compose and AWS):** email is written to the log,
  not sent. The worker logs `mail not delivered (MAIL_MODE=log)` and the delivery counts as
  successful. Set `MAIL_MODE=smtp` with `SMTP_HOST` and `SMTP_PORT`, or `MAIL_MODE=ses`.
- **Locally:** the stack sends to Mailpit; open <http://localhost:4425>.
- **No channel on the rule:** events show in Alerts but nothing is sent until the rule has
  a channel. Alerts, Channels, **Send test** checks a channel end to end.
- **SES sandbox:** SES only delivers to verified addresses until the account has production
  access. Alerts, Deliveries shows the error, and the AWS alarm on failed deliveries fires.
- **Retries:** a failing delivery is retried with backoff up to 8 times (Deliveries shows
  attempts and the last error), then marked failed.

## webhook_url_blocked

Saving a webhook channel (or delivering to it) failed the SSRF check. The message names the
resolved address and why:

- `a link-local or cloud metadata address`: 169.254.0.0/16, fe80::/10 or the AWS IPv6
  metadata address. Always refused.
- `a private or loopback address (WEBHOOK_ALLOW_PRIVATE is false)`: the receiver is on a
  private network and the deployment refuses those (the AWS environments default to
  `false`). Set `webhook_allow_private = true` (Terraform) or `WEBHOOK_ALLOW_PRIVATE=true`
  if the receiver is meant to be internal; on AWS also allow its port with
  `webhook_egress` if it is not 443.
- `Cannot resolve <host>`: DNS from the API or worker cannot resolve the name.
- `Use an http:// or https:// URL`: another scheme.

Redirects are not followed; point the channel at the final URL.

## The live view says "Refreshing every 5 s"

The dashboard could not keep the server-sent event stream (`/api/v1/live/stream`) open, so
it polls `/api/v1/live` every 5 s instead and retries the stream every 15 s. Data is still
current within 5 s.

- A reverse proxy in front of the dashboard buffers or times out streaming responses.
  Disable buffering for `/api/v1/live/stream` (the API sends `X-Accel-Buffering: no` and
  `Cache-Control: no-cache`) and allow long-lived connections; the stream sends a
  heartbeat comment every 15 s.
- A network blip or an API restart; it reconnects by itself.

If tiles show no data at all, the agents are not reporting (see the host status) rather
than a streaming problem. With Redis down the stream still works, sending a snapshot every
5 s from Postgres.

## Rows are dropped

The ingest reply's `dropped` count and `gpuwatch_ingest_dropped_total` show refused rows:

- `reason="time_window"`: the machine's clock is more than 120 s ahead
  (`INGEST_MAX_FUTURE_S`), or rows are older than `RAW_RETENTION_DAYS` (a spool from a long
  outage). Fix the clock (NTP).
- `reason="unknown_gpu"`: samples for a GPU UUID the batch did not declare in its
  inventory; only seen with a custom or modified agent.

## 429 rate_limited or 413 payload_too_large from ingest

- **429:** more than `INGEST_RPM_PER_HOST` (240) batches a minute from one host, usually
  several agents sharing one host token (each machine needs its own enrolment), or a very
  short `GPUWATCH_INTERVAL_S`. The agent spools and retries.
- **413 / `batch_too_large`:** a batch over `MAX_BODY_BYTES` or `INGEST_MAX_SAMPLES` rows,
  for example a machine with very many processes. Raise the limits if it is legitimate.

## Local stack problems

- **`make up` fails on a port:** another service uses one of 4410, 4425, 4426, 4430, 4442,
  4450, 4466 or 4479. Override it in `deploy/compose/.env` (`GW_WEB_PORT=...`, see
  [configuration.md](configuration.md#local-stack-ports)).
- **`run make env first`:** `deploy/compose/.env` is missing; `make up` creates it, or run
  `make env`.
- **The demo shows no history yet:** the agents backfill 30 days first (a minute or two);
  `make logs SERVICE=agent-train` shows `backfilled N hours of simulated history`. The
  worker then rolls the history up over the next minutes.
- **Forgot the demo password:** it is `GW_DEMO_PASSWORD` in `deploy/compose/.env`.
- **Start fresh:** `make down` (deletes all volumes), then `make up && make demo`.
