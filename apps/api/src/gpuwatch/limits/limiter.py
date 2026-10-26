"""Per-key request rate limits (RPM) in Redis.

Rates use the sliding-window counter algorithm: the previous fixed window's count is
weighted by how much of it still overlaps the sliding window. It needs two integers per
limit, is exact at window boundaries to within a few percent, and runs as one atomic
script so concurrent requests cannot overshoot.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from redis.asyncio import Redis

_SLIDING = """
local amount = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local window = tonumber(ARGV[3])
local frac = tonumber(ARGV[4])
local cur = tonumber(redis.call('GET', KEYS[1]) or '0')
local prev = tonumber(redis.call('GET', KEYS[2]) or '0')
local weighted = prev * (1 - frac) + cur
if weighted + amount > limit then
  return {0, math.floor(weighted)}
end
redis.call('INCRBY', KEYS[1], amount)
redis.call('EXPIRE', KEYS[1], window * 2)
return {1, math.floor(weighted + amount)}
"""


@dataclass(frozen=True, slots=True)
class LimitDecision:
    allowed: bool
    retry_after_s: int = 0
    observed: int = 0


class Limiter:
    WINDOW_S = 60

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._sliding = redis.register_script(_SLIDING)

    def _keys(self, name: str, now: float) -> tuple[list[str], float, int]:
        window = int(now // self.WINDOW_S)
        frac = (now % self.WINDOW_S) / self.WINDOW_S
        retry = math.ceil(self.WINDOW_S - (now % self.WINDOW_S))
        return [f"gw:rl:{name}:{window}", f"gw:rl:{name}:{window - 1}"], frac, retry

    async def hit(self, name: str, limit: int, amount: int = 1) -> LimitDecision:
        now = time.time()
        keys, frac, retry = self._keys(name, now)
        allowed, observed = await self._sliding(
            keys=keys, args=[amount, limit, self.WINDOW_S, f"{frac:.6f}"]
        )
        return LimitDecision(bool(int(allowed)), 0 if allowed else max(1, retry), int(observed))
