# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Base models, the result envelope and shared input types (DESIGN.md §4.0).

Inputs are snake_case (camelCase also accepted), ``extra="forbid"``, every field
described. Outputs are camelCase and subclass :class:`ToolResultBase`.
Adapted from idss-mesa/neon-mcp ``models/common.py`` (MIT).
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from pydantic import AliasChoices, AliasGenerator, BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from daymet_mcp.daymet.catalog import Variable


def _validation_alias(name: str) -> AliasChoices:
    camel = to_camel(name)
    return AliasChoices(name, camel) if camel != name else AliasChoices(name)


class DaymetInput(BaseModel):
    """Base for every tool input."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        alias_generator=AliasGenerator(validation_alias=_validation_alias),
    )


class DaymetOutput(BaseModel):
    """Base for every output object; dumped ``by_alias`` (camelCase)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Page(DaymetOutput):
    total: int | None = Field(None, description="Total time steps available.")
    returned: int = Field(description="Time steps in this result.")
    offset: int = Field(description="Index of the first returned time step.")
    limit: int = Field(description="Page size applied.")
    truncated: bool = Field(description="True when more time steps exist beyond this page.")
    next_offset: int | None = Field(None, description="Offset of the next page.")
    truncated_reason: Literal["limit", "budget"] | None = Field(
        None, description="limit = page size reached; budget = trimmed to the size budget."
    )


class Resolved(DaymetOutput):
    field: str
    input: str
    value: str


class Source(DaymetOutput):
    endpoints: list[str] = Field(default_factory=list)
    via: Literal["single-pixel", "single-pixel-mosaic", "earthdata-opendap", "cmr", "local"] = (
        "local"
    )
    cached: bool = False
    derived: list[str] = Field(default_factory=list)


class CalendarInfo(DaymetOutput):
    days_per_year: int = 365
    rule: str = "leap years keep Feb 29 and drop Dec 31"


class ToolResultBase(DaymetOutput):
    """Envelope carried by every tool result."""

    resolved: list[Resolved] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    source: Source | None = None

    #: Whether :func:`daymet_mcp.registry.fit_to_budget` may trim the time axis.
    budget_time_axis: ClassVar[bool] = False

    @classmethod
    def trim_time(cls, payload: dict[str, Any], keep: int) -> None:
        """Keep the first ``keep`` time steps in a dumped payload (override per model)."""
        raise NotImplementedError

    @classmethod
    def time_length(cls, payload: dict[str, Any]) -> int:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Shared input types
# ---------------------------------------------------------------------------

Lat = Annotated[float, Field(ge=-90, le=90, description="Latitude, decimal degrees WGS84.")]
Lon = Annotated[
    float, Field(ge=-180, le=180, description="Longitude, decimal degrees WGS84 (west negative).")
]
Year = Annotated[
    int,
    Field(
        ge=1980, description="Year (inclusive). Max = latest published year (checked at call time)."
    ),
]
VariablesField = Annotated[
    list[Variable] | None,
    Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
        description="Daymet variables (dayl, prcp, srad, swe, tmax, tmin, vp). Default: all seven.",
    ),
]
Offset = Annotated[int, Field(ge=0, description="Index of the first time step to return.")]
Limit = Annotated[int, Field(ge=1, le=1000, description="Max time steps to return.")]


class BBox(DaymetInput):
    west: float = Field(ge=-180, le=180, description="West longitude (degrees).")
    south: float = Field(ge=-90, le=90, description="South latitude (degrees).")
    east: float = Field(ge=-180, le=180, description="East longitude (degrees).")
    north: float = Field(ge=-90, le=90, description="North latitude (degrees).")

    @model_validator(mode="after")
    def _ordered(self) -> BBox:
        if self.west >= self.east:
            raise ValueError("bbox west must be < east")
        if self.south >= self.north:
            raise ValueError("bbox south must be < north")
        return self


class AggregationOverrides(DaymetInput):
    swe: Literal["mean", "last"] | None = Field(
        None, description="swe: mean (default, as ORNL) or last (value on the period's last day)."
    )
    srad: Literal["mean", "total"] | None = Field(
        None, description="srad: mean W/m2 (default) or total MJ/m2 (sum of srad*dayl/1e6)."
    )


def unique_variables(values: list[Variable] | None) -> list[Variable]:
    """Deduplicate preserving order; default to all seven."""
    from daymet_mcp.daymet.catalog import VARIABLE_NAMES

    if not values:
        return list(VARIABLE_NAMES)
    seen: list[Variable] = []
    for v in values:
        if v not in seen:
            seen.append(v)
    return seen
