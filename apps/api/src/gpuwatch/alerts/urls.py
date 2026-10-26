"""Webhook URL checks: a webhook URL is something an admin types, and the worker then posts
to it. Without a check, that turns GPUWatch into a proxy for cloud metadata endpoints
(instance credentials) and other internal hosts.

Checked when a channel is saved and again before every delivery (DNS may have changed).
Always refused: link-local addresses (169.254.0.0/16, fe80::/10, which include the AWS, GCP
and Azure metadata endpoints), the AWS IPv6 and Alibaba Cloud metadata addresses, multicast,
unspecified and reserved addresses. Loopback and private networks are allowed by default because an
internal chat relay is a common target; set WEBHOOK_ALLOW_PRIVATE=false to refuse them too.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from gpuwatch.core.errors import AppError

AWS_IPV6_METADATA = ipaddress.ip_address("fd00:ec2::254")
# Metadata endpoints outside link-local space: AWS over IPv6, Alibaba Cloud in CGNAT space.
METADATA = {AWS_IPV6_METADATA, ipaddress.ip_address("100.100.100.200")}
# Shared address space (carrier-grade NAT): internal, but Python does not call it private.
CGNAT = ipaddress.ip_network("100.64.0.0/10")


class WebhookUrlError(AppError):
    code = "webhook_url_blocked"


def _blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, allow_private: bool) -> str | None:
    if ip.is_link_local or ip in METADATA:
        return "a link-local or cloud metadata address"
    if ip.is_unspecified or ip.is_multicast:
        return "an unspecified or multicast address"
    # Before the reserved check: Python counts ::1 (IPv6 loopback) as reserved, and 0.0.0.0
    # as private, so the order of these checks matters.
    if ip.is_loopback or ip.is_private or (ip.version == 4 and ip in CGNAT):
        if not allow_private:
            return "a private or loopback address (WEBHOOK_ALLOW_PRIVATE is false)"
        return None
    if ip.is_reserved:
        return "a reserved address"
    return None


async def check_webhook_url(url: str, *, allow_private: bool) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise WebhookUrlError("Use an http:// or https:// URL")
    host = parts.hostname
    if not host:
        raise WebhookUrlError(
            "The URL has no host. Use a full URL such as https://hooks.example.com/x"
        )
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise WebhookUrlError(
            f"Cannot resolve {host}. Check the host name, or that GPUWatch can reach it."
        ) from exc
    for *_, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if reason := _blocked(ip, allow_private):
            raise WebhookUrlError(
                f"{host} resolves to {ip}, {reason}. Webhooks cannot point there."
            )
