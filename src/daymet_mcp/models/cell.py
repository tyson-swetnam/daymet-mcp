# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Models for ``daymet_locate_cell``."""

from __future__ import annotations

from pydantic import Field

from daymet_mcp.models.catalog import GridOut
from daymet_mcp.models.common import DaymetInput, DaymetOutput, Lat, Lon, ToolResultBase


class LocateCellInput(DaymetInput):
    lat: Lat
    lon: Lon


class QueryPoint(DaymetOutput):
    lat: float
    lon: float
    x_m: float = Field(description="Daymet LCC x (m).")
    y_m: float = Field(description="Daymet LCC y (m).")


class CellOut(DaymetOutput):
    col: int
    row: int
    x_centre_m: float
    y_centre_m: float
    lat_centre: float
    lon_centre: float
    distance_to_centre_m: float


class LocateCellOutput(ToolResultBase):
    region: str | None = Field(None, description="na, hi or pr; absent outside coverage.")
    in_coverage: bool
    query: QueryPoint
    cell: CellOut | None = Field(
        None, description="NA grid cell; absent outside coverage and for hi/pr (D9)."
    )
    crs: str
    grid_definition: GridOut | None = None
