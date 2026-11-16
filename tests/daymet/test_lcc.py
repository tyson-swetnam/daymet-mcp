# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Pure-Python LCC against values the single-pixel service reported (S1 ``grid.log``)."""

from __future__ import annotations

import random

import pytest
from hypothesis import given
from hypothesis import strategies as st

from daymet_mcp.daymet import lcc


def test_forward_matches_service_dem_centre() -> None:
    # single-pixel echo for (35.802997, -106.624036): -575071.13 -688303.76
    x, y = lcc.forward(35.802997, -106.624036)
    assert x == pytest.approx(-575071.13, abs=0.02)
    assert y == pytest.approx(-688303.76, abs=0.02)


def test_forward_matches_service_hawaii() -> None:
    # recorded fixture: "LCC": [-5643436.98, -258972.42]
    x, y = lcc.forward(21.3, -157.8)
    assert x == pytest.approx(-5643436.98, abs=0.02)
    assert y == pytest.approx(-258972.42, abs=0.02)


def test_dem_centre_cell() -> None:
    cell = lcc.cell_for_latlon(35.802997, -106.624036)
    assert (cell.col, cell.row) == (3985, 5672)
    assert (cell.x_centre, cell.y_centre) == (-575250.0, -688000.0)
    lat, lon = cell.centre_latlon()
    # the service's "loc" for the cell-centre query: 35.805702, -106.626365
    assert lat == pytest.approx(35.805702, abs=1e-6)
    assert lon == pytest.approx(-106.626365, abs=1e-6)
    assert cell.in_grid()


@pytest.mark.parametrize(
    ("x", "y", "col", "row"),
    [
        (-574770.0, -688000.0, 3985, 5672),  # +480 m east: same cell
        (-574730.0, -688000.0, 3986, 5672),  # +520 m east: neighbour
        (-575250.0, -687520.0, 3985, 5672),  # +480 m north: same cell
        (-575250.0, -687480.0, 3985, 5671),  # +520 m north: neighbour
        (-575700.0, -688450.0, 3985, 5672),  # -450/-450: same cell
    ],
)
def test_snap_edges_from_s1_probe(x: float, y: float, col: int, row: int) -> None:
    cell = lcc.snap(x, y)
    assert (cell.col, cell.row) == (col, row)


def test_grid_extent() -> None:
    assert not lcc.Cell(-1, 0).in_grid()
    assert not lcc.Cell(0, lcc.N_ROWS).in_grid()
    assert lcc.Cell(lcc.N_COLS - 1, lcc.N_ROWS - 1).in_grid()


@given(
    lat=st.floats(min_value=15.0, max_value=80.0),
    lon=st.floats(min_value=-178.0, max_value=-53.0),
)
def test_round_trip(lat: float, lon: float) -> None:
    x, y = lcc.forward(lat, lon)
    lat2, lon2 = lcc.inverse(x, y)
    assert lat2 == pytest.approx(lat, abs=1e-9)
    assert lon2 == pytest.approx(lon, abs=1e-9)


def test_against_pyproj() -> None:
    pyproj = pytest.importorskip("pyproj")
    tr = pyproj.Transformer.from_crs(
        "EPSG:4326",
        "+proj=lcc +lat_1=25 +lat_2=60 +lat_0=42.5 +lon_0=-100 +x_0=0 +y_0=0 +ellps=WGS84 "
        "+units=m +no_defs",
        always_xy=True,
    )
    rng = random.Random(20261115)
    for _ in range(500):
        lat = rng.uniform(14.1, 82.9)
        lon = rng.uniform(-178.1, -53.1)
        px, py = tr.transform(lon, lat)
        x, y = lcc.forward(lat, lon)
        assert abs(px - x) < 0.05 and abs(py - y) < 0.05, (lat, lon, px - x, py - y)
