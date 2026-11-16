# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Local politeness limits per host group (DESIGN.md §6, D19).

Upstream publishes no rate limits, so daymet-mcp applies its own: a token bucket (rate,
burst 1) plus a concurrency semaphore per group.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal

import anyio

HostGroup = Literal["single_pixel", "cmr", "earthdata"]


@dataclass(frozen=True)
class Policy:
    rate_per_s: float
    concurrency: int


POLICIES: dict[HostGroup, Policy] = {
    "single_pixel": Policy(2.0, 4),
    "cmr": Policy(1.0, 2),
    "earthdata": Policy(2.0, 2),
}


class _Bucket:
    def __init__(self, policy: Policy, clock: Callable[[], float]) -> None:
        self.interval = 1.0 / policy.rate_per_s
        self.next_at = 0.0
        self.clock = clock
        self.lock = anyio.Lock()
        self.sem = anyio.Semaphore(policy.concurrency)


class RateLimiter:
    def __init__(
        self,
        *,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        clock: Callable[[], float] | None = None,
        policies: dict[HostGroup, Policy] | None = None,
    ) -> None:
        self._sleep = sleep or anyio.sleep
        self._clock = clock or time.monotonic
        self._buckets = {g: _Bucket(p, self._clock) for g, p in (policies or POLICIES).items()}

    @asynccontextmanager
    async def slot(self, group: HostGroup) -> AsyncIterator[None]:
        bucket = self._buckets[group]
        async with bucket.sem:
            async with bucket.lock:
                now = self._clock()
                wait = bucket.next_at - now
                bucket.next_at = max(now, bucket.next_at) + bucket.interval
            if wait > 0:
                await self._sleep(wait)
            yield
