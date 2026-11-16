# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Upstream client: host allow-list, manual redirects, Authorization scoping, retries."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from daymet_mcp import USER_AGENT
from daymet_mcp.context import UpstreamStats
from daymet_mcp.daymet.client import DaymetHttpClient
from daymet_mcp.daymet.ratelimit import RateLimiter
from daymet_mcp.errors import UpstreamError
from tests.conftest import FakeSleep
from tests.fixture_router import TEST_TOKEN

Handler = Callable[[httpx.Request], httpx.Response]


def make(handler: Handler, sleep: FakeSleep, token: str | None = None) -> DaymetHttpClient:
    return DaymetHttpClient(
        limiter=RateLimiter(sleep=sleep),
        transport=httpx.MockTransport(handler),
        sleep=sleep,
        token=token,
    )


async def test_user_agent_is_generic(fake_sleep: FakeSleep) -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={})

    client = make(handler, fake_sleep)
    await client.get("https://daymet.ornl.gov/x", group="single_pixel")
    await client.aclose()
    assert seen[0].headers["user-agent"] == USER_AGENT
    assert USER_AGENT.startswith("daymet-mcp/") and "idss-mesa" in USER_AGENT


@pytest.mark.parametrize(
    "url", ["https://example.com/x", "http://daymet.ornl.gov/x", "ftp://daymet.ornl.gov/x"]
)
async def test_host_allow_list(url: str, fake_sleep: FakeSleep) -> None:
    client = make(lambda r: httpx.Response(200), fake_sleep)
    with pytest.raises(UpstreamError) as info:
        await client.get(url, group="single_pixel")
    await client.aclose()
    assert info.value.kind == "host"


async def test_authorization_only_to_edl_hosts(fake_sleep: FakeSleep) -> None:
    seen: dict[str, str | None] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen[req.url.host] = req.headers.get("authorization")
        if req.url.host == "opendap.earthdata.nasa.gov":
            return httpx.Response(302, headers={"location": "https://daymet.ornl.gov/elsewhere"})
        return httpx.Response(200, json={})

    client = make(handler, fake_sleep, token=TEST_TOKEN)
    assert client.has_token
    await client.get("https://cmr.earthdata.nasa.gov/search", group="cmr", auth=True)
    await client.get("https://opendap.earthdata.nasa.gov/a", group="earthdata", auth=True)
    await client.aclose()
    assert seen["cmr.earthdata.nasa.gov"] is None
    assert seen["opendap.earthdata.nasa.gov"] == f"Bearer {TEST_TOKEN}"
    # redirect hop to a non-EDL host carries no Authorization
    assert seen["daymet.ornl.gov"] is None


async def test_redirect_to_disallowed_host_refused(fake_sleep: FakeSleep) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://bucket.s3.amazonaws.com/x"})

    client = make(handler, fake_sleep, token=TEST_TOKEN)
    with pytest.raises(UpstreamError) as info:
        await client.get("https://opendap.earthdata.nasa.gov/a", group="earthdata", auth=True)
    await client.aclose()
    assert info.value.kind == "host"


async def test_redirect_loop_and_missing_location(fake_sleep: FakeSleep) -> None:
    client = make(lambda r: httpx.Response(302, headers={"location": "/again"}), fake_sleep)
    with pytest.raises(UpstreamError, match="too many redirects"):
        await client.get("https://daymet.ornl.gov/a", group="single_pixel")
    await client.aclose()
    client = make(lambda r: httpx.Response(302), fake_sleep)
    with pytest.raises(UpstreamError, match="without Location"):
        await client.get("https://daymet.ornl.gov/a", group="single_pixel")
    await client.aclose()


async def test_429_honours_retry_after(fake_sleep: FakeSleep) -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "7"})
        return httpx.Response(200, json={"ok": True})

    client = make(handler, fake_sleep)
    stats = UpstreamStats()
    r = await client.get("https://daymet.ornl.gov/a", group="single_pixel", stats=stats)
    await client.aclose()
    assert r.json() == {"ok": True}
    assert 7.0 in fake_sleep.calls and stats.requests == 2


async def test_5xx_gives_up_after_three_attempts(fake_sleep: FakeSleep) -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="busy")

    client = make(handler, fake_sleep)
    with pytest.raises(UpstreamError) as info:
        await client.get("https://daymet.ornl.gov/a", group="single_pixel")
    await client.aclose()
    assert calls["n"] == 3 and info.value.status == 503


async def test_429_exhausted_reports_retry_after(fake_sleep: FakeSleep) -> None:
    client = make(lambda r: httpx.Response(429, headers={"retry-after": "3"}), fake_sleep)
    with pytest.raises(UpstreamError) as info:
        await client.get("https://daymet.ornl.gov/a", group="single_pixel")
    await client.aclose()
    assert info.value.status == 429 and info.value.retry_after_s == 3.0


@pytest.mark.parametrize(
    ("exc", "kind"),
    [(httpx.ConnectError("boom"), "transport"), (httpx.ReadTimeout("slow"), "timeout")],
)
async def test_transport_errors(exc: Exception, kind: str, fake_sleep: FakeSleep) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise exc

    client = make(handler, fake_sleep)
    with pytest.raises(UpstreamError) as info:
        await client.get("https://daymet.ornl.gov/a", group="single_pixel")
    await client.aclose()
    assert info.value.kind == kind
    assert len(fake_sleep.calls) >= 2
