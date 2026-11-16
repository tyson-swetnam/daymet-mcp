# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Models for ``daymet_get_area`` and ``daymet_download_area``."""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field, model_validator

from daymet_mcp.daymet.catalog import Variable
from daymet_mcp.models.common import (
    AggregationOverrides,
    BBox,
    CalendarInfo,
    DaymetInput,
    DaymetOutput,
    Limit,
    Offset,
    Page,
    ToolResultBase,
    Year,
)


class _AreaBase(DaymetInput):
    bbox: BBox = Field(
        description=(
            "WGS84 bounding box in decimal degrees; every Daymet cell whose centre falls inside "
            "is included."
        )
    )
    variables: list[Variable] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
        description="Daymet variables (dayl, prcp, srad, swe, tmax, tmin, vp).",
    )
    start_year: Year
    end_year: Year
    temporal: Literal["daily", "monthly", "annual"] = Field(
        description="daily values, or monthly/annual summaries computed from daily data."
    )
    aggregation_overrides: AggregationOverrides | None = Field(
        None, description="Only swe (mean|last) and srad (mean|total) have alternatives."
    )
    include_elevation: bool = Field(
        False, description="Add the Daymet 1 km cell elevation grid (m)."
    )
    backend: Literal["auto", "single_pixel", "earthdata"] = Field(
        "auto",
        description=(
            "auto = single_pixel when within its cell limit, else earthdata if a token is "
            "configured."
        ),
    )

    @model_validator(mode="after")
    def _years(self) -> _AreaBase:
        if self.end_year < self.start_year:
            raise ValueError("end_year must be >= start_year")
        return self


class AreaInput(_AreaBase):
    offset: Offset = 0
    limit: Limit = 366


class DownloadAreaInput(_AreaBase):
    format: Literal["aaigrid", "csv", "netcdf"] = Field(
        "aaigrid",
        description=(
            "aaigrid: one .asc+.prj per variable and time step (GDAL-readable, no extra deps); "
            "csv: one long table; netcdf: one file per variable and year (needs the [grid] extra)."
        ),
    )
    subdir: str | None = Field(
        None,
        pattern=r"^[A-Za-z0-9._-]{1,64}$",
        description="Folder under the configured downloads.dir (default: derived from the request).",
    )
    overwrite: bool = Field(False, description="Replace existing files with the same names.")


class Shape(DaymetOutput):
    time: int
    rows: int
    cols: int


class GridInfo(DaymetOutput):
    region: str
    crs: str
    col_range: list[int]
    row_range: list[int]
    x_centres_m: list[float]
    y_centres_m: list[float]
    shape: Shape
    cell_order: str = "row-major, north to south, west to east"


class AreaTime(DaymetOutput):
    labels: list[str]
    day_count: list[int]


class AreaSeries(DaymetOutput):
    aggregation: str
    units: str
    field_label: str
    definition: str
    values: list[list[list[float | None]]]


class AreaOutput(ToolResultBase):
    grid: GridInfo
    time: AreaTime
    series: dict[str, AreaSeries]
    elevation_m: list[list[float | None]] | None = None
    backend: Literal["single-pixel-mosaic", "earthdata-opendap"]
    cells_requested: int
    calendar: CalendarInfo
    page: Page

    budget_time_axis: ClassVar[bool] = True

    @classmethod
    def trim_time(cls, payload: dict[str, Any], keep: int) -> None:
        payload["time"]["labels"] = payload["time"]["labels"][:keep]
        payload["time"]["dayCount"] = payload["time"]["dayCount"][:keep]
        for s in payload["series"].values():
            s["values"] = s["values"][:keep]
        payload["grid"]["shape"]["time"] = min(keep, payload["grid"]["shape"]["time"])

    @classmethod
    def time_length(cls, payload: dict[str, Any]) -> int:
        return len(payload["time"]["labels"])


class FileOut(DaymetOutput):
    path: str
    format: str
    variable: str
    label: str
    aggregation: str
    units: str
    bytes: int
    sha256: str


class DownloadAreaOutput(ToolResultBase):
    directory: str
    files: list[FileOut]
    grid: GridInfo
    manifest_path: str
    backend: Literal["single-pixel-mosaic", "earthdata-opendap"]
    cells_requested: int
