"""Acceptance criterion 12, private by default: GPUWatch contacts nothing it was not told to.

The API's only outbound connections are the configured database, Redis, AWS endpoints, SMTP
server and the webhook URLs an admin adds; the agent's are the GPUWatch URL and the inference
or DCGM endpoints it is configured with. No telemetry, no update checks, no hardcoded hosts.
"""

from __future__ import annotations

import re
from pathlib import Path

API_SRC = Path(__file__).resolve().parents[2] / "src" / "gpuwatch"
AGENT_SRC = Path(__file__).resolve().parents[3] / "agent" / "src" / "gpuwatch_agent"
URL = re.compile(r"https?://([A-Za-z0-9.\-]+)")
ALLOWED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "example.com",
    "hooks.example.com",
    "gpuwatch.example.com",
    "vllm",
    "tgi",
}
# Strings in docstrings and messages that are examples, not targets.
ALLOWED_SUFFIXES = (".local", ".test", ".example")


def _hosts(root: Path) -> set[str]:
    found = set()
    for path in root.rglob("*.py"):
        if "migrations" in path.parts:
            continue
        for host in URL.findall(path.read_text()):
            found.add(host)
    return found


def test_the_api_has_no_hardcoded_outbound_hosts() -> None:
    unexpected = {
        h for h in _hosts(API_SRC) if h not in ALLOWED_HOSTS and not h.endswith(ALLOWED_SUFFIXES)
    }
    assert unexpected == set()


def test_the_agent_has_no_hardcoded_outbound_hosts() -> None:
    unexpected = {
        h for h in _hosts(AGENT_SRC) if h not in ALLOWED_HOSTS and not h.endswith(ALLOWED_SUFFIXES)
    }
    assert unexpected == set()


def test_no_telemetry_or_tracing_is_on_by_default() -> None:
    from gpuwatch.core.config import Settings

    s = Settings()
    assert s.otel_enabled is False
    assert s.mail_mode == "log"
    assert s.aws_endpoint_url is None
