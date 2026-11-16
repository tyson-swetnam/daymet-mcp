# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""The ORNL DAAC single-pixel API: request builder, parser and silent-failure guards.

Observed upstream behaviour (RESEARCH.md, Research B §1) that the guards exist for (D6):
unknown variables are ignored (HTTP 200, all variables); an unpublished year or a pre-1980
start returns the **entire record** with HTTP 200; points off the land grid give HTTP 400
"Daymet Tile was not found". The server therefore validates inputs itself and checks that
the years and row counts returned are exactly the ones requested.

Every request asks for all seven variables for whole years (D11) and is cached per
(region, cell, year), so any variable mix for a cell-year is served from one GET.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from daymet_mcp.daymet import lcc
from daymet_mcp.daymet.cache import TTLCache
from daymet_mcp.daymet.calendar import DAYS_PER_YEAR
from daymet_mcp.daymet.catalog import VARIABLE_NAMES, VARIABLES, Region
from daymet_mcp.daymet.client import DaymetHttpClient
from daymet_mcp.errors import UpstreamError

if TYPE_CHECKING:
    from daymet_mcp.context import UpstreamStats

ENDPOINT = "GET daymet.ornl.gov/single-pixel/api/data"
ALL_VARS = ",".join(VARIABLE_NAMES)
REQUIRED_KEYS = ("loc", "Tile", "Elevation", "LCC", "citation", "data")


@dataclass(frozen=True)
class PixelLocation:
    """Where a single-pixel request is sent and how it is cached."""

    region: Region
    query_lat: float
    query_lon: float
    cell: lcc.Cell | None

    @property
    def cache_prefix(self) -> str:
        if self.cell is not None:
            return f"pixel:{self.region}:c{self.cell.col}:r{self.cell.row}"
        return f"pixel:{self.region}:{self.query_lat:.5f}:{self.query_lon:.5f}"


def location_for(lat: float, lon: float, region: Region) -> PixelLocation:
    """NA points are sent as their cell centre (deterministic per cell); hi/pr as given (D9)."""
    if region == "na":
        cell = lcc.cell_for_latlon(lat, lon)
        clat, clon = cell.centre_latlon()
        return PixelLocation(region, round(clat, 6), round(clon, 6), cell)
    return PixelLocation(region, round(lat, 6), round(lon, 6), None)


@dataclass
class PixelYear:
    year: int
    header: dict[str, Any]
    values: dict[str, list[float | None]]

    def to_json(self) -> dict[str, Any]:
        return {"year": self.year, "header": self.header, "values": self.values}

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> PixelYear:
        return cls(
            int(raw["year"]), dict(raw["header"]), {k: list(v) for k, v in raw["values"].items()}
        )


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def parse_elevation(raw: Any) -> float | None:
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        head = raw.strip().split(" ")[0]
        return _num(head)
    return None


def parse_response(
    body: Any, *, expected_years: Sequence[int] | None = None, expected_rows: int | None = None
) -> tuple[dict[str, Any], dict[int, dict[str, list[float | None]]], list[int]]:
    """Validate a single-pixel JSON body.

    Returns ``(header, values_by_year, ydays_in_order)``. Raises :class:`UpstreamError`
    (``drift`` or ``parse``) when keys, units, years or row counts are not as requested.
    """
    if not isinstance(body, dict):
        raise UpstreamError(
            "parse", "single-pixel body is not a JSON object", host="daymet.ornl.gov"
        )
    missing = [k for k in REQUIRED_KEYS if k not in body]
    data = body.get("data")
    if missing or not isinstance(data, dict):
        raise UpstreamError(
            "drift",
            "single-pixel response lacks expected keys",
            host="daymet.ornl.gov",
            details={"drift": {"missingKeys": missing or ["data"]}},
        )
    columns = {VARIABLES[v].upstream_column: v for v in VARIABLE_NAMES}
    absent = [c for c in (*columns, "year", "yday") if c not in data]
    if absent:
        raise UpstreamError(
            "drift",
            "single-pixel columns or units changed",
            host="daymet.ornl.gov",
            details={"drift": {"missingColumns": absent, "returnedColumns": sorted(data)}},
        )
    years = [int(y) for y in data["year"]]
    ydays = [int(d) for d in data["yday"]]
    n = len(years)
    if len(ydays) != n or any(len(data[c]) != n for c in columns):
        raise UpstreamError(
            "drift", "single-pixel columns have unequal lengths", host="daymet.ornl.gov"
        )
    returned = sorted(set(years))
    if expected_years is not None:
        exp = sorted(set(expected_years))
        rows = {y: years.count(y) for y in returned}
        if returned != exp or any(rows[y] != DAYS_PER_YEAR for y in returned):
            raise UpstreamError(
                "drift",
                "the years or row counts returned differ from the request",
                host="daymet.ornl.gov",
                details={
                    "drift": {
                        "expectedYears": exp,
                        "returnedYears": returned[:5] + (["..."] if len(returned) > 5 else []),
                        "expectedRows": DAYS_PER_YEAR * len(exp),
                        "returnedRows": n,
                    }
                },
            )
    if expected_rows is not None and n != expected_rows:
        raise UpstreamError(
            "drift",
            "the row count returned differs from the request",
            host="daymet.ornl.gov",
            details={"drift": {"expectedRows": expected_rows, "returnedRows": n}},
        )
    citation = str(body.get("citation", ""))
    if "ORNLDAAC/2129" not in citation:
        raise UpstreamError(
            "drift",
            "the embedded citation no longer names DOI 10.3334/ORNLDAAC/2129",
            host="daymet.ornl.gov",
            details={"drift": {"citation": citation[:200]}},
        )
    lcc_xy = body.get("LCC") or [None, None]
    loc = body.get("loc") or [None, None]
    header = {
        "tile": str(body.get("Tile")),
        "elevationM": parse_elevation(body.get("Elevation")),
        "elevationRaw": str(body.get("Elevation")),
        "lccX": _num(lcc_xy[0]),
        "lccY": _num(lcc_xy[1]),
        "lat": _num(loc[0]),
        "lon": _num(loc[1]),
        "citation": citation,
    }
    by_year: dict[int, dict[str, list[float | None]]] = {}
    for i, y in enumerate(years):
        slot = by_year.setdefault(y, {v: [] for v in VARIABLE_NAMES})
        for col, var in columns.items():
            slot[var].append(_num(data[col][i]))
    return header, by_year, ydays


class SinglePixelService:
    def __init__(self, client: DaymetHttpClient, cache: TTLCache, url: str) -> None:
        self.client = client
        self.cache = cache
        self.url = url

    async def get_years(
        self, where: PixelLocation, years: Sequence[int], stats: UpstreamStats
    ) -> dict[int, PixelYear]:
        """All seven variables for each requested whole year (cache first, one GET for the rest)."""
        out: dict[int, PixelYear] = {}
        missing: list[int] = []
        for y in sorted(set(years)):
            hit = self.cache.peek(f"{where.cache_prefix}:{y}")
            if hit is not None:
                out[y] = PixelYear.from_json(hit)
                stats.cache_hits += 1
            else:
                missing.append(y)
        if not missing:
            return out

        async def fetch() -> dict[str, Any]:
            params = {
                "lat": f"{where.query_lat:.6f}",
                "lon": f"{where.query_lon:.6f}",
                "vars": ALL_VARS,
                "years": ",".join(str(y) for y in missing),
                "format": "json",
            }
            response = await self.client.get(
                self.url, params=params, group="single_pixel", stats=stats, endpoint=ENDPOINT
            )
            try:
                body = response.json()
            except ValueError:
                raise UpstreamError(
                    "parse", "single-pixel body is not JSON", host="daymet.ornl.gov"
                ) from None
            header, by_year, _ = parse_response(body, expected_years=missing)
            return {str(y): PixelYear(y, header, by_year[y]).to_json() for y in missing}

        key = f"{where.cache_prefix}:batch:{','.join(map(str, missing))}"
        fetched, from_cache = await self.cache.get_or_fetch(key, fetch)
        if from_cache:
            stats.cache_hits += 1
        for y in missing:
            item = fetched[str(y)]
            self.cache.put(f"{where.cache_prefix}:{y}", item)
            out[y] = PixelYear.from_json(item)
        return out

    async def get_window(
        self, lat: float, lon: float, start: date, end: date, stats: UpstreamStats
    ) -> tuple[dict[str, Any], int]:
        """A small uncached date window (used by ``daymet_ping``); returns (header, rows)."""
        params = {
            "lat": f"{lat:.6f}",
            "lon": f"{lon:.6f}",
            "vars": ALL_VARS,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "format": "json",
        }
        response = await self.client.get(
            self.url, params=params, group="single_pixel", stats=stats, endpoint=ENDPOINT
        )
        expected = (end - start).days + 1
        header, _, ydays = parse_response(response.json(), expected_rows=expected)
        return header, len(ydays)
