# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""One live test per tool against the real ORNL DAAC single-pixel API and NASA CMR.

Volume is kept small (single pixels, one 3x3 mosaic, a 2-day window). Key sets and values
are compared with the recorded fixtures to detect upstream drift or data revisions.
Earthdata (``-m "network and edl"``) needs ``DAYMET_MCP_EARTHDATA__TOKEN`` and is skipped
otherwise.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import pytest

from daymet_mcp.daymet.single_pixel import parse_response
from daymet_mcp.server import DaymetServer
from tests.fixture_router import DEM_CENTRE, HAWAII, MOSAIC_BBOX, fixture_json
from tests.helpers import call_ok

pytestmark = pytest.mark.network
LAT, LON = DEM_CENTRE


async def test_live_ping(live_server: DaymetServer) -> None:
    out = await call_ok(live_server, "daymet_ping", {"check_upstream": True})
    assert out["upstream"]["ok"] is True and out["upstream"]["rows"] == 2


async def test_live_list_variables(live_server: DaymetServer) -> None:
    out = await call_ok(live_server, "daymet_list_variables")
    latest = {c["product"]: c for c in out["collections"]}
    assert latest["daily"]["latestYearSource"] == "cmr"
    assert latest["daily"]["latestYear"] >= 2025


async def test_live_locate_cell(live_server: DaymetServer) -> None:
    out = await call_ok(live_server, "daymet_locate_cell", {"lat": LAT, "lon": LON})
    assert (out["cell"]["col"], out["cell"]["row"]) == (3985, 5672)


async def test_live_point_daily_matches_fixture(live_server: DaymetServer) -> None:
    out = await call_ok(
        live_server, "daymet_get_point_daily", {"lat": LAT, "lon": LON, "years": [2020]}
    )
    assert len(out["time"]["date"]) == 365 and out["time"]["date"][-1] == "2020-12-30"
    _, fixture, _ = parse_response(fixture_json("pixel_dem_centre_2020"), expected_years=[2020])
    for var, series in out["series"].items():
        expected = [None if v is None else round(v, 2) for v in fixture[2020][var]]
        assert series["values"] == expected, f"{var} differs from the recorded fixture"


async def test_live_point_daily_hawaii(live_server: DaymetServer) -> None:
    out = await call_ok(
        live_server,
        "daymet_get_point_daily",
        {"lat": HAWAII[0], "lon": HAWAII[1], "start_date": "2020-02-28", "end_date": "2020-03-01"},
    )
    assert out["time"]["date"] == ["2020-02-28", "2020-02-29", "2020-03-01"]


async def test_live_point_summary_monthly_prcp(live_server: DaymetServer) -> None:
    daily = await call_ok(
        live_server,
        "daymet_get_point_daily",
        {"lat": LAT, "lon": LON, "years": [2020], "variables": ["prcp"]},
    )
    out = await call_ok(
        live_server,
        "daymet_get_point_summary",
        {
            "lat": LAT,
            "lon": LON,
            "period": "monthly",
            "start_year": 2020,
            "end_year": 2020,
            "variables": ["prcp"],
        },
    )
    assert out["series"]["prcp"]["aggregation"] == "sum"
    assert out["series"]["prcp"]["units"] == "mm/month"
    total_monthly = math.fsum(out["series"]["prcp"]["values"])
    total_daily = math.fsum(daily["series"]["prcp"]["values"])
    assert total_monthly == pytest.approx(total_daily, abs=0.01)
    assert out["periods"][11]["dayCount"] == 30


async def test_live_get_area(live_server: DaymetServer) -> None:
    out = await call_ok(
        live_server,
        "daymet_get_area",
        {
            "bbox": MOSAIC_BBOX,
            "variables": ["prcp"],
            "start_year": 2020,
            "end_year": 2020,
            "temporal": "annual",
            "include_elevation": True,
        },
    )
    assert out["grid"]["shape"] == {"time": 1, "rows": 3, "cols": 3}
    assert out["elevationM"][1][1] == 2545.0


async def test_live_download_area(live_server: DaymetServer) -> None:
    out = await call_ok(
        live_server,
        "daymet_download_area",
        {
            "bbox": MOSAIC_BBOX,
            "variables": ["tmax"],
            "start_year": 2020,
            "end_year": 2020,
            "temporal": "annual",
        },
    )
    assert Path(out["manifestPath"]).is_file() and len(out["files"]) == 2


async def test_live_citation(live_server: DaymetServer) -> None:
    out = await call_ok(live_server, "daymet_get_citation", {"variables": ["prcp"]})
    assert out["citations"][0]["doi"] == "10.3334/ORNLDAAC/2129"


@pytest.mark.edl
@pytest.mark.skipif(
    not os.environ.get("DAYMET_MCP_EARTHDATA__TOKEN"), reason="needs DAYMET_MCP_EARTHDATA__TOKEN"
)
async def test_live_earthdata_area() -> None:  # pragma: no cover - needs credentials
    from daymet_mcp.config import load_config
    from daymet_mcp.server import create_server

    server = create_server(load_config(), transport="stdio")
    try:
        out = await call_ok(
            server,
            "daymet_get_area",
            {
                "bbox": MOSAIC_BBOX,
                "variables": ["tmax"],
                "start_year": 2020,
                "end_year": 2020,
                "temporal": "annual",
                "backend": "earthdata",
            },
        )
        assert out["backend"] == "earthdata-opendap"
    finally:
        await server.aclose()
