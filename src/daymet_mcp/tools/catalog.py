# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""``daymet_list_variables``."""

from __future__ import annotations

from daymet_mcp.context import ToolContext
from daymet_mcp.daymet import lcc
from daymet_mcp.daymet.calendar import calendar_info
from daymet_mcp.daymet.catalog import (
    ALTERNATIVES,
    COLLECTIONS,
    PROJ4,
    PROVISIONAL_NOTE,
    REGIONS,
    VARIABLE_NAMES,
    VARIABLES,
    aggregation_spec,
)
from daymet_mcp.daymet.cmr import ENDPOINT as CMR_ENDPOINT
from daymet_mcp.models.catalog import (
    AggregationOut,
    AlternativeOut,
    BBoxOut,
    CollectionOut,
    GridOut,
    ListVariablesInput,
    ListVariablesOutput,
    RegionOut,
    VariableOut,
)
from daymet_mcp.models.common import CalendarInfo
from daymet_mcp.registry import register_tool


def grid_out() -> GridOut:
    return GridOut(
        crs=PROJ4,
        region="na",
        x_first_centre_m=lcc.X_FIRST_CENTRE,
        y_first_centre_m=lcc.Y_FIRST_CENTRE,
        step_m=lcc.STEP,
        n_cols=lcc.N_COLS,
        n_rows=lcc.N_ROWS,
    )


def variable_table() -> list[VariableOut]:
    out = []
    for name in VARIABLE_NAMES:
        info = VARIABLES[name]
        m = aggregation_spec(name, "monthly")
        a = aggregation_spec(name, "annual")
        alts = []
        for alt in ALTERNATIVES.get(name, ()):
            am = aggregation_spec(name, "monthly", alt)
            aa = aggregation_spec(name, "annual", alt)
            alts.append(
                AlternativeOut(
                    aggregation=alt,
                    monthly_units=am.units,
                    annual_units=aa.units,
                    monthly_field_label=am.field_label,
                    definition=am.definition,
                )
            )
        out.append(
            VariableOut(
                name=name,
                long_name=info.long_name,
                daily_units=info.daily_units,
                description=info.description,
                monthly=AggregationOut(
                    aggregation=m.method,
                    units=m.units,
                    field_label=m.field_label,
                    definition=m.definition,
                ),
                annual=AggregationOut(
                    aggregation=a.method,
                    units=a.units,
                    field_label=a.field_label,
                    definition=a.definition,
                ),
                alternatives=alts,
                in_ornl_summary_products=info.in_ornl_summaries,
            )
        )
    return out


@register_tool(
    "daymet_list_variables",
    title="List Daymet variables and aggregation rules",
    description=(
        "List Daymet V4 R1 variables with daily units and the exact monthly/annual aggregation "
        "the server uses (prcp = sum, others = mean), regions, year ranges, the 365-day "
        "calendar and collection DOIs. Next: call daymet_get_point_summary or daymet_locate_cell."
    ),
    input_model=ListVariablesInput,
    output_model=ListVariablesOutput,
    surface="catalog",
    endpoints=[CMR_ENDPOINT],
)
async def daymet_list_variables(args: ListVariablesInput, ctx: ToolContext) -> ListVariablesOutput:
    del args
    collections = []
    latest_daily = None
    notes = [PROVISIONAL_NOTE]
    for coll in COLLECTIONS:
        latest = await ctx.services.cmr.latest(coll.product, ctx.stats)
        if coll.product == "daily":
            latest_daily = latest.year
        if latest.source == "fallback":
            notes.append(
                f"CMR was unreachable; the {coll.product} latest year is the configured fallback."
            )
        collections.append(
            CollectionOut(
                product=coll.product,
                concept_id=coll.concept_id,
                doi=coll.doi,
                latest_year=latest.year,
                latest_year_source=latest.source,
            )
        )
    regions = [
        RegionOut(
            code=r.code,
            name=r.name,
            bbox=BBoxOut(west=r.west, south=r.south, east=r.east, north=r.north),
            first_year=ctx.config.daymet.first_year,
            latest_daily_year=latest_daily,
            cell_indices=r.code == "na",
        )
        for r in (REGIONS["na"], REGIONS["hi"], REGIONS["pr"])
    ]
    notes.append(
        "Monthly and annual values from daymet-mcp are computed from daily data; the ORNL "
        "monthly/annual products (2131/2130) use the same definitions but have no srad or dayl."
    )
    return ListVariablesOutput(
        variables=variable_table(),
        regions=regions,
        calendar=CalendarInfo(**calendar_info()),  # type: ignore[arg-type]
        collections=collections,
        grid=grid_out(),
        notes=notes,
        next_steps=[
            "daymet_get_point_summary(lat=..., lon=..., period='monthly', start_year=..., end_year=...)",
            "daymet_locate_cell(lat=..., lon=...)",
        ],
    )
