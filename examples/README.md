# Examples

Small, standard-library-only Python scripts (Python 3.11 or newer) against a running
GPUWatch. They work with the local stack (`make up && make demo`, API at
`http://localhost:4430`).

| Script | What it shows |
| ------ | ------------- |
| [`idle_report.py`](idle_report.py) | Read-only automation with a `gwk_` API key: the cost split over a window (`GET /api/v1/costs`) and the open idle findings with their evidence (`GET /api/v1/insights?status=open`), most costly first |
| [`webhook_receiver.py`](webhook_receiver.py) | The alert webhook contract: verifying `X-GPUWatch-Signature` (HMAC-SHA256 over `<timestamp>.<body>`), refusing timestamps older than 5 minutes, printing the alert |

## idle_report.py

`make demo` prints a read-only key the first time it runs ("read-only API key gwk_...").
You can also create one in the dashboard (API keys, Create key; admins only).

```bash
GPUWATCH_API_KEY=gwk_... python examples/idle_report.py
python examples/idle_report.py --url https://gpuwatch.example.com --key gwk_... --days 30 --top 10
```

Output from a demo run (numbers depend on your fleet, your rates and the time of day):

```
Last 7 days: $3,999.68 total, $1,284.26 idle
  $364.33 with nothing running, $919.92 with a workload holding the GPU

Top idle findings (6 open):
- GPU 7 on train-node-01: model loaded, idle, 142.8 h (85% of monitored time), $355.45 in the window, about $1,525.06 a month
- GPU 3 on infer-node-01: nothing running, 167.3 h (100% of monitored time), $100.41 in the window, about $430.83 a month
```

API keys are read-only and rate limited (600 requests a minute unless the key has its own
limit). Money fields are integer nano-dollars; the script divides by 10^9.

## webhook_receiver.py

```bash
GPUWATCH_WEBHOOK_SECRET='a-long-random-secret' python examples/webhook_receiver.py --port 8787
```

Then, in the dashboard, Alerts, Channels, **Add channel**: kind webhook, the receiver's
URL, and the same secret. From the local Compose stack the worker runs in a container, so
use an address it can reach, for example `http://host.docker.internal:8787/` with Docker
Desktop or OrbStack (on Linux, the Docker bridge address of the host). Private and
loopback targets are allowed by default locally (`WEBHOOK_ALLOW_PRIVATE=true`). Click
**Send test**, and the receiver prints:

```
test: GPUWatch test notification
  owner@gpuwatch.local sent a test from the dashboard.
  dashboard_url: http://localhost:4410
```

Attach the channel to an alert rule to receive `alert.fired` and `alert.resolved` events.
The payload format is documented in
[docs/architecture/alerts.md](../docs/architecture/alerts.md#webhook-payload-and-signature).
A request with a wrong signature or a stale timestamp gets 401 and is not printed.
