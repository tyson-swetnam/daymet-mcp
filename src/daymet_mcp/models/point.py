# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Models for ``daymet_get_point_daily`` and ``daymet_get_point_summary``."""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar, Literal

from pydantic import Field, model_validator

from daymet_mcp.models.common import (
    AggregationOverrides,
    CalendarInfo,
    DaymetInput,
    DaymetOutput,
    Lat,
    Limit,
    Lon,
    Offset,
    Page,
    ToolResultBase,
    VariablesField,
    Year,
)


class CellRef(DaymetOutput):
    col: int
    row: int
    x_centre_m: float
    y_centre_m: float


class PointLocation(DaymetOutput):
    requested_lat: float
    requested_lon: float
    region: str
    cell: CellRef | None = Field(None, description="NA grid cell; null for hi/pr (D9).")
    query_lat: float = Field(description="Latitude sent upstream (the cell centre for NA).")
    query_lon: float
    tile: str | None = None
    elevation_m: float | None = None
    elevation_source: str = "single-pixel header (Daymet 1 km cell elevation)"


class PointDailyInput(DaymetInput):
    lat: Lat
    lon: Lon
    variables: VariablesField = None
    years: list[Year] | None = Field(
        None,
        min_length=1,
        max_length=46,
        json_schema_extra={"uniqueItems": True},
        description="Whole years. Give either years or start_date+end_date.",
    )
    start_date: date | None = Field(
        None, description="YYYY-MM-DD, inclusive; must exist in the Daymet calendar."
    )
    end_date: date | None = Field(None, description="YYYY-MM-DD, inclusive.")
    offset: Offset = 0
    limit: Limit = 366

    @model_validator(mode="after")
    def _one_window(self) -> PointDailyInput:
        has_years = self.years is not None
        has_dates = self.start_date is not None or self.end_date is not None
        if has_years == has_dates:
            raise ValueError("give exactly one of years or start_date+end_date")
        if has_dates and (self.start_date is None or self.end_date is None):
            raise ValueError("start_date and end_date must be given together")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class TimeAxis(DaymetOutput):
    date: list[str]
    year: list[int]
    yday: list[int]


class DailySeries(DaymetOutput):
    units: str
    description: str
    values: list[float | None]


class PointDailyOutput(ToolResultBase):
    location: PointLocation
    calendar: CalendarInfo
    data_version: str
    doi: str
    time: TimeAxis
    series: dict[str, DailySeries]
    page: Page

    budget_time_axis: ClassVar[bool] = True

    @classmethod
    def trim_time(cls, payload: dict[str, Any], keep: int) -> None:
        for key in ("date", "year", "yday"):
            payload["time"][key] = payload["time"][key][:keep]
        for s in payload["series"].values():
            s["values"] = s["values"][:keep]

    @classmethod
    def time_length(cls, payload: dict[str, Any]) -> int:
        return len(payload["time"]["date"])


class PointSummaryInput(DaymetInput):
    lat: Lat
    lon: Lon
    variables: VariablesField = None
    period: Literal["monthly", "annual"] = Field(
        description="monthly = calendar months; annual = Daymet 365-day year."
    )
    start_year: Year
    end_year: Year
    months: list[int] | None = Field(
        None,
        json_schema_extra={"uniqueItems": True},
        description="Optional month filter 1-12 (monthly only).",
    )
    aggregation_overrides: AggregationOverrides | None = Field(
        None,
        description=(
            "Only swe and srad have alternatives; every other variable's aggregation is fixed "
            "(see daymet_list_variables)."
        ),
    )
    offset: Offset = 0
    limit: Limit = 366

    @model_validator(mode="after")
    def _check(self) -> PointSummaryInput:
        if self.end_year < self.start_year:
            raise ValueError("end_year must be >= start_year")
        if self.months is not None:
            if self.period != "monthly":
                raise ValueError("months applies only to period=monthly")
            if not self.months or any(not 1 <= m <= 12 for m in self.months):
                raise ValueError("months must be integers 1-12")
        return self


class PeriodOut(DaymetOutput):
    label: str
    year: int
    month: int | None = None
    day_count: int
    complete: bool
    first_date: str
    last_date: str


class SummarySeries(DaymetOutput):
    aggregation: str
    daily_units: str
    units: str
    field_label: str
    definition: str
    values: list[float | None]


class PointSummaryOutput(ToolResultBase):
    location: PointLocation
    calendar: CalendarInfo
    data_version: str
    doi: str
    period: Literal["monthly", "annual"]
    periods: list[PeriodOut]
    series: dict[str, SummarySeries]
    page: Page

    budget_time_axis: ClassVar[bool] = True

    @classmethod
    def trim_time(cls, payload: dict[str, Any], keep: int) -> None:
        payload["periods"] = payload["periods"][:keep]
        for s in payload["series"].values():
            s["values"] = s["values"][:keep]

    @classmethod
    def time_length(cls, payload: dict[str, Any]) -> int:
        return len(payload["periods"])
