# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Latest published year per Daymet product from NASA CMR (DESIGN.md §3.3).

The single-pixel API is never trusted for this: asked for an unpublished year it returns
the whole record with HTTP 200. CMR answers without credentials; results are cached 24 h
and a configured fallback is used (and reported) when CMR fails.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import structlog

from daymet_mcp.daymet.cache import TTLCache
from daymet_mcp.daymet.catalog import COLLECTIONS, Collection
from daymet_mcp.daymet.client import DaymetHttpClient
from daymet_mcp.errors import UpstreamError

if TYPE_CHECKING:
    from daymet_mcp.context import UpstreamStats

ENDPOINT = "GET cmr.earthdata.nasa.gov/search/granules.umm_json"
log = structlog.get_logger("daymet_mcp.cmr")


@dataclass(frozen=True)
class LatestYear:
    product: str
    year: int | None
    source: Literal["cmr", "fallback"]


def parse_latest_year(body: Any) -> int:
    """Year of the newest granule's start date in a ``granules.umm_json`` page."""
    try:
        item = body["items"][0]["umm"]
        rng = item["TemporalExtent"]["RangeDateTime"]
        begin = str(rng["BeginningDateTime"])
        return int(begin[:4])
    except (KeyError, IndexError, TypeError, ValueError):
        raise UpstreamError(
            "drift",
            "CMR granule response lacks TemporalExtent.RangeDateTime",
            host="cmr.earthdata.nasa.gov",
            details={"drift": {"endpoint": ENDPOINT}},
        ) from None


class CmrService:
    def __init__(
        self, client: DaymetHttpClient, cache: TTLCache, cmr_url: str, fallback_daily: int
    ) -> None:
        self.client = client
        self.cache = cache
        self.url = cmr_url.rstrip("/") + "/granules.umm_json"
        self.fallback_daily = fallback_daily

    async def _latest(self, coll: Collection, stats: UpstreamStats) -> int:
        async def fetch() -> int:
            response = await self.client.get(
                self.url,
                params={
                    "collection_concept_id": coll.concept_id,
                    "sort_key": "-start_date",
                    "page_size": "1",
                },
                group="cmr",
                stats=stats,
                endpoint=ENDPOINT,
            )
            return parse_latest_year(response.json())

        value, cached = await self.cache.get_or_fetch(f"cmr:latest:{coll.concept_id}", fetch)
        if cached:
            stats.cache_hits += 1
        return int(value)

    async def latest(self, product: str, stats: UpstreamStats) -> LatestYear:
        coll = next(c for c in COLLECTIONS if c.product == product)
        try:
            return LatestYear(product, await self._latest(coll, stats), "cmr")
        except UpstreamError as exc:
            log.warning("cmr.fallback", product=product, reason=exc.kind)
            year = self.fallback_daily if product == "daily" else None
            return LatestYear(product, year, "fallback")

    async def latest_daily(self, stats: UpstreamStats) -> LatestYear:
        return await self.latest("daily", stats)
