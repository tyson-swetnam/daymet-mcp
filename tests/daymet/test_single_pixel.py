# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Single-pixel parser and the guards against upstream silent failures (D6)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from daymet_mcp.context import UpstreamStats
from daymet_mcp.daymet.cache import TTLCache
from daymet_mcp.daymet.calendar import yday_to_date
from daymet_mcp.daymet.client import DaymetHttpClient
from daymet_mcp.daymet.ratelimit import RateLimiter
from daymet_mcp.daymet.single_pixel import (
    SinglePixelService,
    location_for,
    parse_elevation,
    parse_response,
)
from daymet_mcp.errors import UpstreamError
from tests.conftest import FakeSleep
from tests.fixture_router import DEM_CENTRE, HAWAII, FixtureRouter, fixture_json

URL = "https://daymet.ornl.gov/single-pixel/api/data"


def test_parse_leap_year_fixture() -> None:
    body = fixture_json("pixel_dem_centre_2020")
    header, by_year, ydays = parse_response(body, expected_years=[2020])
    assert list(by_year) == [2020]
    assert len(ydays) == 365 and ydays[0] == 1 and ydays[-1] == 365
    # Leap year: Feb 29 (yday 60) present, Dec 31 absent (yday 365 = Dec 30).
    assert yday_to_date(2020, ydays[59]).isoformat() == "2020-02-29"
    assert yday_to_date(2020, ydays[-1]).isoformat() == "2020-12-30"
    assert header["tile"] == "11197"
    assert header["elevationM"] == 2545.0
    assert header["lccX"] == pytest.approx(-575250.0)
    assert set(by_year[2020]) == {"dayl", "prcp", "srad", "swe", "tmax", "tmin", "vp"}
    assert all(len(v) == 365 for v in by_year[2020].values())
    # S1 centre_2020.csv row 1: 2020,1,34645.92,0.00,317.07,2.64,-13.57,214.50
    first = {k: round(v[0] or 0.0, 2) for k, v in by_year[2020].items()}
    assert first["dayl"] == 34645.92 and first["srad"] == 317.07 and first["vp"] == 214.5


def test_parse_hawaii_fixture() -> None:
    header, by_year, _ = parse_response(fixture_json("pixel_hawaii_2020"), expected_years=[2020])
    assert header["tile"] == "9912" and header["elevationM"] == 176.0
    assert len(by_year[2020]["prcp"]) == 365


def test_unpublished_year_guard() -> None:
    # Asking for 2026 returned the whole record with HTTP 200 (truncated in the fixture).
    body = fixture_json("pixel_unpublished_year")
    with pytest.raises(UpstreamError) as info:
        parse_response(body, expected_years=[2026])
    assert info.value.kind == "drift"
    assert info.value.details["drift"]["expectedYears"] == [2026]
    assert info.value.details["drift"]["returnedYears"] == [1980, 1981]


def test_row_count_guard() -> None:
    body = copy.deepcopy(fixture_json("pixel_dem_centre_2020"))
    body["data"] = {k: v[:-1] for k, v in body["data"].items()}
    with pytest.raises(UpstreamError, match="row counts"):
        parse_response(body, expected_years=[2020])
    with pytest.raises(UpstreamError, match="row count"):
        parse_response(fixture_json("pixel_dem_centre_2020"), expected_rows=2)


def test_units_never_relabelled() -> None:
    body = copy.deepcopy(fixture_json("pixel_dem_centre_2020"))
    body["data"]["vp (hPa)"] = body["data"].pop("vp (Pa)")
    with pytest.raises(UpstreamError) as info:
        parse_response(body, expected_years=[2020])
    assert info.value.kind == "drift"
    assert "vp (Pa)" in info.value.details["drift"]["missingColumns"]


@pytest.mark.parametrize(
    ("mutate", "kind"),
    [
        (lambda b: b.pop("citation"), "drift"),
        (lambda b: b.__setitem__("citation", "Some other DOI 10.1/x"), "drift"),
        (lambda b: b.__setitem__("data", []), "drift"),
    ],
)
def test_other_drift(mutate: Any, kind: str) -> None:
    body = copy.deepcopy(fixture_json("pixel_dem_centre_2020"))
    mutate(body)
    with pytest.raises(UpstreamError) as info:
        parse_response(body, expected_years=[2020])
    assert info.value.kind == kind


def test_not_an_object() -> None:
    with pytest.raises(UpstreamError) as info:
        parse_response([1, 2])
    assert info.value.kind == "parse"


def test_parse_elevation() -> None:
    assert parse_elevation("2545 meters") == 2545.0
    assert parse_elevation("176 m") == 176.0
    assert parse_elevation(12) == 12.0
    assert parse_elevation(None) is None
    assert parse_elevation("n/a") is None


def test_location_for_snaps_na_to_cell_centre() -> None:
    where = location_for(*DEM_CENTRE, "na")
    assert where.cell is not None and (where.cell.col, where.cell.row) == (3985, 5672)
    assert (where.query_lat, where.query_lon) == (35.805702, -106.626365)
    assert where.cache_prefix == "pixel:na:c3985:r5672"
    hi = location_for(*HAWAII, "hi")
    assert hi.cell is None and (hi.query_lat, hi.query_lon) == HAWAII


async def test_service_caches_by_cell(router: FixtureRouter, fake_sleep: FakeSleep) -> None:
    client = DaymetHttpClient(
        limiter=RateLimiter(sleep=fake_sleep), transport=router.transport, sleep=fake_sleep
    )
    service = SinglePixelService(
        client, TTLCache(max_entries=100, ttl_s=3600, stale_if_error_s=0), URL
    )
    try:
        stats = UpstreamStats()
        data = await service.get_years(location_for(*DEM_CENTRE, "na"), [2020], stats)
        assert stats.requests == 1 and stats.cache_hits == 0
        assert len(data[2020].values["prcp"]) == 365
        # A different point inside the same cell is served from the cache.
        stats2 = UpstreamStats()
        await service.get_years(location_for(35.8049, -106.6250, "na"), [2020], stats2)
        assert stats2.requests == 0 and stats2.cache_hits == 1
        assert router.count("single-pixel") == 1
        header, rows = await service.get_window(
            35.805702, -106.626365, *_ping_window(), UpstreamStats()
        )
        assert rows == 2 and header["tile"] == "11197"
    finally:
        await client.aclose()


def _ping_window() -> tuple[Any, Any]:
    from daymet_mcp.tools.core import PROBE_END, PROBE_START

    return PROBE_START, PROBE_END
