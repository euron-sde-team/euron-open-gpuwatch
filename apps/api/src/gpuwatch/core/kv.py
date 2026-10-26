"""A small key-value interface with two backends: Redis, or process memory.

GPUWatch can run with no Redis at all, so everything that would use Redis (the latest
sample per GPU for the live view, rate limits, the config version stamp) goes through
:class:`KV`. With ``REDIS_URL`` set, state is shared by every replica; without it, each
process keeps its own, which is exact for a single replica and documented as such.

A Redis outage never stops ingest: callers treat live-store and limiter errors as a miss
or a pass and count them in ``gpuwatch_dependency_errors_total``. Postgres stays the
source of truth.
"""

from __future__ import annotations

import math
import time
from collections import OrderedDict
from typing import Protocol

from redis.asyncio import Redis

from gpuwatch.limits.limiter import LimitDecision, Limiter


class KV(Protocol):
    backend: str

    async def get(self, key: str) -> bytes | None: ...
    async def mget(self, keys: list[str]) -> list[bytes | None]: ...
    async def set(self, key: str, value: bytes, ttl_s: int) -> None: ...
    async def incr(self, key: str) -> int: ...
    async def hit(self, name: str, limit: int, amount: int = 1) -> LimitDecision: ...
    async def ping(self) -> None: ...
    async def close(self) -> None: ...


class RedisKV:
    backend = "redis"

    def __init__(self, url: str) -> None:
        self.redis = Redis.from_url(
            url,
            decode_responses=False,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
            health_check_interval=15,
            retry_on_timeout=False,
        )
        self._limiter = Limiter(self.redis)

    async def get(self, key: str) -> bytes | None:
        value = await self.redis.get(key)
        if value is None:
            return None
        return value if isinstance(value, bytes) else str(value).encode()

    async def mget(self, keys: list[str]) -> list[bytes | None]:
        if not keys:
            return []
        values = await self.redis.mget(keys)
        return [v if isinstance(v, bytes) or v is None else str(v).encode() for v in values]

    async def set(self, key: str, value: bytes, ttl_s: int) -> None:
        await self.redis.set(key, value, ex=ttl_s)

    async def incr(self, key: str) -> int:
        return int(await self.redis.incr(key))

    async def hit(self, name: str, limit: int, amount: int = 1) -> LimitDecision:
        return await self._limiter.hit(name, limit, amount)

    async def ping(self) -> None:
        await self.redis.ping()

    async def close(self) -> None:
        await self.redis.aclose()


_FOREVER_S = 10 * 365 * 24 * 3600


class MemoryKV:
    """LRU with expiry bounded by entries and bytes, plus fixed-window rate counters.

    One process only. Bounded by entries and bytes so a large fleet cannot grow it
    without limit.
    """

    backend = "memory"

    def __init__(self, max_entries: int = 20_000, max_bytes: int = 64_000_000) -> None:
        self._data: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
        self._windows: dict[str, tuple[int, int]] = {}
        self._max = max_entries
        self._max_bytes = max_bytes
        self._bytes = 0

    async def get(self, key: str) -> bytes | None:
        hit = self._data.get(key)
        if hit is None:
            return None
        if hit[0] < time.monotonic():
            self._drop(key)
            return None
        self._data.move_to_end(key)
        return hit[1]

    async def mget(self, keys: list[str]) -> list[bytes | None]:
        return [await self.get(k) for k in keys]

    async def set(self, key: str, value: bytes, ttl_s: int) -> None:
        if len(value) > self._max_bytes:
            return
        self._drop(key)
        self._data[key] = (time.monotonic() + ttl_s, value)
        self._bytes += len(key) + len(value)
        while len(self._data) > self._max or self._bytes > self._max_bytes:
            oldest = next(iter(self._data))
            self._drop(oldest)

    def _drop(self, key: str) -> None:
        old = self._data.pop(key, None)
        if old is not None:
            self._bytes -= len(key) + len(old[1])

    async def incr(self, key: str) -> int:
        current = await self.get(key)
        value = int(current or b"0") + 1
        await self.set(key, str(value).encode(), _FOREVER_S)
        return value

    async def hit(self, name: str, limit: int, amount: int = 1) -> LimitDecision:
        now = time.time()
        window = int(now // Limiter.WINDOW_S)
        if len(self._windows) > 10_000:
            # Only the current window matters; forget every key from earlier ones.
            self._windows = {k: v for k, v in self._windows.items() if v[0] == window}
        current_window, count = self._windows.get(name, (window, 0))
        if current_window != window:
            count = 0
        if count + amount > limit:
            retry = math.ceil(Limiter.WINDOW_S - (now % Limiter.WINDOW_S))
            return LimitDecision(False, max(1, retry), count)
        self._windows[name] = (window, count + amount)
        return LimitDecision(True, 0, count + amount)

    async def ping(self) -> None:
        return None

    async def close(self) -> None:
        self._data.clear()
        self._bytes = 0


def create_kv(redis_url: str, memory_max_bytes: int = 64_000_000) -> KV:
    return RedisKV(redis_url) if redis_url else MemoryKV(max_bytes=memory_max_bytes)
