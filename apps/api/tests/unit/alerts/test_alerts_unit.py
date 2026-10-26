"""Webhook URL checks, signatures, backoff, email text and rule descriptions."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
from datetime import timedelta

import pytest

from gpuwatch.alerts.models import AlertRule
from gpuwatch.alerts.notifier import backoff, email_text, signature
from gpuwatch.alerts.service import describe
from gpuwatch.alerts.urls import WebhookUrlError, _blocked, check_webhook_url


@pytest.mark.parametrize(
    ("ip", "private_ok", "blocked"),
    [
        ("169.254.169.254", True, True),
        ("fd00:ec2::254", True, True),
        ("100.100.100.200", True, True),  # Alibaba Cloud metadata, inside CGNAT space
        ("fe80::1", True, True),
        ("0.0.0.0", True, True),
        ("224.0.0.1", True, True),
        ("127.0.0.1", True, False),
        ("::1", True, False),
        ("10.1.2.3", True, False),
        ("100.64.0.1", True, False),
        ("10.1.2.3", False, True),
        ("100.64.0.1", False, True),
        ("::1", False, True),
        ("93.184.216.34", False, False),
    ],
)
def test_blocked_addresses(ip: str, private_ok: bool, blocked: bool) -> None:
    assert (_blocked(ipaddress.ip_address(ip), private_ok) is not None) is blocked


async def test_check_refuses_bad_schemes_and_hosts() -> None:
    for url in ("ftp://x.test/", "http:///nohost", "http://169.254.169.254/latest"):
        with pytest.raises(WebhookUrlError):
            await check_webhook_url(url, allow_private=True)
    await check_webhook_url("http://127.0.0.1:9/x", allow_private=True)
    with pytest.raises(WebhookUrlError, match="Cannot resolve"):
        await check_webhook_url("http://does-not-exist.invalid/x", allow_private=True)


def test_signature_is_hmac_of_timestamp_and_body() -> None:
    expected = hmac.new(b"k", b"123.{}", hashlib.sha256).hexdigest()
    assert signature("k", "123", b"{}") == f"sha256={expected}"


def test_backoff_doubles_and_caps_at_an_hour() -> None:
    assert [backoff(n) for n in (1, 2, 3)] == [
        timedelta(seconds=30),
        timedelta(seconds=60),
        timedelta(seconds=120),
    ]
    assert backoff(20) == timedelta(hours=1)


def test_email_text_carries_the_rule_and_a_link() -> None:
    subject, body = email_text(
        {
            "title": "[CRITICAL] Hot",
            "message": "Temperature 90",
            "rule": {"name": "Hot", "condition": "Temperature above 85°C"},
            "started_at": "2026-10-26T10:00:00+00:00",
            "dashboard_url": "http://d.test/gpus/1",
        }
    )
    assert subject == "[CRITICAL] Hot"
    assert "Rule: Hot (Temperature above 85°C)" in body and "http://d.test/gpus/1" in body
    assert email_text({})[0] == "GPUWatch notification"


def test_rule_descriptions() -> None:
    assert (
        describe(AlertRule(kind="agent_offline", duration_s=0)) == "A host's agent stops reporting"
    )
    assert describe(AlertRule(kind="gpu_lost", duration_s=0)).startswith("A GPU disappears")
    assert (
        describe(
            AlertRule(
                kind="threshold", metric="mem_used_pct", operator="gt", threshold=95, duration_s=300
            )
        )
        == "Memory used above 95% for 5 min"
    )
    assert (
        describe(
            AlertRule(
                kind="threshold", metric="util_gpu", operator="lt", threshold=5, duration_s=30
            )
        )
        == "GPU utilization below 5% for 30 s"
    )
    assert (
        describe(
            AlertRule(
                kind="threshold", metric="power_w", operator="gt", threshold=300, duration_s=0
            )
        )
        == "Power draw above 300W"
    )
