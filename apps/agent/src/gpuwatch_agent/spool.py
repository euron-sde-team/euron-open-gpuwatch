"""Disk spool for batches the server could not take (network down, server restarting).

Each batch is one JSON file named by time and batch id, replayed oldest first. The batch id
makes replays idempotent on the server, so a batch sent twice (sent, then the reply was
lost) is stored once. The spool is bounded: past ``max_bytes`` the oldest files go first.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class Spool:
    def __init__(self, directory: Path, max_bytes: int) -> None:
        self.dir = directory
        self.max_bytes = max_bytes
        self.dir.mkdir(parents=True, exist_ok=True)

    def put(self, batch: dict[str, Any]) -> Path:
        name = f"{time.time_ns():020d}-{batch['batch_id']}.json"
        tmp = self.dir / f".{name}.tmp"
        tmp.write_text(json.dumps(batch, separators=(",", ":")))
        path = self.dir / name
        os.replace(tmp, path)  # atomic: a crash never leaves half a batch
        self._trim()
        return path

    def pending(self) -> list[Path]:
        return sorted(p for p in self.dir.glob("*.json") if not p.name.startswith("."))

    def load(self, path: Path) -> dict[str, Any] | None:
        try:
            data: dict[str, Any] = json.loads(path.read_text())
            return data
        except (OSError, ValueError):
            self.drop(path)  # unreadable: it would block the queue forever
            return None

    def drop(self, path: Path) -> None:
        path.unlink(missing_ok=True)

    def size(self) -> int:
        return sum(p.stat().st_size for p in self.pending())

    def _trim(self) -> None:
        files = self.pending()
        total = sum(p.stat().st_size for p in files)
        for p in files:
            if total <= self.max_bytes:
                break
            total -= p.stat().st_size
            self.drop(p)
