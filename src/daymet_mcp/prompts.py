# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Three task prompts (DESIGN.md §10): one user message each, arguments validated."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from mcp import types as t

from daymet_mcp.errors import ToolError


@dataclass(frozen=True)
class PromptSpec:
    name: str
    title: str
    description: str
    arguments: tuple[tuple[str, str], ...]
    render: Callable[[dict[str, float]], str]


def _num(
    args: Mapping[str, str] | None,
    name: str,
    *,
    integer: bool = False,
    lo: float | None = None,
    hi: float | None = None,
) -> float:
    raw = (args or {}).get(name)
    if raw is None or str(raw).strip() == "":
        raise ToolError("invalid_argument", f"Missing prompt argument {name!r}.")
    try:
        value = float(int(str(raw))) if integer else float(str(raw))
    except ValueError:
        raise ToolError("invalid_argument", f"Prompt argument {name!r} must be a number.") from None
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise ToolError("invalid_argument", f"Prompt argument {name!r} is out of range.")
    return value


def _site(a: dict[str, float]) -> str:
    return (
        f"Describe the climate at latitude {a['lat']}, longitude {a['lon']} from Daymet for "
        f"{int(a['start_year'])}-{int(a['end_year'])}.\n"
        "1. Call daymet_locate_cell to confirm the 1 km cell and region.\n"
        "2. Call daymet_get_point_summary with period='monthly' for those years.\n"
        "3. Summarise monthly normals: precipitation as monthly TOTALS (mm/month), temperature "
        "and vapour pressure as monthly MEANS; quote the field labels.\n"
        "4. Finish with the citations from daymet_get_citation."
    )


def _eemt(a: dict[str, float]) -> str:
    return (
        f"Prepare Daymet inputs for an EEMT run over bbox west={a['west']}, south={a['south']}, "
        f"east={a['east']}, north={a['north']} for {int(a['year'])}.\n"
        "1. Check the number of 1 km cells (daymet_get_area with temporal='annual' and one "
        "variable is a cheap probe) against the credential-free limit.\n"
        "2. Call daymet_download_area with temporal='monthly', variables=['tmin','tmax','prcp','vp'], "
        "include_elevation=true, format='aaigrid'. Monthly prcp is a total (mm/month); "
        "tmin/tmax/vp are means.\n"
        "3. Report the manifest path and the files, and cite with daymet_get_citation."
    )


def _precip(a: dict[str, float]) -> str:
    return (
        f"Show how monthly precipitation is derived at latitude {a['lat']}, longitude {a['lon']} "
        f"for {int(a['year'])}.\n"
        "1. Call daymet_get_point_daily for that year with variables=['prcp'].\n"
        "2. Call daymet_get_point_summary with period='monthly' and variables=['prcp'].\n"
        "3. Show each month's total next to the sum of its daily values, confirm they agree, "
        "and explain that Daymet monthly prcp is a SUM (mm/month), not a mean; note that a "
        "leap-year December has 30 Daymet days."
    )


PROMPTS: tuple[PromptSpec, ...] = (
    PromptSpec(
        "daymet_eemt_inputs",
        "EEMT inputs from Daymet",
        "Download monthly tmin/tmax/prcp/vp grids and elevation for an EEMT domain.",
        (
            ("west", "West longitude"),
            ("south", "South latitude"),
            ("east", "East longitude"),
            ("north", "North latitude"),
            ("year", "Year"),
        ),
        _eemt,
    ),
    PromptSpec(
        "daymet_monthly_precip_check",
        "Monthly precipitation check",
        "Show daily prcp and monthly totals side by side and explain sum vs mean.",
        (("lat", "Latitude"), ("lon", "Longitude"), ("year", "Year")),
        _precip,
    ),
    PromptSpec(
        "daymet_site_climate",
        "Site climate from Daymet",
        "Monthly climate normals for a point, with explicit totals and means, and citations.",
        (
            ("lat", "Latitude"),
            ("lon", "Longitude"),
            ("start_year", "First year"),
            ("end_year", "Last year"),
        ),
        _site,
    ),
)


def list_prompts() -> list[t.Prompt]:
    return [
        t.Prompt(
            name=p.name,
            title=p.title,
            description=p.description,
            arguments=[
                t.PromptArgument(name=n, description=d, required=True) for n, d in p.arguments
            ],
        )
        for p in PROMPTS
    ]


def get_prompt(name: str, arguments: Mapping[str, str] | None) -> t.GetPromptResult:
    spec = next((p for p in PROMPTS if p.name == name), None)
    if spec is None:
        raise ToolError("not_found", f"Unknown prompt {name!r}.")
    values: dict[str, float] = {}
    for arg, _ in spec.arguments:
        if arg in ("lat", "south", "north"):
            values[arg] = _num(arguments, arg, lo=-90, hi=90)
        elif arg in ("lon", "west", "east"):
            values[arg] = _num(arguments, arg, lo=-180, hi=180)
        else:
            values[arg] = _num(arguments, arg, integer=True, lo=1980, hi=2100)
    return t.GetPromptResult(
        description=spec.description,
        messages=[
            t.PromptMessage(
                role="user", content=t.TextContent(type="text", text=spec.render(values))
            )
        ],
    )
