# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""``daymet_locate_cell`` (pure computation, no network)."""

from __future__ import annotations

import math

from daymet_mcp.context import ToolContext
from daymet_mcp.daymet import lcc
from daymet_mcp.daymet.catalog import PROJ4, region_for
from daymet_mcp.models.cell import CellOut, LocateCellInput, LocateCellOutput, QueryPoint
from daymet_mcp.registry import register_tool
from daymet_mcp.tools.catalog import grid_out


def locate(lat: float, lon: float) -> LocateCellOutput:
    region = region_for(lat, lon)
    x, y = lcc.forward(lat, lon)
    query = QueryPoint(lat=lat, lon=lon, x_m=round(x, 2), y_m=round(y, 2))
    notes: list[str] = []
    cell_out = None
    grid = None
    if region is None:
        notes.append("The point is outside every Daymet region bbox (na, hi, pr).")
    elif region == "na":
        cell = lcc.snap(x, y)
        if cell.in_grid():
            clat, clon = cell.centre_latlon()
            cell_out = CellOut(
                col=cell.col,
                row=cell.row,
                x_centre_m=cell.x_centre,
                y_centre_m=cell.y_centre,
                lat_centre=round(clat, 6),
                lon_centre=round(clon, 6),
                distance_to_centre_m=round(math.hypot(x - cell.x_centre, y - cell.y_centre), 1),
            )
            grid = grid_out()
        notes.append(
            "A point inside the bbox but over water cannot be detected offline; the data tools "
            "report it as not_found (off_grid)."
        )
    else:
        notes.append(
            f"Cell indices are not computed for region '{region}' in v0.1 (its mosaic origin is "
            "unverified); LCC coordinates are exact."
        )
    return LocateCellOutput(
        region=region,
        in_coverage=region is not None,
        query=query,
        cell=cell_out,
        crs=PROJ4,
        grid_definition=grid,
        notes=notes,
        next_steps=[
            f"daymet_get_point_summary(lat={lat}, lon={lon}, period='monthly', start_year=..., end_year=...)",
            f"daymet_get_point_daily(lat={lat}, lon={lon}, years=[...])",
        ],
    )


@register_tool(
    "daymet_locate_cell",
    title="Locate the Daymet grid cell",
    description=(
        "Map a WGS84 lat/lon to Daymet's Lambert Conformal Conic projection and the 1 km grid "
        "cell that contains it (column, row, cell-centre x/y and lat/lon, distance to centre). "
        "Pure computation; no network. Next: call daymet_get_point_daily or "
        "daymet_get_point_summary for that point."
    ),
    input_model=LocateCellInput,
    output_model=LocateCellOutput,
    surface="cell",
    endpoints=[],
    open_world=False,
)
async def daymet_locate_cell(args: LocateCellInput, ctx: ToolContext) -> LocateCellOutput:
    del ctx
    return locate(args.lat, args.lon)
