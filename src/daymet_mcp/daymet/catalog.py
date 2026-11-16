# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Variables, aggregation rules, regions, collections and the grid (DESIGN.md §3).

The aggregation table is the answer to "is monthly precipitation a total or a mean?":
prcp is a **sum** (mm/month, mm/year); tmax, tmin, vp, swe, srad and dayl are **means of
daily values**; swe (``last``) and srad (``total``, MJ m-2) have opt-in alternatives.
The ORNL monthly/annual products (DOIs 2131/2130) use the same definitions for prcp, tmax,
tmin, vp and swe and have no srad or dayl.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from daymet_mcp.daymet import lcc

Variable = Literal["dayl", "prcp", "srad", "swe", "tmax", "tmin", "vp"]
VARIABLE_NAMES: tuple[Variable, ...] = ("dayl", "prcp", "srad", "swe", "tmax", "tmin", "vp")
Period = Literal["monthly", "annual"]
Aggregation = Literal["sum", "mean", "last", "total"]


@dataclass(frozen=True)
class VariableInfo:
    name: Variable
    long_name: str
    daily_units: str
    upstream_column: str
    description: str
    in_ornl_summaries: bool


VARIABLES: dict[Variable, VariableInfo] = {
    "dayl": VariableInfo(
        "dayl",
        "day length",
        "s/day",
        "dayl (s)",
        "duration of the daylight period (flat horizon)",
        False,
    ),
    "prcp": VariableInfo(
        "prcp",
        "precipitation",
        "mm/day",
        "prcp (mm/day)",
        "daily total precipitation, all forms as water equivalent",
        True,
    ),
    "srad": VariableInfo(
        "srad",
        "shortwave radiation",
        "W/m2",
        "srad (W/m^2)",
        "incident shortwave radiation flux density averaged over the daylight period",
        False,
    ),
    "swe": VariableInfo(
        "swe",
        "snow water equivalent",
        "kg/m2",
        "swe (kg/m^2)",
        "amount of water in the snowpack",
        True,
    ),
    "tmax": VariableInfo(
        "tmax",
        "maximum air temperature",
        "degC",
        "tmax (deg c)",
        "daily maximum 2 m air temperature",
        True,
    ),
    "tmin": VariableInfo(
        "tmin",
        "minimum air temperature",
        "degC",
        "tmin (deg c)",
        "daily minimum 2 m air temperature",
        True,
    ),
    "vp": VariableInfo(
        "vp",
        "water vapour pressure",
        "Pa",
        "vp (Pa)",
        "daily average partial pressure of water vapour",
        True,
    ),
}

#: Default and allowed aggregation per variable (same for monthly and annual).
DEFAULT_AGGREGATION: dict[Variable, Aggregation] = {
    "dayl": "mean",
    "prcp": "sum",
    "srad": "mean",
    "swe": "mean",
    "tmax": "mean",
    "tmin": "mean",
    "vp": "mean",
}
ALTERNATIVES: dict[Variable, tuple[Aggregation, ...]] = {"swe": ("last",), "srad": ("total",)}

_LABEL_UNITS = {
    "degC": "degC",
    "Pa": "Pa",
    "kg/m2": "kg_m2",
    "W/m2": "W_m2",
    "s/day": "s",
    "mm": "mm",
    "MJ/m2": "MJ_m2",
}


@dataclass(frozen=True)
class AggSpec:
    variable: Variable
    period: Period
    method: Aggregation
    daily_units: str
    units: str
    field_label: str
    definition: str


def aggregation_spec(
    variable: Variable, period: Period, method: Aggregation | None = None
) -> AggSpec:
    """The exact reduction, units and machine label for ``variable`` over ``period``."""
    info = VARIABLES[variable]
    method = method or DEFAULT_AGGREGATION[variable]
    allowed = (DEFAULT_AGGREGATION[variable], *ALTERNATIVES.get(variable, ()))
    if method not in allowed:
        raise ValueError(f"{variable} cannot be aggregated with {method!r}; allowed: {allowed}")
    span = "month" if period == "monthly" else "year"
    span_days = (
        "the Daymet days in the month" if period == "monthly" else "the 365 Daymet days of the year"
    )
    if method == "sum":
        units = f"mm/{span}"
        label_units = "mm"
        word = "total"
        definition = f"sum of daily {variable} over {span_days}"
    elif method == "total":
        units = f"MJ/m2/{span}"
        label_units = "MJ/m2"
        word = "total"
        definition = f"sum over {span_days} of srad*dayl/1e6 (daily MJ/m2, Daymet guide Table 1)"
    elif method == "last":
        units = info.daily_units
        label_units = info.daily_units
        word = "last"
        definition = f"daily {variable} on the last Daymet day of the {span}"
    else:
        units = info.daily_units
        label_units = info.daily_units
        word = "mean"
        definition = f"arithmetic mean of daily {variable} over {span_days}"
    label = f"{variable}_{period}_{word}_{_LABEL_UNITS[label_units]}"
    return AggSpec(variable, period, method, info.daily_units, units, label, definition)


# ---------------------------------------------------------------------------
# Regions, collections, grid
# ---------------------------------------------------------------------------

Region = Literal["na", "hi", "pr"]


@dataclass(frozen=True)
class RegionInfo:
    code: Region
    name: str
    west: float
    south: float
    east: float
    north: float

    def contains(self, lat: float, lon: float) -> bool:
        return self.south <= lat <= self.north and self.west <= lon <= self.east


# Bounding boxes from the Daymet V4 R1 daily user guide. hi and pr are checked first: they
# lie inside the NA bbox.
REGIONS: dict[Region, RegionInfo] = {
    "hi": RegionInfo("hi", "Hawaii", -160.3056, 17.9539, -154.772, 23.5186),
    "pr": RegionInfo("pr", "Puerto Rico", -67.9927, 16.8444, -64.1196, 19.9382),
    "na": RegionInfo("na", "continental North America", -178.1333, 14.0749, -53.0567, 82.9143),
}


def region_for(lat: float, lon: float) -> Region | None:
    for code in ("hi", "pr", "na"):
        if REGIONS[code].contains(lat, lon):
            return code
    return None


@dataclass(frozen=True)
class Collection:
    product: Literal["daily", "monthly", "annual"]
    concept_id: str
    doi: str
    short_name: str


COLLECTIONS: tuple[Collection, ...] = (
    Collection(
        "daily", "C2532426483-ORNL_CLOUD", "10.3334/ORNLDAAC/2129", "Daymet_Daily_V4R1_2129"
    ),
    Collection(
        "monthly", "C2532007210-ORNL_CLOUD", "10.3334/ORNLDAAC/2131", "Daymet_Monthly_V4R1_2131"
    ),
    Collection(
        "annual", "C2531982907-ORNL_CLOUD", "10.3334/ORNLDAAC/2130", "Daymet_Annual_V4R1_2130"
    ),
)
DAILY_DOI = "10.3334/ORNLDAAC/2129"
TOOL_DOI = "10.3334/ORNLDAAC/2361"
DATA_VERSION = "4 R1"

PROJ4 = (
    "+proj=lcc +lat_1=25 +lat_2=60 +lat_0=42.5 +lon_0=-100 +x_0=0 +y_0=0 "
    "+ellps=WGS84 +units=m +no_defs"
)
ESRI_WKT = (
    'PROJCS["Daymet_LCC",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
    'SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],'
    'UNIT["Degree",0.0174532925199433]],PROJECTION["Lambert_Conformal_Conic"],'
    'PARAMETER["False_Easting",0.0],PARAMETER["False_Northing",0.0],'
    'PARAMETER["Central_Meridian",-100.0],PARAMETER["Standard_Parallel_1",25.0],'
    'PARAMETER["Standard_Parallel_2",60.0],PARAMETER["Latitude_Of_Origin",42.5],'
    'UNIT["Meter",1.0]]'
)


def grid_definition() -> dict[str, object]:
    return {
        "region": "na",
        "xFirstCentreM": lcc.X_FIRST_CENTRE,
        "yFirstCentreM": lcc.Y_FIRST_CENTRE,
        "stepM": lcc.STEP,
        "nCols": lcc.N_COLS,
        "nRows": lcc.N_ROWS,
    }


PROVISIONAL_NOTE = "All Daymet data are provisional and subject to revision (ORNL DAAC)."
DERIVED_NOTE = (
    "computed by daymet-mcp from Daymet daily V4 R1 (DOI 10.3334/ORNLDAAC/2129); "
    "not the ORNL monthly product (2131)"
)
ROUNDING_NOTE = (
    "Daily values are rounded to 2 decimals (the CSV precision); aggregates are computed "
    "from the unrounded upstream floats and rounded to 3 decimals."
)
