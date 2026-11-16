# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""daymet_get_area and daymet_download_area (3x3 single-pixel mosaic fixture; the Earthdata
backend runs only against the SYNTHETIC NetCDF fixture)."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path
from typing import Any

import anyio
import pytest

import daymet_mcp.tools.area as area_mod
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


HUGE_BBOX = {"west": -110.0, "south": 30.0, "east": -90.0, "north": 46.0}  # ~3.3M candidates
MID_BBOX = {"west": -107.8, "south": 34.8, "east": -105.2, "north": 36.8}  # 57,085 candidates


def _no_enumeration(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: object) -> None:
        raise AssertionError("cells were enumerated for a request that should be refused first")

    monkeypatch.setattr(area_mod, "enumerate_cells", boom)


@pytest.mark.parametrize(
    ("transport", "token"), [("http", None), ("http", TEST_TOKEN), ("stdio", None)]
)
async def test_huge_bbox_refused_before_planning(
    make_server: Callable[..., DaymetServer],
    router: FixtureRouter,
    monkeypatch: pytest.MonkeyPatch,
    transport: str,
    token: str | None,
) -> None:
    # Regression (protocol-security review): this bbox used to cost ~15-18 s of CPU on the
    # event loop before being refused; /healthz could not answer meanwhile.
    _no_enumeration(monkeypatch)
    server = make_server(transport=transport, token=token)
    t0 = time.monotonic()
    err = await call_err(
        server,
        "daymet_get_area",
        {**BASE, "bbox": HUGE_BBOX, "variables": ["prcp"], "temporal": "annual"},
        code="query_too_large",
    )
    assert time.monotonic() - t0 < 1.0
    assert err["details"]["limitName"] == "candidate_cells"
    assert err["details"]["limit"] == area_mod.PIXEL_RECT_FACTOR * 121
    assert err["details"]["requested"] > 3_000_000
    assert router.calls == []


async def test_huge_bbox_cap_follows_earthdata_limit_with_token(
    make_server: Callable[..., DaymetServer], monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_enumeration(monkeypatch)
    server = make_server(token=TEST_TOKEN)
    err = await call_err(
        server,
        "daymet_get_area",
        {**BASE, "bbox": HUGE_BBOX, "variables": ["prcp"], "temporal": "annual"},
        code="query_too_large",
    )
    # 25e6 values / 365 days = 68,493 cells, plus the one-cell margin of the rectangle
    assert 25_000_000 // 365 < err["details"]["limit"] < area_mod.MAX_CANDIDATE_CELLS


async def test_mid_bbox_without_token_says_what_is_missing(
    make_server: Callable[..., DaymetServer],
    router: FixtureRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Too big for single-pixel, small enough for Earthdata: the caller learns what would help.
    _no_enumeration(monkeypatch)
    args = {**BASE, "bbox": MID_BBOX, "variables": ["prcp"], "temporal": "annual"}
    err = await call_err(make_server(), "daymet_get_area", args, code="auth_required")
    assert err["details"]["reason"] == "token_missing"
    await call_err(
        make_server(transport="http"), "daymet_get_area", args, code="not_available_in_http_mode"
    )
    assert router.calls == []


async def test_explicit_earthdata_refused_without_planning(
    make_server: Callable[..., DaymetServer], monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_enumeration(monkeypatch)
    await call_err(
        make_server(transport="http", token=TEST_TOKEN),
        "daymet_get_area",
        {**BASE, "variables": ["prcp"], "temporal": "annual", "backend": "earthdata"},
        code="not_available_in_http_mode",
    )


async def test_cell_enumeration_runs_off_the_event_loop(
    server: DaymetServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = area_mod.enumerate_cells

    def slow(*a: Any) -> Any:
        time.sleep(0.6)  # stands in for a large, allowed enumeration
        return real(*a)

    monkeypatch.setattr(area_mod, "enumerate_cells", slow)
    stamps: list[float] = []

    async def ticker() -> None:
        for _ in range(20):
            stamps.append(time.monotonic())
            await anyio.sleep(0.05)

    async with anyio.create_task_group() as tg:
        tg.start_soon(ticker)
        await anyio.sleep(0.12)  # the ticker is running before the call starts
        await call_ok(
            server, "daymet_get_area", {**BASE, "variables": ["prcp"], "temporal": "annual"}
        )
    gaps = [b - a for a, b in pairwise(stamps)]
    assert max(gaps) < 0.3  # the loop kept running during the 0.6 s enumeration


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
