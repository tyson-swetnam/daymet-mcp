# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""``daymet_get_area`` and ``daymet_download_area`` (DESIGN.md §4.6-4.7).

Backends: ``single_pixel`` queries one cell centre at a time (credential-free, validated
in S1); ``earthdata`` (experimental, token + ``[grid]`` extra) subsets daily granules over
OPeNDAP. Both reduce daily values with the same :mod:`daymet_mcp.daymet.aggregate` rules.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import anyio

from daymet_mcp import __version__
from daymet_mcp.context import ToolContext
from daymet_mcp.daymet import lcc
from daymet_mcp.daymet.aggregate import summarise
from daymet_mcp.daymet.calendar import is_leap, year_dates
from daymet_mcp.daymet.catalog import (
    DAILY_DOI,
    DERIVED_NOTE,
    PROJ4,
    PROVISIONAL_NOTE,
    ROUNDING_NOTE,
    VARIABLES,
    AggSpec,
    Period,
    Variable,
    region_for,
)
from daymet_mcp.daymet.earthdata import ENDPOINT as EDL_ENDPOINT
from daymet_mcp.daymet.earthdata import require_grid_extra
from daymet_mcp.daymet.single_pixel import ENDPOINT as PIXEL_ENDPOINT
from daymet_mcp.daymet.single_pixel import PixelLocation
from daymet_mcp.daymet.writers import aaigrid_text, csv_text, netcdf_bytes, prj_text, write_file
from daymet_mcp.errors import TILE_NOT_FOUND, ToolError, UpstreamError
from daymet_mcp.models.area import (
    AreaInput,
    AreaOutput,
    AreaSeries,
    AreaTime,
    DownloadAreaInput,
    DownloadAreaOutput,
    FileOut,
    GridInfo,
    Shape,
)
from daymet_mcp.models.common import BBox, CalendarInfo, Source
from daymet_mcp.registry import register_tool
from daymet_mcp.tools._common import CITE_STEP, check_years, page_window, round_daily, specs_for
from daymet_mcp.tools.citation import citation_texts

#: Absolute ceiling on the bounding rectangle that is ever enumerated: one variable-year at the
#: largest allowed ``limits.earthdata_max_values`` (200e6 / 365 = 547,945 cells) plus margin.
#: The per-request ceiling (:func:`_rectangle_cap`) is usually far lower.
MAX_CANDIDATE_CELLS = 600_000
#: The bounding rectangle of a bbox that the single-pixel mosaic can serve may be much larger than
#: its included-cell count (thin bboxes are rotated against the LCC grid). The largest rectangle
#: seen for 2,132 random accepted bboxes with <= 121 cells was 32,964 cells (a 2.9 x 0.0012 degree
#: strip at 25.8N, 136.9W), so the single-pixel cap is this factor x pixel_mosaic_max_cells.
PIXEL_RECT_FACTOR = 400
EDGE_SAMPLES = 25


@dataclass
class AreaPlan:
    cols: tuple[int, int]
    rows: tuple[int, int]
    included: list[lcc.Cell]

    @property
    def xs(self) -> list[float]:
        return [lcc.X_FIRST_CENTRE + lcc.STEP * c for c in range(self.cols[0], self.cols[1] + 1)]

    @property
    def ys(self) -> list[float]:
        return [lcc.Y_FIRST_CENTRE - lcc.STEP * r for r in range(self.rows[0], self.rows[1] + 1)]


@dataclass(frozen=True)
class Bounds:
    """Candidate cell rectangle (inclusive, with a one-cell margin) around a bbox."""

    c0: int
    c1: int
    r0: int
    r1: int

    @property
    def n_cols(self) -> int:
        return self.c1 - self.c0 + 1

    @property
    def n_rows(self) -> int:
        return self.r1 - self.r0 + 1

    @property
    def cells(self) -> int:
        return self.n_cols * self.n_rows


def candidate_bounds(bbox: BBox) -> Bounds:
    """Region checks and the candidate rectangle; cheap (about 100 projections)."""
    probes = [
        (bbox.south, bbox.west),
        (bbox.south, bbox.east),
        (bbox.north, bbox.west),
        (bbox.north, bbox.east),
        ((bbox.south + bbox.north) / 2, (bbox.west + bbox.east) / 2),
    ]
    regions = {region_for(lat, lon) for lat, lon in probes}
    if regions & {"hi", "pr"}:
        raise ToolError(
            "feature_unavailable",
            "Area requests for Hawaii and Puerto Rico are not supported in v0.1 (grid origin unverified).",
            details={
                "reason": "region_cells_unverified",
                "regions": sorted(r for r in regions if r),
            },
            hint="Use daymet_get_point_daily / daymet_get_point_summary for points there.",
        )
    if regions != {"na"}:
        raise ToolError(
            "invalid_argument",
            "The bbox is not entirely inside the Daymet North America region.",
            details={"reason": "out_of_coverage"},
        )
    xs: list[float] = []
    ys: list[float] = []
    for i in range(EDGE_SAMPLES + 1):
        f = i / EDGE_SAMPLES
        lat = bbox.south + f * (bbox.north - bbox.south)
        lon = bbox.west + f * (bbox.east - bbox.west)
        for la, lo in ((lat, bbox.west), (lat, bbox.east), (bbox.south, lon), (bbox.north, lon)):
            x, y = lcc.forward(la, lo)
            xs.append(x)
            ys.append(y)
    lo_cell = lcc.snap(min(xs), max(ys))
    hi_cell = lcc.snap(max(xs), min(ys))
    return Bounds(lo_cell.col - 1, hi_cell.col + 1, lo_cell.row - 1, hi_cell.row + 1)


def _too_many_candidates(bounds: Bounds, cap: int) -> ToolError:
    return ToolError(
        "query_too_large",
        "The bbox covers more cells than any backend available for this request allows.",
        details={
            "limitName": "candidate_cells",
            "limit": cap,
            "requested": bounds.cells,
            "unit": "cells in the bounding rectangle",
            "suggestion": "use a smaller bbox",
        },
    )


def enumerate_cells(bbox: BBox, bounds: Bounds) -> AreaPlan:
    """Cells of ``bounds`` whose centre lies inside ``bbox``: one inverse projection per cell,
    so callers bound ``bounds.cells`` first and run this off the event loop."""
    included: list[lcc.Cell] = []
    for r in range(bounds.r0, bounds.r1 + 1):
        for c in range(bounds.c0, bounds.c1 + 1):
            cell = lcc.Cell(c, r)
            if not cell.in_grid():
                continue
            lat, lon = cell.centre_latlon()
            if bbox.south <= lat <= bbox.north and bbox.west <= lon <= bbox.east:
                included.append(cell)
    if not included:
        raise ToolError(
            "invalid_argument",
            "No Daymet cell centre falls inside the bbox (cells are 1 km).",
            details={"reason": "no_cell_centre_in_bbox"},
            hint="Enlarge the bbox or use daymet_get_point_daily for a single point.",
        )
    cols = (min(c.col for c in included), max(c.col for c in included))
    rows = (min(c.row for c in included), max(c.row for c in included))
    return AreaPlan(cols, rows, included)


def plan_area(bbox: BBox, cap: int = MAX_CANDIDATE_CELLS) -> AreaPlan:
    """Cells whose centre lies inside ``bbox`` (NA grid only in v0.1, D9), synchronously."""
    bounds = candidate_bounds(bbox)
    cap = min(cap, MAX_CANDIDATE_CELLS)
    if bounds.cells > cap:
        raise _too_many_candidates(bounds, cap)
    return enumerate_cells(bbox, bounds)


@dataclass
class AreaData:
    plan: AreaPlan
    backend: str
    labels: list[str]
    day_count: list[int]
    specs: list[AggSpec] | None
    cubes: dict[str, list[list[list[float | None]]]]
    elevation: list[list[float | None]] | None
    notes: list[str] = field(default_factory=list)
    endpoints: list[str] = field(default_factory=list)


def _earthdata_blocked(ctx: ToolContext) -> str | None:
    """Why the Earthdata backend cannot run for this caller (None when it can)."""
    if ctx.transport == "http" and not ctx.config.earthdata.allow_in_http_mode:
        return "http"
    if ctx.config.token_value() is None:
        return "token"
    return None


def _earthdata_error(
    ctx: ToolContext,
    reason: str,
    n_cells: int,
    n_years: int,
    *,
    rectangle: bool = False,
    forced: bool = False,
) -> ToolError:
    """``rectangle``: refused before enumeration, so ``n_cells`` is the bbox's bounding
    rectangle (with its one-cell margin), not the cells whose centres fall inside it.
    ``forced``: the caller asked for backend=earthdata (the size is not the reason)."""
    lim = ctx.config.limits
    size: dict[str, int] = {"boundingRectangleCells": n_cells} if rectangle else {"cells": n_cells}
    if reason == "http":
        return ToolError(
            "not_available_in_http_mode",
            "The Earthdata backend is disabled on this hosted server.",
            details={
                "reason": "earthdata_disabled_in_http_mode",
                **size,
                "limit": lim.pixel_mosaic_max_cells,
            },
            hint="Reduce the bbox to the credential-free limit, or run daymet-mcp locally.",
        )
    if forced:
        why = "backend='earthdata' was requested"
    else:
        area = (
            f"a bounding rectangle of {n_cells} cells"
            if rectangle
            else f"an area of {n_cells} cells"
        )
        why = (
            f"{area} x {n_years} years exceeds the credential-free limit of "
            f"{lim.pixel_mosaic_max_cells} cells / {lim.pixel_mosaic_max_cell_years} cell-years"
        )
    return ToolError(
        "auth_required",
        f"This request needs gridded Daymet data from NASA Earthdata ({why}). "
        "No Earthdata token is configured. Set the environment variable "
        "DAYMET_MCP_EARTHDATA__TOKEN before starting the server (stdio), or reduce the bbox.",
        details={
            "reason": "token_missing",
            **size,
            "guide": "daymet://guide/earthdata-credentials",
        },
    )


def _earthdata_cell_limit(ctx: ToolContext, n_years: int, n_vars: int) -> int:
    """Largest included-cell rectangle the Earthdata value limit allows."""
    return ctx.config.limits.earthdata_max_values // (365 * max(n_years, 1) * max(n_vars, 1))


def _check_rectangle(
    args: AreaInput | DownloadAreaInput,
    ctx: ToolContext,
    bounds: Bounds,
    n_years: int,
    n_vars: int,
) -> None:
    """Refuse, before any cell is enumerated, a rectangle that no usable backend could serve.

    Enumeration costs one inverse projection per candidate cell on the CPU, so an
    anonymous caller must not be able to make it large (protocol-security review).
    """
    blocked = _earthdata_blocked(ctx)
    if args.backend == "earthdata" and blocked is not None:
        raise _earthdata_error(ctx, blocked, bounds.cells, n_years, rectangle=True, forced=True)
    caps: list[int] = []
    if args.backend in ("auto", "single_pixel"):
        caps.append(PIXEL_RECT_FACTOR * ctx.config.limits.pixel_mosaic_max_cells)
    ed_limit = _earthdata_cell_limit(ctx, n_years, n_vars)
    # the candidate rectangle carries a one-cell margin on each side
    ed_cap = ed_limit + 2 * (bounds.n_cols + bounds.n_rows)
    if args.backend in ("auto", "earthdata") and blocked is None:
        caps.append(ed_cap)
    cap = min(max(caps), MAX_CANDIDATE_CELLS)
    if bounds.cells <= cap:
        return
    if args.backend == "auto" and blocked is not None and bounds.cells <= ed_cap:
        # Earthdata could serve this size; say what is missing, as the full plan would.
        raise _earthdata_error(ctx, blocked, bounds.cells, n_years, rectangle=True)
    raise _too_many_candidates(bounds, cap)


def _choose_backend(
    args: AreaInput | DownloadAreaInput, ctx: ToolContext, n_cells: int, n_years: int
) -> str:
    lim = ctx.config.limits
    cell_years = n_cells * n_years
    fits = n_cells <= lim.pixel_mosaic_max_cells and cell_years <= lim.pixel_mosaic_max_cell_years
    if args.backend == "single_pixel" or (args.backend == "auto" and fits):
        if not fits:
            over_cells = n_cells > lim.pixel_mosaic_max_cells
            raise ToolError(
                "query_too_large",
                f"{n_cells} cells x {n_years} years exceeds the single-pixel mosaic limit.",
                details={
                    "limitName": "pixel_mosaic_max_cells"
                    if over_cells
                    else "pixel_mosaic_max_cell_years",
                    "limit": lim.pixel_mosaic_max_cells
                    if over_cells
                    else lim.pixel_mosaic_max_cell_years,
                    "requested": n_cells if over_cells else cell_years,
                    "unit": "cells" if over_cells else "cell-years",
                    "suggestion": "shrink the bbox or the year range, or use backend=earthdata with a token",
                },
            )
        return "single_pixel"
    # earthdata needed
    blocked = _earthdata_blocked(ctx)
    if blocked is not None:
        raise _earthdata_error(ctx, blocked, n_cells, n_years)
    require_grid_extra()
    return "earthdata"


async def _pixel_cells(
    ctx: ToolContext, plan: AreaPlan, years: Sequence[int]
) -> tuple[
    dict[tuple[int, int], dict[str, list[float | None]]], dict[tuple[int, int], dict[str, Any]], int
]:
    out: dict[tuple[int, int], dict[str, list[float | None]]] = {}
    headers: dict[tuple[int, int], dict[str, Any]] = {}
    off_grid = 0
    # Failures are collected here instead of escaping the task group: anyio would wrap them in
    # an ExceptionGroup, which registry.invoke cannot map (it surfaced as internal_error).
    failures: list[UpstreamError] = []

    async def one(cell: lcc.Cell, scope: anyio.CancelScope) -> None:
        nonlocal off_grid
        lat, lon = cell.centre_latlon()
        where = PixelLocation("na", round(lat, 6), round(lon, 6), cell)
        try:
            data = await ctx.services.pixel.get_years(where, years, ctx.stats)
        except UpstreamError as exc:
            if exc.status == 400 and TILE_NOT_FOUND in exc.message:
                off_grid += 1
                return
            failures.append(exc)
            scope.cancel()  # fail fast: the mosaic is incomplete anyway
            return
        series: dict[str, list[float | None]] = {}
        for y in sorted(set(years)):
            for var, values in data[y].values.items():
                series.setdefault(var, []).extend(values)
        out[(cell.col, cell.row)] = series
        headers[(cell.col, cell.row)] = next(iter(data.values())).header

    async with anyio.create_task_group() as tg:
        for cell in plan.included:
            tg.start_soon(one, cell, tg.cancel_scope)
    if failures:
        # a 429 carries retryAfterS, the most useful thing to tell the caller
        raise next((e for e in failures if e.status == 429), failures[0])
    return out, headers, off_grid


async def _earthdata_cells(
    ctx: ToolContext, plan: AreaPlan, years: Sequence[int], variables: Sequence[str]
) -> dict[tuple[int, int], dict[str, list[float | None]]]:
    n_days = 365 * len(years)
    cells_rect = (plan.cols[1] - plan.cols[0] + 1) * (plan.rows[1] - plan.rows[0] + 1)
    n_values = cells_rect * n_days * len(variables)
    if n_values > ctx.config.limits.earthdata_max_values:
        raise ToolError(
            "query_too_large",
            "The Earthdata subset would exceed the configured value limit.",
            details={
                "limitName": "earthdata_max_values",
                "limit": ctx.config.limits.earthdata_max_values,
                "requested": n_values,
                "unit": "cells x days x variables",
                "suggestion": "fewer years, variables or a smaller bbox",
            },
        )
    out: dict[tuple[int, int], dict[str, list[float | None]]] = {
        (c.col, c.row): {} for c in plan.included
    }
    for var in variables:
        for y in sorted(set(years)):
            cube = await ctx.services.earthdata.daily_cube(
                "na", var, y, plan.rows, plan.cols, plan.xs, plan.ys, ctx.stats
            )
            for cell in plan.included:
                r = cell.row - plan.rows[0]
                c = cell.col - plan.cols[0]
                out[(cell.col, cell.row)].setdefault(var, []).extend(plane[r][c] for plane in cube)
    return out


async def build_area(args: AreaInput | DownloadAreaInput, ctx: ToolContext) -> AreaData:
    years = list(range(args.start_year, args.end_year + 1))
    variables: list[Variable] = list(dict.fromkeys(args.variables))
    specs = (
        None
        if args.temporal == "daily"
        else specs_for(variables, args.temporal, args.aggregation_overrides)
    )
    n_vars = len(variables) + (
        1 if specs and any(s.method == "total" for s in specs) and "dayl" not in variables else 0
    )
    bounds = candidate_bounds(args.bbox)
    _check_rectangle(args, ctx, bounds, len(years), n_vars)
    # Pure-Python CPU work: keep it off the event loop so health checks and the per-tool
    # timeout keep working (abandon_on_cancel lets fail_after return; the bounded thread ends).
    plan = await anyio.to_thread.run_sync(
        partial(enumerate_cells, args.bbox, bounds), abandon_on_cancel=True
    )
    await check_years(ctx, years)
    backend = _choose_backend(args, ctx, len(plan.included), len(years))
    notes = [PROVISIONAL_NOTE, ROUNDING_NOTE]
    elevation: list[list[float | None]] | None = None
    if backend == "single_pixel":
        ctx.stats.backend = "single-pixel-mosaic"
        cells, headers, off_grid = await _pixel_cells(ctx, plan, years)
        if off_grid:
            notes.append(
                f"{off_grid} cell(s) are off the Daymet land grid (e.g. water); their values are null."
            )
        if args.include_elevation:
            elevation = [
                [
                    headers.get((c, r), {}).get("elevationM")
                    for c in range(plan.cols[0], plan.cols[1] + 1)
                ]
                for r in range(plan.rows[0], plan.rows[1] + 1)
            ]
        backend_label = "single-pixel-mosaic"
        endpoints = [PIXEL_ENDPOINT]
    else:
        ctx.stats.backend = "earthdata-opendap"
        need = list(variables)
        if specs and any(s.method == "total" for s in specs) and "dayl" not in need:
            need.append("dayl")
        cells = await _earthdata_cells(ctx, plan, years, need)
        notes.append(
            "EXPERIMENTAL backend: Earthdata OPeNDAP subsetting has not been verified with credentials."
        )
        if args.include_elevation:
            notes.append(
                "Cell elevation is not available from the Earthdata daily granules; elevationM is null."
            )
        backend_label = "earthdata-opendap"
        endpoints = [EDL_ENDPOINT]

    dates = [d for y in sorted(set(years)) for d in year_dates(y)]
    cubes: dict[str, list[list[list[float | None]]]] = {}
    per_cell: dict[tuple[int, int], dict[str, list[float | None]]]
    if specs is None:
        labels = [d.isoformat() for d in dates]
        day_count = [1] * len(dates)
        per_cell = {k: {str(v): round_daily(s[v]) for v in variables} for k, s in cells.items()}
    else:
        period: Period = "monthly" if args.temporal == "monthly" else "annual"
        labels = []
        day_count = []
        per_cell = {}
        for key, s in cells.items():
            periods, values = summarise(dates, s, specs, period)
            per_cell[key] = values
            if not labels:
                labels = [p.label for p in periods]
                day_count = [p.day_count for p in periods]
        if not labels:  # every cell off-grid
            empty: dict[str, list[float | None]] = {v: [None] * len(dates) for v in variables}
            periods, _ = summarise(dates, empty, specs, period)
            labels = [p.label for p in periods]
            day_count = [p.day_count for p in periods]
    for var in variables:
        cube: list[list[list[float | None]]] = []
        for t in range(len(labels)):
            plane = []
            for r in range(plan.rows[0], plan.rows[1] + 1):
                plane.append(
                    [
                        (per_cell[(c, r)][var][t] if (c, r) in per_cell else None)
                        for c in range(plan.cols[0], plan.cols[1] + 1)
                    ]
                )
            cube.append(plane)
        cubes[var] = cube
    if len(plan.included) < (plan.cols[1] - plan.cols[0] + 1) * (plan.rows[1] - plan.rows[0] + 1):
        notes.append("Cells of the bounding rectangle whose centre is outside the bbox are null.")
    if args.temporal != "daily" and any(is_leap(y) for y in years):
        notes.append("Leap-year December has 30 days in Daymet; monthly totals cover Dec 1-30.")
    return AreaData(
        plan, backend_label, labels, day_count, specs, cubes, elevation, notes, endpoints
    )


def _grid_info(plan: AreaPlan, n_time: int) -> GridInfo:
    return GridInfo(
        region="na",
        crs=PROJ4,
        col_range=list(plan.cols),
        row_range=list(plan.rows),
        x_centres_m=plan.xs,
        y_centres_m=plan.ys,
        shape=Shape(time=n_time, rows=len(plan.ys), cols=len(plan.xs)),
    )


def _series_meta(var: Variable, specs: list[AggSpec] | None) -> tuple[str, str, str, str]:
    if specs is None:
        info = VARIABLES[var]
        return "none (daily)", info.daily_units, f"{var}_daily_{info.daily_units}", info.description
    s = next(sp for sp in specs if sp.variable == var)
    return s.method, s.units, s.field_label, s.definition


@register_tool(
    "daymet_get_area",
    title="Daymet grid for a small area",
    description=(
        "Daymet values on the native 1 km LCC grid for a small WGS84 bbox, returned in the "
        "result: daily values or monthly/annual summaries (prcp = sum mm/month, others = "
        "mean). values[time][row][col], rows north to south. Credential-free up to 121 cells via "
        "single-pixel; larger areas need an operator Earthdata token. Time axis paged. Next: "
        "call daymet_download_area for files, then daymet_get_citation."
    ),
    input_model=AreaInput,
    output_model=AreaOutput,
    surface="area",
    endpoints=[PIXEL_ENDPOINT, EDL_ENDPOINT],
    requires_token="optional",
)
async def daymet_get_area(args: AreaInput, ctx: ToolContext) -> AreaOutput:
    area = await build_area(args, ctx)
    sl, page = page_window(len(area.labels), args.offset, args.limit)
    series: dict[str, AreaSeries] = {}
    for var in dict.fromkeys(args.variables):
        agg, units, label, definition = _series_meta(var, area.specs)
        series[var] = AreaSeries(
            aggregation=agg,
            units=units,
            field_label=label,
            definition=definition,
            values=area.cubes[var][sl],
        )
    labels = area.labels[sl]
    derived = (
        [f"series.{s.variable} ({s.field_label}): {DERIVED_NOTE}" for s in area.specs]
        if area.specs
        else []
    )
    next_steps = [CITE_STEP]
    if args.temporal == "daily":
        next_steps.insert(0, "Use temporal='monthly' or daymet_download_area for long daily grids.")
    return AreaOutput(
        grid=_grid_info(area.plan, len(labels)),
        time=AreaTime(labels=labels, day_count=area.day_count[sl]),
        series=series,
        elevation_m=area.elevation,
        backend=area.backend,  # type: ignore[arg-type]
        cells_requested=len(area.plan.included),
        calendar=CalendarInfo(),
        page=page,
        notes=area.notes,
        next_steps=next_steps,
        source=Source(
            endpoints=list(ctx.stats.endpoints) or area.endpoints,
            via=area.backend,  # type: ignore[arg-type]
            cached=ctx.stats.requests == 0,
            derived=derived,
        ),
    )


# ---------------------------------------------------------------------------
# Downloads (stdio only)
# ---------------------------------------------------------------------------


def _safe_dir(root: Path, subdir: str, overwrite: bool) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    real_root = root.resolve(strict=True)
    target = real_root / subdir
    if target.is_symlink():
        raise ToolError(
            "invalid_argument",
            "The download folder is a symbolic link.",
            details={"reason": "symlink_refused"},
        )
    target.mkdir(exist_ok=True)
    resolved = target.resolve(strict=True)
    if resolved.parent != real_root:
        raise ToolError(
            "invalid_argument",
            "The download folder escapes downloads.dir.",
            details={"reason": "path_outside_downloads_dir"},
        )
    del overwrite
    return resolved


def _estimate_bytes(area: AreaData, fmt: str) -> int:
    n_cells = len(area.plan.xs) * len(area.plan.ys)
    per_value = {"aaigrid": 9, "csv": 90, "netcdf": 4}[fmt]
    return n_cells * len(area.labels) * len(area.cubes) * per_value + 4096


@register_tool(
    "daymet_download_area",
    title="Download a Daymet area to files",
    description=(
        "Write a small-area Daymet grid to files under the configured downloads.dir (stdio "
        "only): AAIGrid .asc+.prj per variable and time step (GDAL-readable), one CSV table, or "
        "NetCDF ([grid] extra). Same inputs and aggregation rules as daymet_get_area; writes "
        "manifest.json with sha256, URLs and citation. Next: import the files (e.g. r.in.gdal), "
        "then daymet_get_citation."
    ),
    input_model=DownloadAreaInput,
    output_model=DownloadAreaOutput,
    surface="area",
    endpoints=[PIXEL_ENDPOINT, EDL_ENDPOINT],
    transports=("stdio",),
    requires_token="optional",
    read_only=False,
    destructive=False,
    idempotent=True,
)
async def daymet_download_area(args: DownloadAreaInput, ctx: ToolContext) -> DownloadAreaOutput:
    if args.format == "netcdf":
        require_grid_extra()
    area = await build_area(args, ctx)
    estimate = _estimate_bytes(area, args.format)
    if estimate > ctx.config.downloads.max_bytes:
        raise ToolError(
            "download_limit_exceeded",
            f"The download would be about {estimate} bytes, above downloads.max_bytes.",
            details={
                "limit": ctx.config.downloads.max_bytes,
                "requested": estimate,
                "unit": "bytes",
            },
        )
    plan = area.plan
    region = "na"
    tag = f"c{plan.cols[0]}-{plan.cols[1]}_r{plan.rows[0]}-{plan.rows[1]}"
    subdir = (
        args.subdir or f"daymet_{region}_{args.temporal}_{args.start_year}-{args.end_year}_{tag}"
    )
    directory = _safe_dir(ctx.config.downloads.resolved_dir(), subdir, args.overwrite)

    planned: list[tuple[str, str | bytes, str, str, str, str, str]] = []
    for var in dict.fromkeys(args.variables):
        agg, units, label_field, _ = _series_meta(var, area.specs)
        kind = (
            "daily"
            if area.specs is None
            else f"{args.temporal}_{'total' if agg in ('sum', 'total') else agg}"
        )
        cube = area.cubes[var]
        if args.format == "aaigrid":
            for t, lab in enumerate(area.labels):
                base = f"daymet_{region}_{var}_{kind}_{lab}_{tag}"
                planned.append(
                    (
                        base + ".asc",
                        aaigrid_text(cube[t], plan.xs, plan.ys),
                        "aaigrid",
                        var,
                        lab,
                        agg,
                        units,
                    )
                )
                planned.append((base + ".prj", prj_text(), "prj", var, lab, agg, units))
        elif args.format == "netcdf":
            years = sorted({int(lab[:4]) for lab in area.labels})
            for y in years:
                idx = [i for i, lab in enumerate(area.labels) if int(lab[:4]) == y]
                blob = netcdf_bytes(
                    var,
                    [cube[i] for i in idx],
                    [area.labels[i] for i in idx],
                    plan.xs,
                    plan.ys,
                    {
                        "units": units,
                        "aggregation": agg,
                        "field_label": label_field,
                        "source_doi": DAILY_DOI,
                    },
                )
                planned.append(
                    (
                        f"daymet_{region}_{var}_{kind}_{y}_{tag}.nc",
                        blob,
                        "netcdf",
                        var,
                        str(y),
                        agg,
                        units,
                    )
                )
    if args.format == "csv":
        cols = [
            "region",
            "col",
            "row",
            "x_centre_m",
            "y_centre_m",
            "lat_centre",
            "lon_centre",
            "label",
            "day_count",
            "variable",
            "aggregation",
            "units",
            "field_label",
            "value",
        ]
        rows: list[dict[str, Any]] = []
        for var in dict.fromkeys(args.variables):
            agg, units, label_field, _ = _series_meta(var, area.specs)
            for t, lab in enumerate(area.labels):
                for ri, r in enumerate(range(plan.rows[0], plan.rows[1] + 1)):
                    for ci, c in enumerate(range(plan.cols[0], plan.cols[1] + 1)):
                        lat, lon = lcc.Cell(c, r).centre_latlon()
                        rows.append(
                            {
                                "region": region,
                                "col": c,
                                "row": r,
                                "x_centre_m": plan.xs[ci],
                                "y_centre_m": plan.ys[ri],
                                "lat_centre": round(lat, 6),
                                "lon_centre": round(lon, 6),
                                "label": lab,
                                "day_count": area.day_count[t],
                                "variable": var,
                                "aggregation": agg,
                                "units": units,
                                "field_label": label_field,
                                "value": area.cubes[var][t][ri][ci],
                            }
                        )
        kind = "daily" if area.specs is None else args.temporal
        planned.append(
            (
                f"daymet_{region}_{kind}_{args.start_year}-{args.end_year}_{tag}.csv",
                csv_text(rows, cols),
                "csv",
                ",".join(dict.fromkeys(args.variables)),
                f"{args.start_year}-{args.end_year}",
                "see column",
                "see column",
            )
        )
    if area.elevation is not None:
        base = f"daymet_{region}_elevation_{tag}"
        planned.append(
            (
                base + ".asc",
                aaigrid_text(area.elevation, plan.xs, plan.ys),
                "aaigrid",
                "elevation",
                "static",
                "none",
                "m",
            )
        )
        planned.append((base + ".prj", prj_text(), "prj", "elevation", "static", "none", "m"))

    existing = [name for name, *_ in planned if (directory / name).exists()]
    if existing and not args.overwrite:
        raise ToolError(
            "invalid_argument",
            f"{len(existing)} file(s) already exist in the download folder.",
            details={"reason": "files_exist", "examples": existing[:5]},
            hint="Pass overwrite=true to replace them (contents are deterministic).",
        )
    files: list[FileOut] = []
    for name, content, fmt, var_name, lab, agg, units in planned:
        path = directory / name
        if path.is_symlink():
            raise ToolError(
                "invalid_argument",
                "Refusing to write through a symbolic link.",
                details={"reason": "symlink_refused", "file": name},
            )
        nbytes, digest = write_file(path, content)
        files.append(
            FileOut(
                path=str(path),
                format=fmt,
                variable=var_name,
                label=lab,
                aggregation=agg,
                units=units,
                bytes=nbytes,
                sha256=digest,
            )
        )
    manifest = {
        "generatedBy": f"daymet-mcp {__version__}",
        "generatedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "request": args.model_dump(mode="json"),
        "backend": area.backend,
        "upstreamEndpoints": list(ctx.stats.endpoints) or area.endpoints,
        "grid": _grid_info(plan, len(area.labels)).model_dump(by_alias=True, mode="json"),
        "crsWkt": prj_text().strip(),
        "aggregation": [
            {
                "variable": var,
                **dict(
                    zip(
                        ("aggregation", "units", "fieldLabel", "definition"),
                        _series_meta(var, area.specs),
                        strict=True,
                    )
                ),
            }
            for var in dict.fromkeys(args.variables)
        ],
        "calendar": CalendarInfo().model_dump(by_alias=True),
        "notes": area.notes,
        "citations": citation_texts(
            ["daily"],
            ["single_pixel" if area.backend.startswith("single") else "earthdata"],
            list(args.variables),
        ),
        "files": [f.model_dump(by_alias=True) for f in files],
    }
    manifest_path = directory / "manifest.json"
    write_file(manifest_path, json.dumps(manifest, indent=1, ensure_ascii=False))
    derived = [f"files ({s.field_label}): {DERIVED_NOTE}" for s in area.specs] if area.specs else []
    return DownloadAreaOutput(
        directory=str(directory),
        files=files,
        grid=_grid_info(plan, len(area.labels)),
        manifest_path=str(manifest_path),
        backend=area.backend,  # type: ignore[arg-type]
        cells_requested=len(plan.included),
        notes=[*area.notes, f"{len(files)} files written under downloads.dir."],
        next_steps=[
            f"r.in.gdal input={files[0].path} output=..." if files else "inspect manifest.json",
            CITE_STEP,
        ],
        source=Source(
            endpoints=list(ctx.stats.endpoints) or area.endpoints,
            via=area.backend,  # type: ignore[arg-type]
            cached=ctx.stats.requests == 0,
            derived=derived,
        ),
    )


__all__ = ["build_area", "candidate_bounds", "enumerate_cells", "plan_area"]
