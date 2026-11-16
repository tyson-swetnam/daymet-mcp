# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Pure-Python Lambert Conformal Conic for the Daymet grid (DESIGN.md §3.4, D12).

Ellipsoidal LCC with two standard parallels, after Snyder (1987), *Map Projections — A
Working Manual*, USGS Professional Paper 1395, eqs. 14-15, 15-9 to 15-11 (forward) and
14-18, 15-7 to 15-11 (inverse). Parameters are Daymet's:
``+proj=lcc +lat_1=25 +lat_2=60 +lat_0=42.5 +lon_0=-100 +x_0=0 +y_0=0 +ellps=WGS84``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

A = 6_378_137.0
INV_F = 298.257223563
_F = 1.0 / INV_F
E2 = 2 * _F - _F * _F
E = math.sqrt(E2)

LAT_1 = 25.0
LAT_2 = 60.0
LAT_0 = 42.5
LON_0 = -100.0

# North America grid, cell centres (DESIGN.md §3.4).
X_FIRST_CENTRE = -4_560_250.0
Y_FIRST_CENTRE = 4_984_000.0
STEP = 1000.0
N_COLS = 7814
N_ROWS = 8075


def _m(phi: float) -> float:
    return math.cos(phi) / math.sqrt(1.0 - E2 * math.sin(phi) ** 2)


def _t(phi: float) -> float:
    s = E * math.sin(phi)
    return float(math.tan(math.pi / 4 - phi / 2) / ((1 - s) / (1 + s)) ** (E / 2))


_PHI1 = math.radians(LAT_1)
_PHI2 = math.radians(LAT_2)
_PHI0 = math.radians(LAT_0)
_M1, _M2 = _m(_PHI1), _m(_PHI2)
_T0, _T1, _T2 = _t(_PHI0), _t(_PHI1), _t(_PHI2)
N = (math.log(_M1) - math.log(_M2)) / (math.log(_T1) - math.log(_T2))
F_ = _M1 / (N * _T1**N)
RHO0 = A * F_ * _T0**N


def forward(lat: float, lon: float) -> tuple[float, float]:
    """WGS84 lat/lon (degrees) -> Daymet LCC x, y (metres)."""
    phi = math.radians(lat)
    rho = A * F_ * _t(phi) ** N
    theta = N * math.radians(lon - LON_0)
    return rho * math.sin(theta), RHO0 - rho * math.cos(theta)


def inverse(x: float, y: float) -> tuple[float, float]:
    """Daymet LCC x, y (metres) -> WGS84 lat, lon (degrees)."""
    dy = RHO0 - y
    rho = math.copysign(math.hypot(x, dy), N)
    theta = math.atan2(x, dy) if N > 0 else math.atan2(-x, -dy)
    t = (rho / (A * F_)) ** (1.0 / N)
    phi = math.pi / 2 - 2 * math.atan(t)
    for _ in range(15):
        s = E * math.sin(phi)
        nxt = math.pi / 2 - 2 * math.atan(t * ((1 - s) / (1 + s)) ** (E / 2))
        if abs(nxt - phi) < 1e-12:
            phi = nxt
            break
        phi = nxt
    return math.degrees(phi), math.degrees(theta / N) + LON_0


@dataclass(frozen=True)
class Cell:
    col: int
    row: int

    @property
    def x_centre(self) -> float:
        return X_FIRST_CENTRE + STEP * self.col

    @property
    def y_centre(self) -> float:
        return Y_FIRST_CENTRE - STEP * self.row

    def centre_latlon(self) -> tuple[float, float]:
        return inverse(self.x_centre, self.y_centre)

    def in_grid(self) -> bool:
        return 0 <= self.col < N_COLS and 0 <= self.row < N_ROWS


def snap(x: float, y: float) -> Cell:
    """The NA grid cell containing LCC point (x, y); each cell spans ±500 m around its centre."""
    col = math.floor((x - (X_FIRST_CENTRE - STEP / 2)) / STEP)
    row = math.floor(((Y_FIRST_CENTRE + STEP / 2) - y) / STEP)
    return Cell(col=col, row=row)


def cell_for_latlon(lat: float, lon: float) -> Cell:
    x, y = forward(lat, lon)
    return snap(x, y)
