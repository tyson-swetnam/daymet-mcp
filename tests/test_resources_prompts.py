# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""daymet:// resources (static, JSON references, templates) and the three prompts."""

from __future__ import annotations

import json

import pytest

from daymet_mcp import prompts, resources
from daymet_mcp.errors import ToolError
from daymet_mcp.instructions import SERVER_INSTRUCTIONS
from daymet_mcp.server import DaymetServer


def test_lists() -> None:
    uris = [r.uri for r in resources.list_resources()]
    assert len(uris) == 6 and all(str(u).startswith("daymet://") for u in uris)
    templates = [t.uri_template for t in resources.list_resource_templates()]
    assert templates == ["daymet://cell/{lat}/{lon}", "daymet://point/{lat}/{lon}/monthly/{year}"]
    assert [p.name for p in prompts.list_prompts()] == [
        "daymet_eemt_inputs",
        "daymet_monthly_precip_check",
        "daymet_site_climate",
    ]


async def test_read_static(server: DaymetServer) -> None:
    agg = await resources.read_resource("daymet://guide/aggregation", server)
    assert agg.mime_type == "text/markdown" and "mm/month" in agg.text
    for uri in (
        "daymet://guide/overview",
        "daymet://guide/citing-daymet",
        "daymet://guide/earthdata-credentials",
    ):
        assert (await resources.read_resource(uri, server)).text.strip()
    variables = json.loads(
        (await resources.read_resource("daymet://reference/variables", server)).text
    )
    assert {v["name"]: v["monthly"]["aggregation"] for v in variables}["prcp"] == "sum"
    grid = json.loads((await resources.read_resource("daymet://reference/grid", server)).text)
    assert grid["grid"]["xFirstCentreM"] == -4560250 and "Lambert" in grid["esriWkt"]


async def test_read_templates(server: DaymetServer) -> None:
    cell = json.loads(
        (await resources.read_resource("daymet://cell/35.802997/-106.624036", server)).text
    )
    assert cell["cell"]["col"] == 3985
    month = json.loads(
        (
            await resources.read_resource(
                "daymet://point/35.802997/-106.624036/monthly/2020", server
            )
        ).text
    )
    assert month["series"]["prcp"]["fieldLabel"] == "prcp_monthly_total_mm"
    with pytest.raises(ToolError) as info:
        await resources.read_resource("daymet://point/0/0/monthly/2020", server)
    assert info.value.code == "invalid_argument"


async def test_unknown_resource(server: DaymetServer) -> None:
    with pytest.raises(ToolError) as info:
        await resources.read_resource("daymet://guide/agregation", server)
    assert info.value.code == "not_found"
    assert "daymet://guide/aggregation" in info.value.details["didYouMean"]


def test_prompts() -> None:
    r = prompts.get_prompt(
        "daymet_monthly_precip_check", {"lat": "35.8", "lon": "-106.6", "year": "2020"}
    )
    text = r.messages[0].content.text  # type: ignore[union-attr]
    assert "SUM (mm/month)" in text and "2020" in text
    r = prompts.get_prompt(
        "daymet_eemt_inputs",
        {"west": "-106.7", "south": "35.7", "east": "-106.5", "north": "35.9", "year": "2020"},
    )
    assert "daymet_download_area" in r.messages[0].content.text  # type: ignore[union-attr]
    r = prompts.get_prompt(
        "daymet_site_climate",
        {"lat": "35.8", "lon": "-106.6", "start_year": "2019", "end_year": "2020"},
    )
    assert "2019-2020" in r.messages[0].content.text  # type: ignore[union-attr]
    for name, args in [
        ("daymet_site_climate", {"lat": "x", "lon": "1", "start_year": "2019", "end_year": "2020"}),
        (
            "daymet_site_climate",
            {"lat": "95", "lon": "1", "start_year": "2019", "end_year": "2020"},
        ),
        ("daymet_monthly_precip_check", {"lat": "35", "lon": "-106"}),
        ("daymet_nope", {}),
    ]:
        with pytest.raises(ToolError):
            prompts.get_prompt(name, args)


def test_instructions() -> None:
    assert len(SERVER_INSTRUCTIONS) <= 1200
    for phrase in ("mm/month", "365 days", "Dec 31", "daymet_get_citation", "Earthdata token"):
        assert phrase in SERVER_INSTRUCTIONS
