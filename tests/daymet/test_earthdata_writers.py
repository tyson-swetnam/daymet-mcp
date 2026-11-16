# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Experimental Earthdata backend (SYNTHETIC NetCDF fixture) and the file writers."""

from __future__ import annotations

from pathlib import Path

import pytest

from daymet_mcp.daymet.catalog import ESRI_WKT
from daymet_mcp.daymet.earthdata import (
    describe_backend,
    granule_ur,
    grid_extra_available,
    read_subset,
    subset_request,
)
from daymet_mcp.daymet.writers import aaigrid_text, csv_text, netcdf_bytes, prj_text, write_file
from daymet_mcp.errors import UpstreamError
from tests.fixture_router import FIXTURES

SYNTHETIC = FIXTURES / "synthetic" / "opendap_tmax_2020_3x3.nc4"
needs_grid = pytest.mark.skipif(not grid_extra_available(), reason="[grid] extra not installed")


def test_subset_request() -> None:
    url, params = subset_request(
        "https://opendap.earthdata.nasa.gov/collections",
        "na",
        "tmax",
        2020,
        (5671, 5673),
        (3984, 3986),
    )
    assert url == (
        "https://opendap.earthdata.nasa.gov/collections/C2532426483-ORNL_CLOUD/granules/"
        "Daymet_Daily_V4R1.daymet_v4_daily_na_tmax_2020.nc.dap.nc4"
    )
    assert params == {
        "dap4.ce": "/tmax[0:1:364][5671:1:5673][3984:1:3986];/y[5671:1:5673];/x[3984:1:3986]"
    }
    assert granule_ur("hi", "prcp", 1999) == "Daymet_Daily_V4R1.daymet_v4_daily_hi_prcp_1999.nc"


@needs_grid
def test_read_synthetic_subset() -> None:
    values, ys, xs = read_subset(SYNTHETIC.read_bytes(), "tmax")
    assert len(values) == 365 and len(values[0]) == 3 and len(values[0][0]) == 3
    assert xs == [-576250.0, -575250.0, -574250.0]
    assert ys == [-687000.0, -688000.0, -689000.0]
    assert values[0][2][2] is None  # the one fill value
    assert values[1][0][0] == pytest.approx(10.01, abs=1e-5)
    assert values[0][1][2] == pytest.approx(11.2, abs=1e-5)


@needs_grid
def test_read_subset_errors() -> None:
    with pytest.raises(UpstreamError) as info:
        read_subset(b"not netcdf", "tmax")
    assert info.value.kind == "parse"
    with pytest.raises(UpstreamError):
        read_subset(SYNTHETIC.read_bytes(), "prcp")


def test_describe_backend() -> None:
    if not grid_extra_available():
        assert describe_backend(True, "stdio", False) == "extra_missing"
        return
    assert describe_backend(False, "stdio", False) == "not_configured"
    assert describe_backend(True, "stdio", False) == "configured"
    assert describe_backend(True, "http", False) == "disabled_in_http_mode"
    assert describe_backend(True, "http", True) == "configured"


def test_aaigrid_text() -> None:
    text = aaigrid_text([[1.0, None], [2.5, 3.25]], [-575250.0, -574250.0], [-688000.0, -689000.0])
    lines = text.splitlines()
    assert lines[:6] == [
        "ncols 2",
        "nrows 2",
        "xllcorner -575750.0",
        "yllcorner -689500.0",
        "cellsize 1000",
        "NODATA_value -9999",
    ]
    assert lines[6] == "1.0 -9999" and lines[7] == "2.5 3.25"
    assert prj_text().strip() == ESRI_WKT


def test_csv_and_write_file(tmp_path: Path) -> None:
    text = csv_text([{"a": 1, "b": None}], ["a", "b"])
    assert text == "a,b\n1,\n"
    nbytes, digest = write_file(tmp_path / "x.csv", text)
    assert nbytes == len(text) and len(digest) == 64
    assert (tmp_path / "x.csv").read_text() == text
    assert not list(tmp_path.glob("*.part"))


@needs_grid
def test_netcdf_round_trip() -> None:
    blob = netcdf_bytes(
        "tmax",
        [[[1.0, None]], [[2.0, 3.0]]],
        ["2020-01", "2020-02"],
        [-575250.0, -574250.0],
        [-688000.0],
        {"units": "degC"},
    )
    values, ys, xs = read_subset(blob, "tmax")
    assert values == [[[1.0, None]], [[2.0, 3.0]]]
    assert ys == [-688000.0] and xs == [-575250.0, -574250.0]
