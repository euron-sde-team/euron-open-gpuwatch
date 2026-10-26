"""Delivers the notification outbox: email and signed webhooks, with retries.

Rows are claimed with ``FOR UPDATE SKIP LOCKED``, so several workers never send the same
notification. A failure is retried with exponential backoff (30 s doubling, at most an
hour apart) up to ``MAX_ATTEMPTS``, then marked failed and shown in the dashboard.

Webhook requests carry ``X-GPUWatch-Timestamp`` and, when the channel has a secret,
``X-GPUWatch-Signature: sha256=<hex>``, the HMAC-SHA256 of ``<timestamp>.<body>``.
Receivers recompute it and reject old timestamps to stop replays.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import orjson
from sqlalchemy import select

from gpuwatch.alerts.models import Channel, Notification
from gpuwatch.alerts.urls import check_webhook_url
from gpuwatch.core.container import Container
from gpuwatch.observability import metrics

log = logging.getLogger("gpuwatch.notifier")
MAX_ATTEMPTS = 8
BATCH = 20


def signature(secret: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(3600, 30 * 2 ** max(0, attempts - 1)))


def email_text(payload: dict[str, Any]) -> tuple[str, str]:
    subject = str(payload.get("title") or "GPUWatch notification")
    lines = [str(payload.get("message") or "")]
    if payload.get("rule"):
        lines += ["", f"Rule: {payload['rule']['name']} ({payload['rule']['condition']})"]
    if payload.get("started_at"):
        lines.append(f"Started: {payload['started_at']}")
    if payload.get("resolved_at"):
        lines.append(f"Resolved: {payload['resolved_at']}")
    if payload.get("dashboard_url"):
        lines += ["", f"Open in GPUWatch: {payload['dashboard_url']}"]
    lines += ["", "You receive this because a GPUWatch alert rule notifies this address."]
    return subject, "\n".join(lines)


async def _deliver(container: Container, channel: Channel, payload: dict[str, Any]) -> None:
    if channel.kind == "email":
        subject, body = email_text(payload)
        await container.mail.send([str(e) for e in channel.emails], subject, body)
        return
    assert channel.url is not None
    await check_webhook_url(channel.url, allow_private=container.settings.webhook_allow_private)
    raw = orjson.dumps(payload)
    timestamp = str(int(time.time()))
    headers = {
        "content-type": "application/json",
        "user-agent": "GPUWatch-Webhook/0.1",
        "x-gpuwatch-timestamp": timestamp,
        "x-gpuwatch-event": str(payload.get("type", "")),
    }
    if channel.sealed_secret:
        secret = await container.sealer.open(channel.sealed_secret, f"channel:{channel.id}")
        headers["x-gpuwatch-signature"] = signature(secret, timestamp, raw)
    response = await container.http.post(channel.url, content=raw, headers=headers)
    if response.status_code >= 300:
        raise httpx.HTTPStatusError(
            f"webhook answered {response.status_code}", request=response.request, response=response
        )


async def deliver_pending(container: Container, now: datetime | None = None) -> int:
    """Send up to one batch of due notifications. Returns how many were attempted."""
    now = now or datetime.now(UTC)
    async with container.db.sessionmaker() as session:
        rows = (
            await session.execute(
                select(Notification, Channel)
                .join(Channel, Channel.id == Notification.channel_id)
                .where(
                    Notification.delivered_at.is_(None),
                    Notification.failed_at.is_(None),
                    Notification.next_attempt_at <= now,
                )
                .order_by(Notification.next_attempt_at)
                .limit(BATCH)
                .with_for_update(of=Notification, skip_locked=True)
            )
        ).all()
        for note, channel in rows:
            note.attempts += 1
            try:
                await _deliver(container, channel, note.payload)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"[:500]
                note.last_error = error
                channel.last_error = error
                if note.attempts >= MAX_ATTEMPTS:
                    note.failed_at = now
                    metrics.NOTIFICATIONS.labels(channel.kind, "failed").inc()
                else:
                    note.next_attempt_at = now + backoff(note.attempts)
                    metrics.NOTIFICATIONS.labels(channel.kind, "retry").inc()
                log.warning("notification failed", extra={"channel": channel.name, "error": error})
            else:
                note.delivered_at = now
                note.last_error = None
                channel.last_delivery_at = now
                channel.last_error = None
                metrics.NOTIFICATIONS.labels(channel.kind, "delivered").inc()
        await session.commit()
        return len(rows)
