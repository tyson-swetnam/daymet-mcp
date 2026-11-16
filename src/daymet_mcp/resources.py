# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""``daymet://`` resources (DESIGN.md §10): static guides, JSON references and two
templates backed by tools."""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from importlib import resources as ir
from typing import TYPE_CHECKING, Any

from mcp import types as t

from daymet_mcp.daymet.catalog import ESRI_WKT, PROJ4, REGIONS, grid_definition
from daymet_mcp.errors import ToolError
from daymet_mcp.tools.catalog import variable_table

if TYPE_CHECKING:
    from daymet_mcp.server import DaymetServer

META_KIND = "io.daymet-mcp/kind"
STATIC_TTL_MS = 86_400_000
DERIVED_TTL_MS = 3_600_000


@dataclass(frozen=True)
class StaticResource:
    uri: str
    name: str
    title: str
    description: str
    mime_type: str
    file: str | None = None


STATIC: tuple[StaticResource, ...] = (
    StaticResource(
        "daymet://guide/overview",
        "overview",
        "daymet-mcp overview",
        "What Daymet is, the backends, and when credentials are needed.",
        "text/markdown",
        "overview.md",
    ),
    StaticResource(
        "daymet://guide/aggregation",
        "aggregation",
        "Monthly and annual aggregation",
        "Sum vs mean per variable (monthly prcp = total, mm/month), calendar, rounding.",
        "text/markdown",
        "aggregation.md",
    ),
    StaticResource(
        "daymet://guide/citing-daymet",
        "citing-daymet",
        "Citing Daymet data",
        "Citation templates used by daymet_get_citation.",
        "text/markdown",
        "citing-daymet.md",
    ),
    StaticResource(
        "daymet://guide/earthdata-credentials",
        "earthdata-credentials",
        "Earthdata credentials",
        "How an operator sets an Earthdata token, and the rules.",
        "text/markdown",
        "earthdata-credentials.md",
    ),
    StaticResource(
        "daymet://reference/variables",
        "variables",
        "Variable and aggregation table",
        "Every variable with daily units and monthly/annual aggregation (JSON).",
        "application/json",
    ),
    StaticResource(
        "daymet://reference/grid",
        "grid",
        "Daymet grid and projection",
        "proj4, ESRI WKT, the North America grid definition and region bboxes (JSON).",
        "application/json",
    ),
)

TEMPLATES: tuple[tuple[str, str, str], ...] = (
    (
        "daymet://cell/{lat}/{lon}",
        "cell",
        "The Daymet cell containing lat/lon (daymet_locate_cell).",
    ),
    (
        "daymet://point/{lat}/{lon}/monthly/{year}",
        "point-monthly",
        "Monthly summaries of all variables for one year (daymet_get_point_summary).",
    ),
)
_CELL_RE = re.compile(r"^daymet://cell/(?P<lat>-?\d+(?:\.\d+)?)/(?P<lon>-?\d+(?:\.\d+)?)$")
_POINT_RE = re.compile(
    r"^daymet://point/(?P<lat>-?\d+(?:\.\d+)?)/(?P<lon>-?\d+(?:\.\d+)?)/monthly/(?P<year>\d{4})$"
)


@dataclass(frozen=True)
class ResourceContent:
    text: str
    mime_type: str
    ttl_ms: int


def list_resources() -> list[t.Resource]:
    return [
        t.Resource(
            uri=r.uri,
            name=r.name,
            title=r.title,
            description=r.description,
            mime_type=r.mime_type,
            meta={META_KIND: "static"},
        )
        for r in STATIC
    ]


def list_resource_templates() -> list[t.ResourceTemplate]:
    return [
        t.ResourceTemplate(
            uri_template=uri,
            name=name,
            description=desc,
            mime_type="application/json",
            meta={META_KIND: "derived"},
        )
        for uri, name, desc in TEMPLATES
    ]


def _static_text(res: StaticResource) -> str:
    if res.file:
        return ir.files("daymet_mcp").joinpath(f"resources_static/{res.file}").read_text("utf-8")
    if res.name == "variables":
        return json.dumps(
            [v.model_dump(by_alias=True, mode="json") for v in variable_table()], indent=1
        )
    return json.dumps(
        {
            "proj4": PROJ4,
            "esriWkt": ESRI_WKT,
            "grid": grid_definition(),
            "cellCentres": "x = -4560250 + 1000*col, y = 4984000 - 1000*row (metres)",
            "regions": {
                r.code: {
                    "name": r.name,
                    "west": r.west,
                    "south": r.south,
                    "east": r.east,
                    "north": r.north,
                }
                for r in REGIONS.values()
            },
        },
        indent=1,
    )


async def read_resource(uri: str, server: DaymetServer) -> ResourceContent:
    for res in STATIC:
        if res.uri == uri:
            return ResourceContent(_static_text(res), res.mime_type, STATIC_TTL_MS)
    m = _CELL_RE.match(uri)
    if m:
        return await _derived(
            server, "daymet_locate_cell", {"lat": float(m["lat"]), "lon": float(m["lon"])}
        )
    m = _POINT_RE.match(uri)
    if m:
        year = int(m["year"])
        return await _derived(
            server,
            "daymet_get_point_summary",
            {
                "lat": float(m["lat"]),
                "lon": float(m["lon"]),
                "period": "monthly",
                "start_year": year,
                "end_year": year,
            },
        )
    known = [r.uri for r in STATIC] + [u for u, _, _ in TEMPLATES]
    raise ToolError(
        "not_found",
        f"Unknown resource {uri!r}.",
        details={"uri": uri, "didYouMean": difflib.get_close_matches(uri, known, n=3, cutoff=0.3)},
    )


async def _derived(server: DaymetServer, tool: str, args: dict[str, Any]) -> ResourceContent:
    outcome = await server.call(tool, args)
    if outcome.is_error:
        err = outcome.payload.get("error", {})
        raise ToolError(
            err.get("code", "internal_error"),
            err.get("message", "failed"),
            details=err.get("details", {}),
        )
    return ResourceContent(
        json.dumps(outcome.payload, ensure_ascii=False), "application/json", DERIVED_TTL_MS
    )
