"""The configured storage, key, cache and mail backends are the ones actually used.

``make test-matrix`` reruns the whole suite with TEST_STORAGE=s3, TEST_KEY_MODE=kms and
TEST_MAIL_MODE=ses against Floci (provisioned by the local-floci Terraform) and with
TEST_CACHE=memory, so every other test also runs on every backend; these assert the wiring.
"""

from __future__ import annotations

import os
from datetime import timedelta

import pytest
from sqlalchemy import select

from gpuwatch.alerts.models import Channel
from gpuwatch.core.kv import MemoryKV, RedisKV
from gpuwatch.core.mail import SesMail, SmtpMail
from gpuwatch.core.sealing import KmsSealer, LocalSealer
from gpuwatch.core.storage import LocalStorage, S3Storage
from tests.integration.conftest import Api, WebhookReceiver, batch, gpu, now, sample

pytestmark = pytest.mark.integration


async def test_backends_match_the_matrix(api: Api) -> None:
    c = api.container
    storage = os.environ.get("TEST_STORAGE", "local")
    keys = os.environ.get("TEST_KEY_MODE", "local")
    cache = os.environ.get("TEST_CACHE", "redis")
    mail = os.environ.get("TEST_MAIL_MODE", "smtp")
    assert isinstance(c.storage, S3Storage if storage == "s3" else LocalStorage)
    assert isinstance(c.sealer, KmsSealer if keys == "kms" else LocalSealer)
    assert isinstance(c.kv, RedisKV if cache == "redis" else MemoryKV)
    assert isinstance(c.mail, SesMail if mail == "ses" else SmtpMail)


async def test_report_round_trips_through_the_storage_backend(api: Api) -> None:
    await api.set_rate("NVIDIA A100-SXM4-80GB", "1.00")
    host = await api.host()
    u = host.uuids[0]
    start = now().replace(minute=0, second=0) - timedelta(hours=2)
    await host.ok(
        batch([gpu(u)], [sample(u, start + timedelta(minutes=i), interval=60) for i in range(60)])
    )
    await api.rollup(start + timedelta(hours=1))
    report = await api.ok(
        "POST",
        "/api/v1/reports",
        {
            "group_by": "gpu",
            "start": start.isoformat(),
            "end": (start + timedelta(hours=1)).isoformat(),
        },
    )
    raw = await api.container.storage.get(f"reports/{report['id']}.csv")
    assert raw.startswith(b"gpu,cost_usd") and b"TOTAL,1.000000" in raw


async def test_webhook_secret_round_trips_through_the_key_backend(
    api: Api, webhook: WebhookReceiver
) -> None:
    created = await api.ok(
        "POST",
        "/api/v1/alerts/channels",
        {"name": "Hook", "kind": "webhook", "url": webhook.url, "secret": "s3cret-value-1"},
    )
    assert created["signed"] is True and "s3cret" not in str(created)
    async with api.container.db.sessionmaker() as s:
        row = await s.scalar(select(Channel).where(Channel.name == "Hook"))
    assert row is not None and row.sealed_secret and b"s3cret" not in row.sealed_secret
    assert (
        await api.container.sealer.open(row.sealed_secret, f"channel:{row.id}") == "s3cret-value-1"
    )
    await api.ok("POST", f"/api/v1/alerts/channels/{created['id']}/test")
    assert await api.deliver() == 1
    assert webhook.received[0].headers["x-gpuwatch-signature"].startswith("sha256=")
