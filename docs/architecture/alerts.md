# Alerts

Alerts tell someone when a GPU runs hot, fills its memory, drops off its host, or its agent
goes quiet, and again when it recovers. Code:
[`alerts/evaluator.py`](../../apps/api/src/gpuwatch/alerts/evaluator.py),
[`alerts/notifier.py`](../../apps/api/src/gpuwatch/alerts/notifier.py),
[`alerts/urls.py`](../../apps/api/src/gpuwatch/alerts/urls.py),
[`alerts/service.py`](../../apps/api/src/gpuwatch/alerts/service.py).

- [Rules](#rules)
- [Evaluation](#evaluation)
- [Fire exactly once, resolve exactly once](#fire-exactly-once-resolve-exactly-once)
- [The outbox](#the-outbox)
- [Delivery](#delivery)
- [Webhook payload and signature](#webhook-payload-and-signature)
- [Tests](#tests)

## Rules

| Field | Meaning |
| ----- | ------- |
| `kind` | `threshold`, `agent_offline` or `gpu_lost` |
| `metric` | `util_gpu`, `util_mem`, `mem_used_pct` (`100 * mem_used_mib / mem_total_mib`), `temp_c`, `power_w`, `power_pct` (`100 * power_w / power_limit_w`), `fan_pct` |
| `operator`, `threshold` | `gt` or `lt` |
| `duration_s` | 0 to 86,400: how long every sample must breach |
| Scope | All GPUs, or one host (`scope_host_id`), one GPU (`scope_gpu_id`), or hosts with a label (`scope_label`, `key=value`) |
| `severity` | `info`, `warning` or `critical` |
| `channel_ids` | Channels to notify |
| `notify_resolved` | Also notify when it resolves (default true) |
| `enabled` | Disabling resolves the rule's open events |

Built-in rules, created by the migration so alerting works before anyone configures it:
"Agent offline", "GPU lost", "GPU too hot" (`temp_c > 85` for 120 s, warning) and "GPU
memory almost full" (`mem_used_pct > 95` for 300 s, warning). Events appear in the
dashboard; add a channel to have them sent.

## Evaluation

The worker's `alerts` job runs every `ALERT_EVAL_INTERVAL_S` (15 s) under
`pg_try_advisory_xact_lock('gpuwatch:alerts')`. Evaluation is **stateless**: it reads the
stored raw samples and last-seen times, not an in-memory history, so any worker replica
can run it and a restart loses nothing.

### Threshold rules

For every non-retired GPU in scope, one aggregate query over `gpu_samples` in the last
`max(duration_s, 60)` seconds returns the sample count, the count that breach, the first
sample time and the newest value.

- **Fires** when there is no open event, every sample in the window breaches, and the
  window is long enough (`duration_s` is 0, or the first sample is at least `duration_s`
  old, with 15 s of slack for sample spacing). A metric the GPU does not report (NULL)
  never counts as a breach, so it never fires.
- **Resolves** symmetrically: when there is an open event, the newest value is known, and
  no sample over the same window breaches for `duration_s` (the newest sample alone when
  `duration_s` is 0). A GPU hovering at the threshold therefore stays one alert, with one
  "fired" and one "resolved" notification, instead of flapping.
- **No recent data:** nothing changes (an open event stays open; the offline and lost
  rules cover silence).
- **Out of scope** (GPU retired, rule rescoped, host revoked): open events resolve with
  "No longer in scope".

### Agent offline

For every non-revoked host in scope that has reported at least once: fires when it has not
reported for more than `HOST_OFFLINE_AFTER_S` (60 s), resolves when it reports again. With
the defaults, a silent agent raises the alert within 60 s plus one evaluation interval,
75 s, inside the 90 s of acceptance criterion 3.

### GPU lost

For every GPU in scope whose host is online: fires when the GPU's last sample is older
than the host's last batch by more than `max(30 s, 3 x host interval)` (it stopped
appearing in its host's reports); resolves when it reports again or is retired.

## Fire exactly once, resolve exactly once

- `alert_events` has the partial unique index
  `uq_alert_events_open (rule_id, target_key) WHERE resolved_at IS NULL`. `_fire()`
  inserts with `ON CONFLICT (rule_id, target_key) WHERE resolved_at IS NULL DO NOTHING
  RETURNING id`; when nothing comes back another evaluator already fired it, and nothing
  is notified. So even two evaluators racing, or a lock lost mid-run, cannot open two
  events for one condition (`test_concurrent_alert_evaluations_fire_once`).
- `_resolve()` runs `UPDATE ... WHERE id = :id AND resolved_at IS NULL` and notifies only
  when a row changed, so a resolution is sent once.
- Notifications are inserted in the **same transaction** as the event change. An event
  without its notifications, or a notification for an event that was rolled back, cannot
  exist.

Target keys are `gpu:<gpu id>` for threshold and lost rules and `host:<host id>` for the
offline rule.

## The outbox

`notifications` rows are the outbox: one per (event transition, channel), holding the
exact payload, `attempts`, `next_attempt_at`, `delivered_at`, `failed_at` and
`last_error`. Test notifications from the Channels tab ("Send test") go through the same
path with `transition = test`.

## Delivery

The worker's `notifications` job runs every 2 s:

1. Claim up to 20 due rows (`delivered_at` and `failed_at` NULL, `next_attempt_at <=
   now`) with `SELECT ... FOR UPDATE OF notifications SKIP LOCKED`, so several workers
   never send the same row.
2. For each, increment `attempts` and deliver:
   - **email:** subject = the payload title; a plain text body with the message, the rule
     and condition, start and resolve times and a link to the dashboard
     (`DASHBOARD_URL`). Sent by `MAIL_MODE`: `smtp` (Mailpit locally), `ses`, or `log`
     (written to the log, nothing delivered).
   - **webhook:** SSRF check of the URL (again, DNS may have changed), then `POST` of the
     JSON payload with the signature headers. Redirects are not followed; any status of
     300 or more is a failure.
3. On success, set `delivered_at` and the channel's `last_delivery_at`, clear errors.
4. On failure, record the error on the row and the channel; if `attempts` reached
   `MAX_ATTEMPTS` (8), set `failed_at` (shown as failed in Deliveries), else
   `next_attempt_at = now + min(3600, 30 * 2^(attempts - 1))` seconds: 30 s, 60 s,
   120 s, ... capped at one hour.

Metrics: `gpuwatch_notifications_total{channel, outcome}` with `delivered`, `retry` and
`failed`. On AWS an alarm fires on failed deliveries.

## Webhook payload and signature

Headers:

| Header | Value |
| ------ | ----- |
| `Content-Type` | `application/json` |
| `User-Agent` | `GPUWatch-Webhook/0.1` |
| `X-GPUWatch-Timestamp` | Unix seconds when the request was signed |
| `X-GPUWatch-Event` | `alert.fired`, `alert.resolved` or `test` |
| `X-GPUWatch-Signature` | `sha256=` + hex HMAC-SHA256(channel secret, `<timestamp>.<raw body>`), only when the channel has a secret |

Body for an alert transition:

```json
{
  "type": "alert.fired",
  "title": "[WARNING] GPU too hot",
  "message": "Temperature 88.0°C on GPU 3 on train-node-01 (> 85 for 120 s)",
  "rule": {"id": "...", "name": "GPU too hot", "kind": "threshold", "condition": "..."},
  "severity": "warning",
  "target": {"host_id": "...", "gpu_id": "...", "label": "GPU 3 on train-node-01"},
  "value": 88.0,
  "started_at": "2026-10-26T10:00:00+00:00",
  "resolved_at": null,
  "dashboard_url": "https://gpuwatch.example.com/gpus/..."
}
```

A resolution has `"type": "alert.resolved"`, a title ending in "resolved", the reason in
`message` and `resolved_at` set. A test has `type`, `title`, `message`, `dashboard_url` and
`sent_at`.

To verify: read the raw body bytes, recompute the HMAC over
`timestamp + "." + body`, compare with `X-GPUWatch-Signature` in constant time, and reject
timestamps too far from your clock (the example receiver allows 5 minutes):
[examples/webhook_receiver.py](../../examples/webhook_receiver.py).

## Tests

| Behaviour | Test |
| --------- | ---- |
| A hot GPU alerts once by email and signed webhook, and resolves once | `tests/integration/test_acceptance.py::test_6_a_hot_gpu_alerts_once_by_email_and_signed_webhook` |
| A silent agent is disconnected and alerts once | `test_acceptance.py::test_3_a_silent_agent_is_disconnected_and_alerts_once` |
| Built-in rules exist; rule validation; scope labels | `tests/integration/test_alerts.py::test_builtin_rules_exist_and_describe_themselves`, `test_rule_validation`, `test_rules_respect_their_scope_label` |
| An unreported metric never fires; a short breach does not fire a long rule | `test_alerts.py::test_a_metric_the_gpu_does_not_report_never_fires`, `test_a_short_breach_does_not_fire_a_long_rule` |
| Disabling a rule resolves its events; retiring a GPU resolves its lost alert | `test_alerts.py::test_disabling_a_rule_resolves_its_events`, `test_a_retired_gpu_resolves_its_lost_alert` |
| Webhooks cannot target metadata or odd schemes; secrets are sealed and never returned | `test_alerts.py::test_webhooks_cannot_target_metadata_or_odd_schemes`, `test_channel_crud_and_secret_handling` |
| Failed deliveries back off, then fail visibly | `test_alerts.py::test_failed_deliveries_back_off_then_fail_visibly` |
| Concurrent evaluations fire once | `tests/integration/test_hardening.py::test_concurrent_alert_evaluations_fire_once` |
| SSRF address classes, signature format, backoff, email text | `tests/unit/alerts/test_alerts_unit.py` |
