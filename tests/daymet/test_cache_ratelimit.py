# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""TTL/LRU cache (single flight, stale-if-error, disk layer) and the local rate limiter."""

from __future__ import annotations

from pathlib import Path

import anyio
import pytest

from daymet_mcp.daymet.cache import TTLCache
from daymet_mcp.daymet.ratelimit import Policy, RateLimiter
from tests.conftest import FakeSleep


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_ttl_and_lru() -> None:
    clock = Clock()
    cache = TTLCache(max_entries=2, ttl_s=10, stale_if_error_s=5, clock=clock)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.peek("a") == 1  # a becomes most recent
    cache.put("c", 3)  # evicts b
    assert cache.peek("b") is None and len(cache) == 2
    clock.now += 11
    assert cache.peek("a") is None
    assert cache.stale("a") == 1
    clock.now += 10
    assert cache.stale("a") is None


async def test_single_flight() -> None:
    cache = TTLCache(max_entries=10, ttl_s=60, stale_if_error_s=0)
    calls = {"n": 0}

    async def fetch() -> int:
        calls["n"] += 1
        await anyio.sleep(0.01)
        return 42

    results: list[tuple[int, bool]] = []

    async def one() -> None:
        results.append(await cache.get_or_fetch("k", fetch))

    async with anyio.create_task_group() as tg:
        for _ in range(5):
            tg.start_soon(one)
    assert calls["n"] == 1
    assert sorted(results) == [(42, False), (42, True), (42, True), (42, True), (42, True)]


async def test_stale_if_error() -> None:
    clock = Clock()
    cache = TTLCache(max_entries=10, ttl_s=10, stale_if_error_s=100, clock=clock)
    cache.put("k", "old")
    clock.now += 20

    async def failing() -> str:
        raise RuntimeError("upstream down")

    assert await cache.get_or_fetch("k", failing) == ("old", True)
    with pytest.raises(RuntimeError):
        await cache.get_or_fetch("other", failing)


def test_disk_layer(tmp_path: Path) -> None:
    clock = Clock()
    a = TTLCache(max_entries=10, ttl_s=60, stale_if_error_s=0, disk_dir=str(tmp_path), clock=clock)
    a.put("pixel:na:c1:r2:2020", {"v": [1.5, None]})
    b = TTLCache(max_entries=10, ttl_s=60, stale_if_error_s=0, disk_dir=str(tmp_path), clock=clock)
    assert b.peek("pixel:na:c1:r2:2020") == {"v": [1.5, None]}
    # a corrupt file is ignored, never fatal
    for path in tmp_path.rglob("*.json.gz"):
        path.write_bytes(b"not gzip")
    c = TTLCache(max_entries=10, ttl_s=60, stale_if_error_s=0, disk_dir=str(tmp_path), clock=clock)
    assert c.peek("pixel:na:c1:r2:2020") is None


def test_disk_write_failure_is_silent(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    cache = TTLCache(max_entries=10, ttl_s=60, stale_if_error_s=0, disk_dir=str(blocker))
    cache.put("k", 1)  # cannot create a directory under a file: no exception
    assert cache.peek("k") == 1


async def test_rate_limiter_spacing() -> None:
    clock = Clock()
    sleep = FakeSleep()
    limiter = RateLimiter(sleep=sleep, clock=clock, policies={"single_pixel": Policy(2.0, 4)})
    for _ in range(3):
        async with limiter.slot("single_pixel"):
            pass
    # clock frozen: second waits one interval (0.5 s), third two
    assert sleep.calls == [0.5, 1.0]
