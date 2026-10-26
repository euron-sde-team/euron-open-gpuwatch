# Quickstart: run GPUWatch locally

The whole stack on your machine with Docker, no GPU and no AWS account needed. Three
simulated GPU hosts send data through the same ingest API a real agent uses, with 30 days
of history.

## Prerequisites

- Docker with Compose v2 (Docker Desktop, OrbStack, or Docker Engine on Linux).
- `make`, `bash` and `openssl` (preinstalled on macOS and most Linux distributions).
- Free local ports 4410, 4425, 4426, 4430, 4442, 4450, 4466 and 4479 (override any of them
  in `deploy/compose/.env`, see [configuration.md](configuration.md#local-stack-ports)).

uv and pnpm are needed only to run tests outside containers ([testing.md](testing.md)).

## 1. Start the stack

```bash
git clone https://github.com/euron-sde-team/euron-open-gpuwatch.git
cd euron-open-gpuwatch
make up
```

`make up` first runs `make env`, which writes `deploy/compose/.env` with random,
local-only secrets (`SESSION_SECRET`, `API_KEY_PEPPER`, `LOCAL_MASTER_KEY`,
`GW_DEMO_PASSWORD`) unless it already exists. Then it builds the images and starts, in
order:

| Service | What it is |
| ------- | ---------- |
| `postgres` | PostgreSQL 16 (`localhost:4442`) |
| `redis` | Redis 7 for the live view and rate limits (`localhost:4479`) |
| `mailpit` | Catches alert email (UI on `localhost:4425`, SMTP on 4426) |
| `floci` | The local AWS emulator (`localhost:4466`) |
| `terraform` | One-shot: applies `infra/terraform/envs/local-floci` to Floci (reports bucket, KMS key, secrets, SES identity) |
| `migrate` | One-shot: applies the Alembic migrations |
| `api` | The API (`localhost:4430`, docs at `/docs`) |
| `worker` | Rollups, attribution, insights, alerts, notifications, retention |
| `web` | The dashboard (`localhost:4410`) |

When it finishes it prints the URLs. The first build takes a few minutes.

## 2. Load the demo

```bash
make demo
```

This does two things:

1. `gpuwatch seed-demo` inside the API container creates the demo configuration: three
   users, example hourly rates for the four simulated GPU models (labelled "Example rate
   for the demo; set your own"), five workload rules, an email channel that lands in
   Mailpit wired to the warning and critical alert rules, an extra "Training GPU too hot"
   rule, a read-only API key, and a simulated enrolment token written where the demo
   agents read it.
2. Starts the `demo` profile: a mock vLLM server and three simulated agents (the real agent
   with its simulated collector):

   | Host | GPUs | What it shows |
   | ---- | ---- | ------------- |
   | `train-node-01` (labels `role=training,site=dc-1`) | 8 x H100 80GB | A training job with a nightly checkpoint wait, one GPU running hot, an occasional XID, two notebook GPUs holding models |
   | `infer-node-01` (labels `role=inference,site=dc-1`) | 2 x L40S, 2 x L4 | vLLM (`llama-chat`) and TGI (`summarizer`) endpoints scraped from the mock server, a batch scoring job, a spare card |
   | `dev-workstation` (labels `role=dev,site=office`) | 1 x GeForce RTX 4090 | A developer card left loaded overnight and power capped when busy |

`seed-demo` prints the logins:

```
  dashboard login   owner@gpuwatch.local / <GW_DEMO_PASSWORD from deploy/compose/.env>
                    admin@gpuwatch.local, viewer@gpuwatch.local (same password)
  read-only API key gwk_...            (printed only the first time)
  alert email       http://localhost:4425 (Mailpit)
```

The agents first backfill `GW_DEMO_DAYS` (30) days of history, one hour per batch, which
takes a minute or two, then report live every 5 s. Follow one with
`make logs SERVICE=agent-train`. Costs, insights and charts fill in as the worker rolls
the backfill up.

## 3. Look around

Open <http://localhost:4410> and sign in as `owner@gpuwatch.local`.

- **Overview:** spend over the last 7 days and this month, the share paid for idle time,
  estimated waste per month, top workloads and top findings.
- **Live:** all 13 GPUs as tiles, updating every few seconds over server-sent events. The
  RTX 4090 shows "Not available" for fields a consumer card does not report.
- **A GPU page** (click a tile): history charts, the processes on it now, who used it over
  the last day, and the "explain this GPU" summary.
- **Insights:** findings such as the notebook GPUs idle with a model loaded, the spare L4
  with nothing running, the power-capped workstation, the thermally throttled H100 and
  queueing on the chat model, each with its evidence and, for spend findings, an estimated
  monthly cost. (The simulator follows the clock, so the exact set depends on when you
  look.)
- **Costs:** spend by workload, team, host, GPU or model; the rates, workload rules and
  CSV reports tabs.
- **Alerts:** events from the built-in and demo rules, and the email in Mailpit at
  <http://localhost:4425>.
- **Inference:** TTFT, tokens per second and cost per million tokens for `llama-chat` and
  `summarizer`.

The [walkthrough](walkthrough.md) tours every screen.

Try the API with the read-only key:

```bash
curl -s -H "Authorization: Bearer gwk_..." http://localhost:4430/api/v1/gpus | head -c 400
```

or run the [examples](../../examples/README.md).

## 4. Add a real agent (optional)

On a machine with an NVIDIA GPU that can reach your API, create an enrolment token in
Hosts, "Add a host", and follow the command it shows. The [agent guide](agent.md) covers
Docker, pip, DCGM exporter mode and inference endpoints.

## 5. Stop

```bash
make down
```

This stops every container, including the demo agents, and **deletes the volumes**
(database, Floci state, agent state). `deploy/compose/.env` is kept, so the next `make up`
uses the same demo password.

## Useful targets

| Target | What it does |
| ------ | ------------ |
| `make ps` | Container status |
| `make logs SERVICE=api` | Tail one service (`worker`, `web`, `floci`, `agent-infer`, ...) |
| `make admin EMAIL=you@example.com` | Create or reset an owner (prompts for the password) |
| `make bench` | Ingest and dashboard latency against the running stack |
| `make help` | Every target |

Problems? See [troubleshooting.md](troubleshooting.md).
