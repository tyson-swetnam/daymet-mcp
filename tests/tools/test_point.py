# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""daymet_get_point_daily and daymet_get_point_summary on recorded 2020 fixtures."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from datetime import date, timedelta

import pytest

from daymet_mcp.config import Config
from daymet_mcp.models.point import PointDailyOutput
from daymet_mcp.registry import fit_to_budget, json_size
from daymet_mcp.server import DaymetServer
from tests.fixture_router import DEM_CENTRE, HAWAII, OCEAN, FixtureRouter, fixture_json
from tests.helpers import call_err, call_ok

LAT, LON = DEM_CENTRE


def _fixture_prcp() -> list[float]:
    return [float(v) for v in fixture_json("pixel_dem_centre_2020")["data"]["prcp (mm/day)"]]


async def test_daily_full_leap_year(server: DaymetServer, router: FixtureRouter) -> None:
    out = await call_ok(server, "daymet_get_point_daily", {"lat": LAT, "lon": LON, "years": [2020]})
    t = out["time"]
    assert len(t["date"]) == 365 and t["date"][0] == "2020-01-01"
    assert "2020-02-29" in t["date"] and "2020-12-31" not in t["date"]
    assert t["date"][-1] == "2020-12-30" and t["yday"][-1] == 365
    assert set(out["series"]) == {"dayl", "prcp", "srad", "swe", "tmax", "tmin", "vp"}
    assert out["series"]["prcp"]["units"] == "mm/day"
    assert out["series"]["vp"]["units"] == "Pa"
    assert out["series"]["srad"]["units"] == "W/m2"
    assert out["series"]["vp"]["values"][0] == 214.5  # S1 centre_2020.csv row 1
    loc = out["location"]
    assert loc["cell"] == {"col": 3985, "row": 5672, "xCentreM": -575250.0, "yCentreM": -688000.0}
    assert loc["tile"] == "11197" and loc["elevationM"] == 2545.0
    assert out["doi"] == "10.3334/ORNLDAAC/2129" and out["dataVersion"] == "4 R1"
    assert out["page"]["truncated"] is False and out["page"]["total"] == 365
    assert any("Feb 29" in n for n in out["notes"])
    assert out["nextSteps"][-1].startswith("daymet_get_citation")
    assert out["source"]["via"] == "single-pixel" and out["source"]["cached"] is False
    assert router.count("single-pixel") == 1


async def test_daily_variable_filter_paging_and_cache(
    server: DaymetServer, router: FixtureRouter
) -> None:
    args = {"lat": LAT, "lon": LON, "years": [2020], "variables": ["prcp"], "limit": 100}
    first = await call_ok(server, "daymet_get_point_daily", args)
    assert list(first["series"]) == ["prcp"]
    assert first["page"] == {
        "total": 365,
        "returned": 100,
        "offset": 0,
        "limit": 100,
        "truncated": True,
        "nextOffset": 100,
        "truncatedReason": "limit",
    }
    second = await call_ok(server, "daymet_get_point_daily", {**args, "offset": 300})
    assert second["page"]["returned"] == 65 and second["page"]["truncated"] is False
    assert second["time"]["date"][0] == (date(2020, 1, 1) + timedelta(days=300)).isoformat()
    assert second["source"]["cached"] is True
    assert router.count("single-pixel") == 1


async def test_daily_date_window(server: DaymetServer) -> None:
    out = await call_ok(
        server,
        "daymet_get_point_daily",
        {"lat": LAT, "lon": LON, "start_date": "2020-12-29", "end_date": "2020-12-30"},
    )
    assert out["time"]["date"] == ["2020-12-29", "2020-12-30"]
    assert out["time"]["yday"] == [364, 365]


@pytest.mark.parametrize(
    ("args", "reason_or_fragment"),
    [
        ({"start_date": "2020-12-01", "end_date": "2020-12-31"}, "not_in_daymet_calendar"),
        ({"years": [2030]}, "year_out_of_range"),
        ({"years": [1979]}, "years.0"),
        ({"years": [2020], "start_date": "2020-01-01", "end_date": "2020-01-02"}, "exactly one"),
        ({"start_date": "2020-01-01"}, "together"),
        ({"years": [2020], "variables": ["foo"]}, "variables.0"),
    ],
)
async def test_daily_invalid(
    server: DaymetServer, args: dict[str, object], reason_or_fragment: str
) -> None:
    err = await call_err(
        server, "daymet_get_point_daily", {"lat": LAT, "lon": LON, **args}, code="invalid_argument"
    )
    assert reason_or_fragment in json.dumps(err)


async def test_daily_hawaii(server: DaymetServer) -> None:
    out = await call_ok(
        server, "daymet_get_point_daily", {"lat": HAWAII[0], "lon": HAWAII[1], "years": [2020]}
    )
    assert out["location"]["region"] == "hi" and out["location"].get("cell") is None
    assert out["location"]["tile"] == "9912" and len(out["time"]["date"]) == 365


async def test_daily_off_grid_and_out_of_coverage(server: DaymetServer) -> None:
    err = await call_err(
        server,
        "daymet_get_point_daily",
        {"lat": OCEAN[0], "lon": OCEAN[1], "years": [2020]},
        code="not_found",
    )
    assert err["details"]["reason"] == "off_grid"
    err = await call_err(
        server,
        "daymet_get_point_daily",
        {"lat": 0.0, "lon": 0.0, "years": [2020]},
        code="invalid_argument",
    )
    assert err["details"]["reason"] == "out_of_coverage"


async def test_too_many_years(
    make_server: Callable[..., DaymetServer], config: Config, router: FixtureRouter
) -> None:
    cfg = config.model_copy(deep=True)
    cfg.limits.max_years_per_point = 1
    err = await call_err(
        make_server(config=cfg),
        "daymet_get_point_summary",
        {"lat": LAT, "lon": LON, "period": "annual", "start_year": 2019, "end_year": 2020},
        code="query_too_large",
    )
    assert err["details"]["limitName"] == "max_years_per_point"
    assert err["details"]["requested"] == 2
    assert router.calls == []  # refused before any upstream request


def test_budget_trim() -> None:
    payload = {
        "location": {},
        "time": {"date": ["d"] * 400, "year": [2020] * 400, "yday": [1] * 400},
        "series": {"prcp": {"units": "mm/day", "values": [1.25] * 400}},
        "page": {"total": 400, "returned": 400, "offset": 0, "limit": 400, "truncated": False},
        "nextSteps": [],
    }
    out = fit_to_budget(payload, PointDailyOutput, 2000)
    assert json_size(out) <= 2000
    kept = out["page"]["returned"]
    assert 0 < kept < 400 and out["page"]["truncatedReason"] == "budget"
    assert out["page"]["nextOffset"] == kept and len(out["time"]["date"]) == kept
    assert "offset=" in out["nextSteps"][0]


async def test_summary_monthly_prcp_is_total(server: DaymetServer, router: FixtureRouter) -> None:
    out = await call_ok(
        server,
        "daymet_get_point_summary",
        {
            "lat": LAT,
            "lon": LON,
            "period": "monthly",
            "start_year": 2020,
            "end_year": 2020,
            "variables": ["prcp", "tmax"],
        },
    )
    prcp = out["series"]["prcp"]
    assert prcp["aggregation"] == "sum" and prcp["units"] == "mm/month"
    assert prcp["dailyUnits"] == "mm/day" and prcp["fieldLabel"] == "prcp_monthly_total_mm"
    assert out["series"]["tmax"]["aggregation"] == "mean"
    assert out["series"]["tmax"]["fieldLabel"] == "tmax_monthly_mean_degC"
    daily = _fixture_prcp()
    by_month: dict[int, float] = {}
    for i, p in enumerate(daily):
        m = (date(2020, 1, 1) + timedelta(days=i)).month
        by_month[m] = by_month.get(m, 0.0) + p
    assert prcp["values"] == [round(by_month[m], 3) for m in range(1, 13)]
    assert math.fsum(prcp["values"]) == pytest.approx(math.fsum(daily), abs=6e-3)
    dec = out["periods"][11]
    assert dec == {
        "label": "2020-12",
        "year": 2020,
        "month": 12,
        "dayCount": 30,
        "complete": True,
        "firstDate": "2020-12-01",
        "lastDate": "2020-12-30",
    }
    assert any("30 days" in n for n in out["notes"])
    assert any("prcp_monthly_total_mm" in d and "2129" in d for d in out["source"]["derived"])
    assert router.count("single-pixel") == 1


async def test_summary_annual_months_and_overrides(server: DaymetServer) -> None:
    annual = await call_ok(
        server,
        "daymet_get_point_summary",
        {"lat": LAT, "lon": LON, "period": "annual", "start_year": 2020, "end_year": 2020},
    )
    assert annual["series"]["prcp"]["units"] == "mm/year"
    assert annual["series"]["prcp"]["values"] == [round(math.fsum(_fixture_prcp()), 3)]
    assert annual["periods"][0]["dayCount"] == 365
    srad = annual["series"]["srad"]
    assert srad["units"] == "W/m2" and "not a 24-h mean" in srad["definition"]
    some = await call_ok(
        server,
        "daymet_get_point_summary",
        {
            "lat": LAT,
            "lon": LON,
            "period": "monthly",
            "start_year": 2020,
            "end_year": 2020,
            "months": [2, 12],
            "variables": ["swe", "srad"],
            "aggregation_overrides": {"swe": "last", "srad": "total"},
        },
    )
    assert [p["label"] for p in some["periods"]] == ["2020-02", "2020-12"]
    assert some["series"]["swe"]["fieldLabel"] == "swe_monthly_last_kg_m2"
    assert some["series"]["srad"]["units"] == "MJ/m2/month"


@pytest.mark.parametrize(
    "extra",
    [
        {"aggregation_overrides": {"prcp": "mean"}},
        {"aggregation_overrides": {"swe": "sum"}},
        {"period": "annual", "months": [1]},
        {"months": [13]},
        {"end_year": 2019},
    ],
)
async def test_summary_invalid(server: DaymetServer, extra: dict[str, object]) -> None:
    args = {"lat": LAT, "lon": LON, "period": "monthly", "start_year": 2020, "end_year": 2020}
    await call_err(server, "daymet_get_point_summary", {**args, **extra}, code="invalid_argument")
