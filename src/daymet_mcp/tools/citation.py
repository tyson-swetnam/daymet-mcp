# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""``daymet_get_citation``: rendered locally from ``resources_static/citing-daymet.md``."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from functools import cache
from importlib import resources

from daymet_mcp.context import ToolContext
from daymet_mcp.models.citation import CitationInput, CitationOut, CitationOutput
from daymet_mcp.models.common import unique_variables
from daymet_mcp.registry import register_tool

DATA_POLICY_URL = "https://daymet.ornl.gov/citations"
_TEMPLATE_RE = re.compile(
    r"<!-- template (?P<attrs>[^>]*?) -->\n(?P<body>.*?)\n<!-- end -->", re.DOTALL
)
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
_BIB_RE = re.compile(r"```bibtex\n(?P<bib>.*?)\n```", re.DOTALL)


@cache
def load_templates() -> dict[str, dict[str, str]]:
    text = (
        resources.files("daymet_mcp")
        .joinpath("resources_static/citing-daymet.md")
        .read_text("utf-8")
    )
    out: dict[str, dict[str, str]] = {}
    for m in _TEMPLATE_RE.finditer(text):
        attrs = dict(_ATTR_RE.findall(m.group("attrs")))
        body = m.group("body")
        bib = _BIB_RE.search(body)
        attrs["text"] = body[: bib.start()].strip() if bib else body.strip()
        attrs["bibtex"] = bib.group("bib").strip() if bib else ""
        out[attrs["id"]] = attrs
    return out


def select(
    products: Sequence[str],
    access: Sequence[str],
    variables: Sequence[str],
    include_methods: bool = True,
) -> list[dict[str, str]]:
    t = load_templates()
    chosen = [t[p] for p in ("daily", "monthly", "annual") if p in products]
    if "single_pixel" in access:
        chosen.append(t["single_pixel"])
    if include_methods:
        chosen.append(t["method_2021"])
        if {"srad", "vp"} & set(variables):
            chosen += [t["method_2000"], t["method_1999"]]
    return chosen


def citation_texts(
    products: Sequence[str], access: Sequence[str], variables: Sequence[str]
) -> list[str]:
    return [c["text"] for c in select(products, access, variables)]


@register_tool(
    "daymet_get_citation",
    title="Cite Daymet data",
    description=(
        "Citation text, DOI and BibTeX for Daymet V4 R1 data: the dataset (required; "
        "server-computed monthly/annual values cite the daily product 2129), the single-pixel "
        "tool when used (required), and method papers (recommended; extra ones for srad/vp). "
        "No network. Next: paste the citations into your methods section."
    ),
    input_model=CitationInput,
    output_model=CitationOutput,
    surface="citation",
    endpoints=[],
    open_world=False,
)
async def daymet_get_citation(args: CitationInput, ctx: ToolContext) -> CitationOutput:
    del ctx
    variables = unique_variables(args.variables)
    picked = select(args.products, args.access, variables, args.include_method_papers)
    accessed = (args.accessed_on or datetime.now(UTC).date()).isoformat()
    notes = [
        "Server-computed monthly/annual summaries are derived from the daily product: cite DOI "
        "10.3334/ORNLDAAC/2129, not the ORNL monthly (2131) or annual (2130) products.",
        "The citation embedded in single-pixel responses adds B.E. Wilson as an author; the "
        "Daymet V4 R1 user guide form (without) is used here.",
        "All Daymet data are provisional and subject to revision; record the access date.",
    ]
    if "monthly" in args.products or "annual" in args.products:
        notes.append("Cite 2131/2130 only for values read from those ORNL products themselves.")
    return CitationOutput(
        citations=[
            CitationOut(
                role=c["role"],  # type: ignore[arg-type]
                requirement=c["requirement"],  # type: ignore[arg-type]
                text=c["text"],
                doi=c["doi"],
                doi_url=f"https://doi.org/{c['doi']}",
                bibtex=c["bibtex"],
            )
            for c in picked
        ],
        accessed_on=accessed,
        data_policy_url=DATA_POLICY_URL,
        notes=notes,
        next_steps=[
            "Paste the citations into your methods section; keep accessedOn with your data."
        ],
    )
