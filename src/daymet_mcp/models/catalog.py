# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Models for ``daymet_ping`` and ``daymet_list_variables``."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from daymet_mcp.models.common import CalendarInfo, DaymetInput, DaymetOutput, ToolResultBase


class PingInput(DaymetInput):
    check_upstream: bool = Field(
        False, description="Also make one tiny live single-pixel request (2-day window)."
    )


class ServerInfo(DaymetOutput):
    name: str
    version: str
    protocol_version: str
    transport: Literal["stdio", "http"]


class Backends(DaymetOutput):
    single_pixel: Literal["available"] = "available"
    earthdata: Literal["configured", "not_configured", "disabled_in_http_mode", "extra_missing"]


class UpstreamCheck(DaymetOutput):
    ok: bool
    latency_ms: float
    status: str
    rows: int | None = None


class PingOutput(ToolResultBase):
    server: ServerInfo
    backends: Backends
    upstream: UpstreamCheck | None = None


class ListVariablesInput(DaymetInput):
    """No arguments."""


class AggregationOut(DaymetOutput):
    aggregation: str
    units: str
    field_label: str
    definition: str


class AlternativeOut(DaymetOutput):
    aggregation: str
    monthly_units: str
    annual_units: str
    monthly_field_label: str
    definition: str


class VariableOut(DaymetOutput):
    name: str
    long_name: str
    daily_units: str
    description: str
    monthly: AggregationOut
    annual: AggregationOut
    alternatives: list[AlternativeOut] = Field(default_factory=list)
    in_ornl_summary_products: bool


class BBoxOut(DaymetOutput):
    west: float
    south: float
    east: float
    north: float


class RegionOut(DaymetOutput):
    code: str
    name: str
    bbox: BBoxOut
    first_year: int
    latest_daily_year: int | None = None
    cell_indices: bool


class CollectionOut(DaymetOutput):
    product: str
    concept_id: str
    doi: str
    latest_year: int | None = Field(
        None, description="Absent when CMR failed and no fallback exists."
    )
    latest_year_source: Literal["cmr", "fallback"]


class GridOut(DaymetOutput):
    crs: str
    region: str
    x_first_centre_m: float
    y_first_centre_m: float
    step_m: float
    n_cols: int
    n_rows: int


class ListVariablesOutput(ToolResultBase):
    variables: list[VariableOut]
    regions: list[RegionOut]
    calendar: CalendarInfo
    collections: list[CollectionOut]
    grid: GridOut
