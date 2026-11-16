# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""``daymet_get_point_daily`` and ``daymet_get_point_summary`` (single-pixel backend)."""

from __future__ import annotations

from collections.abc import Sequence

from daymet_mcp.context import ToolContext
from daymet_mcp.daymet.aggregate import summarise
from daymet_mcp.daymet.calendar import date_to_yday, in_calendar, is_leap
from daymet_mcp.daymet.catalog import (
    DAILY_DOI,
    DATA_VERSION,
    DERIVED_NOTE,
    PROVISIONAL_NOTE,
    ROUNDING_NOTE,
    VARIABLES,
)
from daymet_mcp.daymet.single_pixel import ENDPOINT, PixelLocation, PixelYear, location_for
from daymet_mcp.errors import ToolError
from daymet_mcp.models.common import CalendarInfo, Source, unique_variables
from daymet_mcp.models.point import (
    DailySeries,
    PeriodOut,
    PointDailyInput,
    PointDailyOutput,
    PointLocation,
    PointSummaryInput,
    PointSummaryOutput,
    SummarySeries,
    TimeAxis,
)
from daymet_mcp.registry import register_tool
from daymet_mcp.tools._common import (
    CITE_STEP,
    cell_ref,
    check_years,
    page_window,
    require_region,
    round_daily,
    specs_for,
    stitch_years,
)

LEAP_DEC_NOTE = "Leap-year December has 30 days in Daymet (Dec 31 is not in the product); totals cover Dec 1-30."


def _location(
    lat: float, lon: float, where: PixelLocation, data: dict[int, PixelYear]
) -> PointLocation:
    header = next(iter(data.values())).header if data else {}
    return PointLocation(
        requested_lat=lat,
        requested_lon=lon,
        region=where.region,
        cell=cell_ref(where.cell),
        query_lat=where.query_lat,
        query_lon=where.query_lon,
        tile=header.get("tile"),
        elevation_m=header.get("elevationM"),
    )


async def fetch_point(
    ctx: ToolContext, lat: float, lon: float, years: Sequence[int]
) -> tuple[PixelLocation, dict[int, PixelYear]]:
    region = require_region(lat, lon)
    if len(set(years)) > ctx.config.limits.max_years_per_point:
        raise ToolError(
            "query_too_large",
            f"{len(set(years))} years requested; the limit per point call is "
            f"{ctx.config.limits.max_years_per_point}.",
            details={
                "limit": ctx.config.limits.max_years_per_point,
                "limitName": "max_years_per_point",
                "requested": len(set(years)),
                "unit": "years",
                "suggestion": "split the range",
            },
        )
    await check_years(ctx, years)
    where = location_for(lat, lon, region)
    ctx.stats.backend = "single-pixel"
    data = await ctx.services.pixel.get_years(where, years, ctx.stats)
    return where, data


@register_tool(
    "daymet_get_point_daily",
    title="Daily Daymet values at a point",
    description=(
        "Daily Daymet V4 R1 values (dayl, prcp, srad, swe, tmax, tmin, vp) for the 1 km cell "
        "containing a point, via the credential-free ORNL single-pixel API. Give whole years "
        "or a start/end date. Units sit next to every series; years have 365 days (leap years "
        "drop Dec 31). Paged by offset/limit. Next: call daymet_get_point_summary for monthly "
        "totals/means, then daymet_get_citation."
    ),
    input_model=PointDailyInput,
    output_model=PointDailyOutput,
    surface="point",
    endpoints=[ENDPOINT],
)
async def daymet_get_point_daily(args: PointDailyInput, ctx: ToolContext) -> PointDailyOutput:
    variables = unique_variables(args.variables)
    notes = [PROVISIONAL_NOTE, ROUNDING_NOTE]
    if args.years is not None:
        years = sorted(set(args.years))
        window = None
    else:
        if args.start_date is None or args.end_date is None:  # excluded by the input model
            raise ToolError("invalid_argument", "Give either years or start_date and end_date.")
        for d in (args.start_date, args.end_date):
            if not in_calendar(d):
                raise ToolError(
                    "invalid_argument",
                    f"{d.isoformat()} is not in the Daymet calendar (leap years drop Dec 31).",
                    details={"reason": "not_in_daymet_calendar", "date": d.isoformat()},
                    hint=f"Use {d.year}-12-30 as the last day of {d.year}.",
                )
        years = list(range(args.start_date.year, args.end_date.year + 1))
        window = (args.start_date, args.end_date)
    where, data = await fetch_point(ctx, args.lat, args.lon, years)
    dates, series = stitch_years(data, years)
    if window is not None:
        keep = [i for i, d in enumerate(dates) if window[0] <= d <= window[1]]
        dates = [dates[i] for i in keep]
        series = {k: [v[i] for i in keep] for k, v in series.items()}
    sl, page = page_window(len(dates), args.offset, args.limit)
    shown = dates[sl]
    if any(is_leap(y) for y in years):
        notes.append("Leap years in this request have Feb 29 and no Dec 31 (365 Daymet days).")
    return PointDailyOutput(
        location=_location(args.lat, args.lon, where, data),
        calendar=CalendarInfo(),
        data_version=DATA_VERSION,
        doi=DAILY_DOI,
        time=TimeAxis(
            date=[d.isoformat() for d in shown],
            year=[d.year for d in shown],
            yday=[date_to_yday(d) for d in shown],
        ),
        series={
            v: DailySeries(
                units=VARIABLES[v].daily_units,
                description=VARIABLES[v].description,
                values=round_daily(series[v][sl]),
            )
            for v in variables
        },
        page=page,
        notes=notes,
        next_steps=[
            f"daymet_get_point_summary(lat={args.lat}, lon={args.lon}, period='monthly', "
            f"start_year={years[0]}, end_year={years[-1]})",
            CITE_STEP,
        ],
        source=Source(
            endpoints=list(ctx.stats.endpoints) or [ENDPOINT],
            via="single-pixel",
            cached=ctx.stats.requests == 0,
        ),
    )


@register_tool(
    "daymet_get_point_summary",
    title="Monthly or annual Daymet summaries at a point",
    description=(
        "Monthly or annual summaries computed from Daymet daily data at a point. prcp is a SUM "
        "(mm/month, mm/year); tmax, tmin, vp, swe, srad and dayl are MEANS of daily values "
        "(swe 'last' and srad 'total' MJ/m2 on request). Every series states its aggregation, "
        "units and a field label such as prcp_monthly_total_mm. Covers the latest daily year. "
        "Next: call daymet_get_citation."
    ),
    input_model=PointSummaryInput,
    output_model=PointSummaryOutput,
    surface="point",
    endpoints=[ENDPOINT],
)
async def daymet_get_point_summary(args: PointSummaryInput, ctx: ToolContext) -> PointSummaryOutput:
    variables = unique_variables(args.variables)
    years = list(range(args.start_year, args.end_year + 1))
    where, data = await fetch_point(ctx, args.lat, args.lon, years)
    dates, series = stitch_years(data, years)
    specs = specs_for(variables, args.period, args.aggregation_overrides)
    periods, values = summarise(dates, series, specs, args.period)
    keep = list(range(len(periods)))
    if args.months:
        wanted = set(args.months)
        keep = [i for i, p in enumerate(periods) if p.month in wanted]
    sl, page = page_window(len(keep), args.offset, args.limit)
    idx = keep[sl]
    notes = [PROVISIONAL_NOTE, ROUNDING_NOTE]
    if any(is_leap(y) for y in years):
        notes.append(LEAP_DEC_NOTE)
    if any(not periods[i].complete for i in idx):
        notes.append(
            "Periods with a missing daily value are complete=false with value null (no imputation)."
        )
    notes.append(
        "Means are arithmetic over the Daymet days present; sums are not rescaled to a nominal "
        "month length."
    )
    derived = [f"series.{s.variable} ({s.field_label}): {DERIVED_NOTE}" for s in specs]
    return PointSummaryOutput(
        location=_location(args.lat, args.lon, where, data),
        calendar=CalendarInfo(),
        data_version=DATA_VERSION,
        doi=DAILY_DOI,
        period=args.period,
        periods=[
            PeriodOut(
                label=periods[i].label,
                year=periods[i].year,
                month=periods[i].month,
                day_count=periods[i].day_count,
                complete=periods[i].complete,
                first_date=periods[i].first_date.isoformat(),
                last_date=periods[i].last_date.isoformat(),
            )
            for i in idx
        ],
        series={
            s.variable: SummarySeries(
                aggregation=s.method,
                daily_units=s.daily_units,
                units=s.units,
                field_label=s.field_label,
                definition=s.definition,
                values=[values[s.variable][i] for i in idx],
            )
            for s in specs
        },
        page=page,
        notes=notes,
        next_steps=[
            f"daymet_get_point_daily(lat={args.lat}, lon={args.lon}, years=[{args.start_year}])",
            CITE_STEP,
        ],
        source=Source(
            endpoints=list(ctx.stats.endpoints) or [ENDPOINT],
            via="single-pixel",
            cached=ctx.stats.requests == 0,
            derived=derived,
        ),
    )
