"""Process details from /proc: name, user and container id.

In a container, run the agent with ``--pid=host`` so GPU process ids resolve; without it the
names are unknown and processes show as ``pid <n>``.
"""

from __future__ import annotations

import pwd
import re
from dataclasses import dataclass
from pathlib import Path

# A 64-hex container id in a cgroup path (Docker, containerd, CRI-O, Kubernetes).
_CONTAINER = re.compile(r"([0-9a-f]{64})")


@dataclass(frozen=True)
class ProcInfo:
    name: str
    username: str | None
    container_id: str | None


def _read(path: Path) -> str | None:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return None


def container_id(cgroup: str | None) -> str | None:
    if not cgroup:
        return None
    m = _CONTAINER.search(cgroup)
    return m.group(1)[:12] if m else None


def lookup(pid: int, proc: Path = Path("/proc")) -> ProcInfo:
    base = proc / str(pid)
    name = (_read(base / "comm") or "").strip() or f"pid {pid}"
    username = None
    status = _read(base / "status") or ""
    m = re.search(r"^Uid:\s+(\d+)", status, re.MULTILINE)
    if m:
        try:
            username = pwd.getpwuid(int(m.group(1))).pw_name
        except KeyError:
            username = m.group(1)
    return ProcInfo(name[:255], username, container_id(_read(base / "cgroup")))
