# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""The one upstream HTTP client (DESIGN.md §7).

* one ``httpx.AsyncClient`` per process, ``follow_redirects=False``; redirects are
  followed manually, one hop at a time, only to allow-listed hosts;
* only GET (and HEAD); timeouts connect 10 s / read 60 s; ``max_connections=8``;
* ``Authorization: Bearer`` is attached only to Earthdata Login hosts and never carried to
  another host on a redirect (D15);
* retries: 429 honours ``Retry-After``; 5xx and transport errors back off
  ``0.5*2^n`` + jitter; at most 3 attempts;
* a generic User-Agent (D20).
"""

from __future__ import annotations

import random
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlsplit

import anyio
import httpx
import structlog

from daymet_mcp import USER_AGENT
from daymet_mcp.daymet.ratelimit import HostGroup, RateLimiter
from daymet_mcp.errors import UpstreamError

if TYPE_CHECKING:
    from daymet_mcp.context import UpstreamStats

ALLOWED_HOSTS = frozenset(
    {
        "daymet.ornl.gov",
        "cmr.earthdata.nasa.gov",
        "opendap.earthdata.nasa.gov",
        "urs.earthdata.nasa.gov",
        "data.ornldaac.earthdata.nasa.gov",
    }
)
EDL_HOSTS = frozenset(
    {"opendap.earthdata.nasa.gov", "urs.earthdata.nasa.gov", "data.ornldaac.earthdata.nasa.gov"}
)
MAX_ATTEMPTS = 3
MAX_REDIRECTS = 5

log = structlog.get_logger("daymet_mcp.http")


def _log_query(params: Mapping[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (params or {}).items():
        if key in ("lat", "lon"):
            try:
                out[key] = round(float(value), 3)
            except (TypeError, ValueError):
                out[key] = "?"
        elif key in ("years", "start", "end", "collection_concept_id"):
            out[key] = value
    return out


class DaymetHttpClient:
    def __init__(
        self,
        *,
        limiter: RateLimiter,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        token: str | None = None,
        allowed_hosts: frozenset[str] = ALLOWED_HOSTS,
    ) -> None:
        self._limiter = limiter
        self._sleep = sleep or anyio.sleep
        self._token = token
        self._allowed = allowed_hosts
        self._client = httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            timeout=httpx.Timeout(60.0, connect=10.0),
            limits=httpx.Limits(max_connections=8),
            headers={"User-Agent": USER_AGENT},
        )

    @property
    def has_token(self) -> bool:
        return bool(self._token)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _check_host(self, url: str) -> str:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme != "https" or host not in self._allowed:
            raise UpstreamError(
                "host",
                f"refusing to contact a host outside the allow-list ({host or 'none'})",
                host=host,
            )
        return host

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        group: HostGroup,
        stats: UpstreamStats | None = None,
        endpoint: str | None = None,
        auth: bool = False,
    ) -> httpx.Response:
        """GET with redirects, retries and limits; raises :class:`UpstreamError` on failure."""
        if stats is not None and endpoint:
            stats.record_endpoint(endpoint)
        current_url = url
        current_params: Mapping[str, Any] | None = params
        for _hop in range(MAX_REDIRECTS + 1):
            host = self._check_host(current_url)
            headers: dict[str, str] = {}
            if auth and self._token and host in EDL_HOSTS:
                headers["Authorization"] = f"Bearer {self._token}"
            response = await self._attempts(
                current_url, current_params, headers, group, host, stats
            )
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise UpstreamError(
                        "status",
                        "redirect without Location",
                        status=response.status_code,
                        host=host,
                    )
                current_url = urljoin(str(response.request.url), location)
                current_params = None
                continue
            if response.status_code >= 400:
                text = response.text[:300] if response.content else ""
                raise UpstreamError(
                    "status",
                    text or f"HTTP {response.status_code}",
                    status=response.status_code,
                    host=host,
                    retry_after_s=_retry_after(response),
                )
            return response
        raise UpstreamError("status", "too many redirects", host=urlsplit(url).hostname)

    async def _attempts(
        self,
        url: str,
        params: Mapping[str, Any] | None,
        headers: dict[str, str],
        group: HostGroup,
        host: str,
        stats: UpstreamStats | None,
    ) -> httpx.Response:
        last_exc: Exception | None = None
        kind = "transport"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            started = time.monotonic()
            try:
                async with self._limiter.slot(group):
                    if stats is not None:
                        stats.requests += 1
                    response = await self._client.get(url, params=params, headers=headers)
            except httpx.TimeoutException as exc:
                last_exc = exc
                kind = "timeout"
            except httpx.TransportError as exc:
                last_exc = exc
                kind = "transport"
            else:
                log.info(
                    "daymet.http",
                    host=host,
                    path=urlsplit(url).path,
                    query=_log_query(params),
                    status=response.status_code,
                    ms=round((time.monotonic() - started) * 1000, 1),
                    attempt=attempt,
                )
                if response.status_code == 429 and attempt < MAX_ATTEMPTS:
                    await self._sleep(_retry_after(response) or 0.5 * 2 ** (attempt - 1))
                    continue
                if response.status_code >= 500 and attempt < MAX_ATTEMPTS:
                    await self._sleep(_backoff(attempt))
                    continue
                return response
            if attempt < MAX_ATTEMPTS:
                await self._sleep(_backoff(attempt))
        raise UpstreamError(
            "timeout" if kind == "timeout" else "transport",
            type(last_exc).__name__ if last_exc else "unknown",
            host=host,
        )


def _backoff(attempt: int) -> float:
    return float(0.5 * 2 ** (attempt - 1) + random.uniform(0, 0.25))  # noqa: S311 - jitter only


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None
