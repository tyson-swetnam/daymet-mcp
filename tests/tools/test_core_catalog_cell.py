# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""daymet_ping, daymet_list_variables, daymet_locate_cell, daymet_get_citation."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from daymet_mcp.daymet.earthdata import grid_extra_available
from daymet_mcp.server import DaymetServer
from tests.fixture_router import DEM_CENTRE, HAWAII, TEST_TOKEN, FixtureRouter
from tests.helpers import call_err, call_ok

CMR = "GET cmr.earthdata.nasa.gov/search/granules.umm_json"


async def test_ping_offline(server: DaymetServer, router: FixtureRouter) -> None:
    out = await call_ok(server, "daymet_ping")
    assert out["server"]["name"] == "daymet-mcp"
    assert out["server"]["protocolVersion"] == "2026-07-28"
    assert out["server"]["transport"] == "stdio"
    assert out["backends"]["singlePixel"] == "available"
    assert "upstream" not in out or out["upstream"] is None
    assert router.calls == []


async def test_ping_check_upstream(server: DaymetServer, router: FixtureRouter) -> None:
    out = await call_ok(server, "daymet_ping", {"check_upstream": True})
    assert out["upstream"]["ok"] is True and out["upstream"]["rows"] == 2
    assert router.count("single-pixel") == 1


async def test_ping_upstream_failure_is_reported(
    server: DaymetServer, router: FixtureRouter
) -> None:
    key = (
        "GET daymet.ornl.gov/single-pixel/api/data?end=2020-01-02&format=json&lat=35.805702"
        "&lon=-106.626365&start=2020-01-01&vars=dayl,prcp,srad,swe,tmax,tmin,vp"
    )
    router.add(key, 503, text="down", times=3)
    out = await call_ok(server, "daymet_ping", {"check_upstream": True})
    assert out["upstream"]["ok"] is False and out["upstream"]["status"] == "status:503"


async def test_ping_backends(make_server: Callable[..., DaymetServer]) -> None:
    with_token = await call_ok(make_server(token=TEST_TOKEN), "daymet_ping")
    over_http = await call_ok(make_server(transport="http", token=TEST_TOKEN), "daymet_ping")
    if grid_extra_available():
        assert with_token["backends"]["earthdata"] == "configured"
        assert over_http["backends"]["earthdata"] == "disabled_in_http_mode"
    else:
        assert with_token["backends"]["earthdata"] == "extra_missing"


async def test_list_variables(server: DaymetServer, router: FixtureRouter) -> None:
    out = await call_ok(server, "daymet_list_variables")
    by_name = {v["name"]: v for v in out["variables"]}
    assert sorted(by_name) == ["dayl", "prcp", "srad", "swe", "tmax", "tmin", "vp"]
    prcp = by_name["prcp"]
    assert prcp["dailyUnits"] == "mm/day"
    assert prcp["monthly"] == {
        "aggregation": "sum",
        "units": "mm/month",
        "fieldLabel": "prcp_monthly_total_mm",
        "definition": "sum of daily prcp over the Daymet days in the month",
    }
    assert prcp["annual"]["units"] == "mm/year"
    for name in ("tmax", "tmin", "vp", "swe", "srad", "dayl"):
        assert by_name[name]["monthly"]["aggregation"] == "mean"
    assert by_name["vp"]["dailyUnits"] == "Pa"
    assert [a["aggregation"] for a in by_name["swe"]["alternatives"]] == ["last"]
    assert by_name["srad"]["alternatives"][0]["monthlyUnits"] == "MJ/m2/month"
    assert by_name["srad"]["inOrnlSummaryProducts"] is False
    latest = {c["product"]: (c["latestYear"], c["latestYearSource"]) for c in out["collections"]}
    assert latest == {"daily": (2025, "cmr"), "monthly": (2024, "cmr"), "annual": (2024, "cmr")}
    assert out["calendar"] == {"daysPerYear": 365, "rule": "leap years keep Feb 29 and drop Dec 31"}
    assert out["grid"]["xFirstCentreM"] == -4560250 and out["grid"]["nCols"] == 7814
    assert [r["code"] for r in out["regions"]] == ["na", "hi", "pr"]
    assert router.count("cmr.earthdata") == 3
    # cached for the next call
    await call_ok(server, "daymet_list_variables")
    assert router.count("cmr.earthdata") == 3


async def test_list_variables_cmr_fallback(server: DaymetServer, router: FixtureRouter) -> None:
    for concept in ("C2532426483-ORNL_CLOUD", "C2532007210-ORNL_CLOUD", "C2531982907-ORNL_CLOUD"):
        router.add(
            f"{CMR}?collection_concept_id={concept}&page_size=1&sort_key=-start_date",
            500,
            text="err",
            times=3,
        )
    out = await call_ok(server, "daymet_list_variables")
    latest = {
        c["product"]: (c.get("latestYear"), c["latestYearSource"]) for c in out["collections"]
    }
    assert latest["daily"] == (2025, "fallback")
    assert latest["monthly"] == (None, "fallback")
    assert any("fallback" in n for n in out["notes"])


async def test_locate_dem_centre(server: DaymetServer, router: FixtureRouter) -> None:
    out = await call_ok(server, "daymet_locate_cell", {"lat": DEM_CENTRE[0], "lon": DEM_CENTRE[1]})
    assert out["region"] == "na" and out["inCoverage"] is True
    assert out["query"] == {
        "lat": 35.802997,
        "lon": -106.624036,
        "xM": -575071.13,
        "yM": -688303.76,
    }
    cell = out["cell"]
    assert (cell["col"], cell["row"]) == (3985, 5672)
    assert (cell["xCentreM"], cell["yCentreM"]) == (-575250.0, -688000.0)
    assert (cell["latCentre"], cell["lonCentre"]) == (35.805702, -106.626365)
    assert cell["distanceToCentreM"] == pytest.approx(352.5, abs=0.1)
    assert out["gridDefinition"]["stepM"] == 1000
    assert router.calls == []


async def test_locate_hawaii_and_outside(server: DaymetServer) -> None:
    hi = await call_ok(server, "daymet_locate_cell", {"lat": HAWAII[0], "lon": HAWAII[1]})
    assert hi["region"] == "hi" and hi.get("cell") is None
    assert hi["query"]["xM"] == pytest.approx(-5643436.98, abs=0.02)
    out = await call_ok(server, "daymet_locate_cell", {"lat": 0.0, "lon": 0.0})
    assert out["inCoverage"] is False and out.get("region") is None and out.get("cell") is None


async def test_locate_bad_arguments(server: DaymetServer) -> None:
    err = await call_err(
        server, "daymet_locate_cell", {"lat": 1, "lon": 2, "bogus": 3}, code="invalid_argument"
    )
    assert err["details"]["validArguments"] == ["lat", "lon"]
    await call_err(server, "daymet_locate_cell", {"lat": 91, "lon": 0}, code="invalid_argument")
    await call_err(server, "daymet_locate_cell", {"lat": 10}, code="invalid_argument")


async def test_unknown_tool(server: DaymetServer) -> None:
    await call_err(server, "daymet_nope", {}, code="unknown_tool")


async def test_citation_defaults(server: DaymetServer) -> None:
    out = await call_ok(
        server, "daymet_get_citation", {"accessed_on": "2026-11-15", "variables": ["prcp"]}
    )
    roles = [(c["role"], c["requirement"], c["doi"]) for c in out["citations"]]
    assert roles == [
        ("dataset", "required", "10.3334/ORNLDAAC/2129"),
        ("tool", "required", "10.3334/ORNLDAAC/2361"),
        ("method", "recommended", "10.1038/s41597-021-00973-0"),
    ]
    assert out["accessedOn"] == "2026-11-15"
    assert out["citations"][0]["doiUrl"] == "https://doi.org/10.3334/ORNLDAAC/2129"
    assert "@" in out["citations"][0]["bibtex"]
    assert "Wilson" not in out["citations"][0]["text"]
    assert out["dataPolicyUrl"] == "https://daymet.ornl.gov/citations"
    # default variables are all seven, which include srad and vp: two more method papers
    full = await call_ok(server, "daymet_get_citation")
    assert len(full["citations"]) == 5


async def test_citation_variants(server: DaymetServer) -> None:
    out = await call_ok(
        server,
        "daymet_get_citation",
        {"variables": ["srad"], "access": ["earthdata"], "products": ["daily", "monthly"]},
    )
    dois = [c["doi"] for c in out["citations"]]
    assert "10.3334/ORNLDAAC/2361" not in dois  # no single-pixel tool citation
    assert "10.3334/ORNLDAAC/2131" in dois
    assert len([c for c in out["citations"] if c["role"] == "method"]) == 3
    bare = await call_ok(server, "daymet_get_citation", {"include_method_papers": False})
    assert all(c["role"] != "method" for c in bare["citations"])
