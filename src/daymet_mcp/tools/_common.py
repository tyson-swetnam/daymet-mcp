# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Helpers shared by the data tools."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date

from daymet_mcp.context import ToolContext
from daymet_mcp.daymet import lcc
from daymet_mcp.daymet.calendar import year_dates
from daymet_mcp.daymet.catalog import (
    DEFAULT_AGGREGATION,
    REGIONS,
    Aggregation,
    AggSpec,
    Period,
    Region,
    Variable,
    aggregation_spec,
    region_for,
)
from daymet_mcp.daymet.single_pixel import PixelYear
from daymet_mcp.errors import ToolError
from daymet_mcp.models.common import AggregationOverrides, Page
from daymet_mcp.models.point import CellRef

CITE_STEP = "daymet_get_citation(products=['daily'], access=['single_pixel'])"
DAILY_DECIMALS = 2


async def latest_daily_year(ctx: ToolContext) -> tuple[int, str]:
    latest = await ctx.services.cmr.latest_daily(ctx.stats)
    year = latest.year if latest.year is not None else ctx.config.daymet.latest_year_fallback.daily
    return year, latest.source


async def check_years(ctx: ToolContext, years: Sequence[int]) -> tuple[int, str]:
    """Refuse years outside 1980..latest (DESIGN.md §4.0); returns (latest, source)."""
    latest, source = await latest_daily_year(ctx)
    first = ctx.config.daymet.first_year
    bad = sorted({y for y in years if y < first or y > latest})
    if bad:
        raise ToolError(
            "invalid_argument",
            f"Year(s) {bad} are outside the published Daymet record {first}-{latest}.",
            details={
                "reason": "year_out_of_range",
                "firstYear": first,
                "latestYear": latest,
                "latestYearSource": source,
            },
            hint=f"Use years {first}..{latest}.",
        )
    return latest, source


def require_region(lat: float, lon: float) -> Region:
    region = region_for(lat, lon)
    if region is None:
        raise ToolError(
            "invalid_argument",
            "The point is outside every Daymet region (North America, Hawaii, Puerto Rico).",
            details={"reason": "out_of_coverage", "lat": lat, "lon": lon},
            hint="See daymet_list_variables for the region bounding boxes.",
        )
    return region


def cell_ref(cell: lcc.Cell | None) -> CellRef | None:
    if cell is None:
        return None
    return CellRef(col=cell.col, row=cell.row, x_centre_m=cell.x_centre, y_centre_m=cell.y_centre)


def specs_for(
    variables: Sequence[Variable], period: Period, overrides: AggregationOverrides | None
) -> list[AggSpec]:
    chosen: dict[str, Aggregation] = {}
    if overrides is not None:
        if overrides.swe:
            chosen["swe"] = overrides.swe
        if overrides.srad:
            chosen["srad"] = "total" if overrides.srad == "total" else "mean"
    return [aggregation_spec(v, period, chosen.get(v, DEFAULT_AGGREGATION[v])) for v in variables]


def stitch_years(
    data: dict[int, PixelYear], years: Sequence[int]
) -> tuple[list[date], dict[str, list[float | None]]]:
    """Concatenate cached cell-years into aligned dates and per-variable series."""
    dates: list[date] = []
    series: dict[str, list[float | None]] = {}
    for y in sorted(set(years)):
        dates.extend(year_dates(y))
        for var, values in data[y].values.items():
            series.setdefault(var, []).extend(values)
    return dates, series


def round_daily(values: Sequence[float | None]) -> list[float | None]:
    return [None if v is None or not math.isfinite(v) else round(v, DAILY_DECIMALS) for v in values]


def page_window(total: int, offset: int, limit: int) -> tuple[slice, Page]:
    end = min(total, offset + limit)
    returned = max(0, end - offset)
    truncated = end < total
    return slice(offset, end), Page(
        total=total,
        returned=returned,
        offset=offset,
        limit=limit,
        truncated=truncated,
        next_offset=end if truncated else None,
        truncated_reason="limit" if truncated else None,
    )


def region_name(region: Region) -> str:
    return REGIONS[region].name
