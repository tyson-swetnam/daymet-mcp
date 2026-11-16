# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""daymet_get_area and daymet_download_area (3x3 single-pixel mosaic fixture; the Earthdata
backend runs only against the SYNTHETIC NetCDF fixture)."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path

import pytest

from daymet_mcp.config import Config
from daymet_mcp.daymet.earthdata import grid_extra_available
from daymet_mcp.server import DaymetServer
from tests.fixture_router import DEM_CENTRE, MOSAIC_BBOX, TEST_TOKEN, FixtureRouter, fixture_json
from tests.helpers import call_err, call_ok

BASE = {"bbox": MOSAIC_BBOX, "start_year": 2020, "end_year": 2020}
BIG_BBOX = {"west": -106.75, "south": 35.70, "east": -106.50, "north": 35.90}
needs_grid = pytest.mark.skipif(not grid_extra_available(), reason="[grid] extra not installed")


async def test_area_monthly_prcp(server: DaymetServer, router: FixtureRouter) -> None:
    out = await call_ok(
        server,
        "daymet_get_area",
        {**BASE, "variables": ["prcp"], "temporal": "monthly", "include_elevation": True},
    )
    grid = out["grid"]
    assert grid["colRange"] == [3984, 3986] and grid["rowRange"] == [5671, 5673]
    assert grid["shape"] == {"time": 12, "rows": 3, "cols": 3}
    assert grid["xCentresM"] == [-576250.0, -575250.0, -574250.0]
    assert grid["yCentresM"] == [-687000.0, -688000.0, -689000.0]
    assert out["cellsRequested"] == 9 and out["backend"] == "single-pixel-mosaic"
    s = out["series"]["prcp"]
    assert s["aggregation"] == "sum" and s["units"] == "mm/month"
    assert s["fieldLabel"] == "prcp_monthly_total_mm"
    assert out["time"]["labels"][11] == "2020-12" and out["time"]["dayCount"][11] == 30
    # centre cell equals the point summary of the DEM centre
    daily = [float(v) for v in fixture_json("pixel_dem_centre_2020")["data"]["prcp (mm/day)"]]
    centre_year = math.fsum(s["values"][t][1][1] for t in range(12))
    assert centre_year == pytest.approx(math.fsum(daily), abs=6e-3)
    assert out["elevationM"][1][1] == 2545.0
    assert out["source"]["via"] == "single-pixel-mosaic" and out["source"]["derived"]
    assert router.count("single-pixel") == 9
    # all nine cells are now cached
    await call_ok(server, "daymet_get_area", {**BASE, "variables": ["tmax"], "temporal": "annual"})
    assert router.count("single-pixel") == 9


async def test_area_daily_paged(server: DaymetServer) -> None:
    out = await call_ok(
        server, "daymet_get_area", {**BASE, "variables": ["tmin"], "temporal": "daily", "limit": 31}
    )
    assert len(out["time"]["labels"]) == 31 and out["page"]["nextOffset"] == 31
    assert out["series"]["tmin"]["aggregation"] == "none (daily)"
    assert out["series"]["tmin"]["units"] == "degC"
    assert out["nextSteps"][0].startswith("Use temporal='monthly'")


async def test_area_needs_token_when_large(server: DaymetServer) -> None:
    err = await call_err(
        server,
        "daymet_get_area",
        {
            "bbox": BIG_BBOX,
            "start_year": 2020,
            "end_year": 2020,
            "variables": ["prcp"],
            "temporal": "annual",
        },
        code="auth_required",
    )
    assert err["details"]["reason"] == "token_missing"
    assert "DAYMET_MCP_EARTHDATA__TOKEN" in err["message"]
    err = await call_err(
        server,
        "daymet_get_area",
        {
            "bbox": BIG_BBOX,
            "start_year": 2020,
            "end_year": 2020,
            "variables": ["prcp"],
            "temporal": "annual",
            "backend": "single_pixel",
        },
        code="query_too_large",
    )
    assert err["details"]["limitName"] == "pixel_mosaic_max_cells"
    assert err["details"]["limit"] == 121 and err["details"]["requested"] > 121


async def test_area_http_mode_refuses_earthdata(make_server: Callable[..., DaymetServer]) -> None:
    server = make_server(transport="http", token=TEST_TOKEN)
    await call_err(
        server,
        "daymet_get_area",
        {
            "bbox": BIG_BBOX,
            "start_year": 2020,
            "end_year": 2020,
            "variables": ["prcp"],
            "temporal": "annual",
        },
        code="not_available_in_http_mode",
    )


@pytest.mark.parametrize(
    ("bbox", "code"),
    [
        ({"west": -158.0, "south": 21.2, "east": -157.9, "north": 21.4}, "feature_unavailable"),
        ({"west": 10.0, "south": 10.0, "east": 11.0, "north": 11.0}, "invalid_argument"),
        (
            {"west": -106.6301, "south": 35.8051, "east": -106.6300, "north": 35.8052},
            "invalid_argument",
        ),
        ({"west": -106.0, "south": 35.0, "east": -107.0, "north": 36.0}, "invalid_argument"),
    ],
)
async def test_area_bbox_errors(server: DaymetServer, bbox: dict[str, float], code: str) -> None:
    await call_err(
        server,
        "daymet_get_area",
        {
            "bbox": bbox,
            "start_year": 2020,
            "end_year": 2020,
            "variables": ["prcp"],
            "temporal": "annual",
        },
        code=code,
    )


@needs_grid
async def test_area_earthdata_synthetic(
    make_server: Callable[..., DaymetServer], router: FixtureRouter
) -> None:
    server = make_server(token=TEST_TOKEN)
    out = await call_ok(
        server,
        "daymet_get_area",
        {
            **BASE,
            "variables": ["tmax"],
            "temporal": "annual",
            "backend": "earthdata",
            "include_elevation": True,
        },
    )
    assert out["backend"] == "earthdata-opendap"
    values = out["series"]["tmax"]["values"][0]
    # synthetic: tmax = 10 + 0.01*day + row + 0.1*col; annual mean over 365 days
    assert values[0][0] == pytest.approx(10 + 0.01 * 182, abs=1e-3)
    assert values[2][2] is None  # one fill value -> incomplete -> null
    assert any("EXPERIMENTAL" in n for n in out["notes"])
    edl = [c for c in router.calls if "opendap" in c.key]
    assert edl and edl[0].headers.get("authorization") == f"Bearer {TEST_TOKEN}"
    assert all("authorization" not in c.headers for c in router.calls if "cmr." in c.key)


async def test_download_aaigrid(
    server: DaymetServer, config: Config, router: FixtureRouter
) -> None:
    args = {**BASE, "variables": ["prcp"], "temporal": "monthly", "include_elevation": True}
    out = await call_ok(server, "daymet_download_area", args)
    root = config.downloads.resolved_dir()
    directory = Path(out["directory"])
    assert directory.parent == root
    names = sorted(Path(f["path"]).name for f in out["files"])
    assert len(names) == 12 * 2 + 2
    assert "daymet_na_prcp_monthly_total_2020-12_c3984-3986_r5671-5673.asc" in names
    assert "daymet_na_elevation_c3984-3986_r5671-5673.asc" in names
    asc = (directory / "daymet_na_prcp_monthly_total_2020-01_c3984-3986_r5671-5673.asc").read_text()
    assert asc.splitlines()[:3] == ["ncols 3", "nrows 3", "xllcorner -576750.0"]
    manifest = json.loads(Path(out["manifestPath"]).read_text())
    assert manifest["aggregation"][0]["aggregation"] == "sum"
    assert manifest["aggregation"][0]["units"] == "mm/month"
    assert manifest["calendar"]["daysPerYear"] == 365
    assert "10.3334/ORNLDAAC/2129" in manifest["citations"][0]
    assert all(len(f["sha256"]) == 64 for f in out["files"])
    # deterministic names: refused without overwrite, identical content with it
    err = await call_err(server, "daymet_download_area", args, code="invalid_argument")
    assert err["details"]["reason"] == "files_exist"
    again = await call_ok(server, "daymet_download_area", {**args, "overwrite": True})
    assert [f["sha256"] for f in again["files"]] == [f["sha256"] for f in out["files"]]
    assert router.count("single-pixel") == 9


async def test_download_csv_and_subdir(server: DaymetServer) -> None:
    out = await call_ok(
        server,
        "daymet_download_area",
        {
            **BASE,
            "variables": ["tmax", "prcp"],
            "temporal": "annual",
            "format": "csv",
            "subdir": "site-a",
        },
    )
    assert Path(out["directory"]).name == "site-a"
    text = Path(out["files"][0]["path"]).read_text().splitlines()
    assert text[0].startswith("region,col,row,x_centre_m")
    assert len(text) == 1 + 2 * 9


async def test_download_path_safety(server: DaymetServer, config: Config, tmp_path: Path) -> None:
    root = config.downloads.resolved_dir()
    root.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside)
    args = {**BASE, "variables": ["prcp"], "temporal": "annual"}
    err = await call_err(server, "daymet_download_area", {**args, "subdir": "link"})
    assert err["details"]["reason"] == "symlink_refused"
    for bad in ("..", "."):
        err = await call_err(server, "daymet_download_area", {**args, "subdir": bad})
        assert err["details"]["reason"] == "path_outside_downloads_dir"
    await call_err(
        server, "daymet_download_area", {**args, "subdir": "a/b"}, code="invalid_argument"
    )
    assert list(outside.iterdir()) == []


async def test_download_not_over_http(http_server: DaymetServer) -> None:
    await call_err(
        http_server,
        "daymet_download_area",
        {**BASE, "variables": ["prcp"], "temporal": "annual"},
        code="not_available_in_http_mode",
    )


async def test_download_manifest_has_no_token(
    make_server: Callable[..., DaymetServer], config: Config
) -> None:
    server = make_server(token=TEST_TOKEN)
    out = await call_ok(
        server, "daymet_download_area", {**BASE, "variables": ["prcp"], "temporal": "annual"}
    )
    assert TEST_TOKEN not in Path(out["manifestPath"]).read_text()
    assert TEST_TOKEN not in json.dumps(out)


@needs_grid
async def test_download_netcdf(server: DaymetServer) -> None:
    from daymet_mcp.daymet.earthdata import read_subset

    out = await call_ok(
        server,
        "daymet_download_area",
        {**BASE, "variables": ["prcp"], "temporal": "monthly", "format": "netcdf"},
    )
    nc = [f for f in out["files"] if f["format"] == "netcdf"]
    assert len(nc) == 1
    values, ys, xs = read_subset(Path(nc[0]["path"]).read_bytes(), "prcp")
    assert len(values) == 12 and len(ys) == 3 and len(xs) == 3


def test_dem_centre_constant() -> None:
    assert DEM_CENTRE == (35.802997, -106.624036)
