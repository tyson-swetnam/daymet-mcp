# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""EXPERIMENTAL Earthdata backend: Hyrax OPeNDAP index subsetting of daily granules.

Status [not run]: no credentialed request has been made. Without Earthdata Login every
gridded endpoint answers 302 -> 401 (RESEARCH.md, Research B §2-3). The URL form follows
``scripts/download_seaz_daymet.py`` in eemt; that Hyrax accepts ``Authorization: Bearer``
and that the granule's ``y``/``x`` indices equal the NA grid row/column are inferred. The
parser is tested only against a **synthetic** NetCDF-4 fixture. Needs the ``[grid]`` extra.
"""

from __future__ import annotations

import io
import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from daymet_mcp.daymet.catalog import COLLECTIONS, Region
from daymet_mcp.daymet.client import DaymetHttpClient
from daymet_mcp.errors import ToolError, UpstreamError

if TYPE_CHECKING:
    from daymet_mcp.context import UpstreamStats

ENDPOINT = "GET opendap.earthdata.nasa.gov/collections/{concept}/granules/{granule}.dap.nc4"
DAILY_CONCEPT = next(c.concept_id for c in COLLECTIONS if c.product == "daily")
FILL = -9999.0


def grid_extra_available() -> bool:
    try:
        import h5netcdf  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        return False
    return True


def require_grid_extra() -> None:
    if not grid_extra_available():
        raise ToolError(
            "feature_unavailable",
            "This needs the optional [grid] extra (numpy, h5netcdf).",
            details={"reason": "extra_missing"},
            hint="Install with: uv pip install 'daymet-mcp[grid]'.",
        )


def granule_ur(region: Region, variable: str, year: int) -> str:
    return f"Daymet_Daily_V4R1.daymet_v4_daily_{region}_{variable}_{year}.nc"


def subset_request(
    opendap_root: str,
    region: Region,
    variable: str,
    year: int,
    rows: tuple[int, int],
    cols: tuple[int, int],
) -> tuple[str, dict[str, str]]:
    """URL and DAP4 constraint for ``variable[time][y][x]`` index ranges (inclusive)."""
    url = f"{opendap_root.rstrip('/')}/{DAILY_CONCEPT}/granules/{granule_ur(region, variable, year)}.dap.nc4"
    ce = (
        f"/{variable}[0:1:364][{rows[0]}:1:{rows[1]}][{cols[0]}:1:{cols[1]}];"
        f"/y[{rows[0]}:1:{rows[1]}];/x[{cols[0]}:1:{cols[1]}]"
    )
    return url, {"dap4.ce": ce}


def read_subset(
    blob: bytes, variable: str
) -> tuple[list[list[list[float | None]]], list[float], list[float]]:
    """Parse a NetCDF-4 subset into ``values[time][row][col]`` plus y and x centres."""
    require_grid_extra()
    import h5netcdf
    import numpy as np

    try:
        with h5netcdf.File(io.BytesIO(blob), "r") as nc:
            var = nc.variables[variable]
            data = np.asarray(var[...], dtype="float64")
            fill = var.attrs.get("_FillValue", FILL)
            ys = [float(v) for v in np.asarray(nc.variables["y"][...]).ravel()]
            xs = [float(v) for v in np.asarray(nc.variables["x"][...]).ravel()]
    except (OSError, KeyError, ValueError) as exc:
        raise UpstreamError(
            "parse",
            f"NetCDF subset unreadable ({type(exc).__name__})",
            host="opendap.earthdata.nasa.gov",
        ) from None
    if data.ndim != 3:
        raise UpstreamError(
            "drift", "subset is not [time][y][x]", host="opendap.earthdata.nasa.gov"
        )
    fill_v = float(np.asarray(fill).ravel()[0])
    out: list[list[list[float | None]]] = []
    for t in range(data.shape[0]):
        plane: list[list[float | None]] = []
        for r in range(data.shape[1]):
            row: list[float | None] = []
            for c in range(data.shape[2]):
                v = float(data[t, r, c])
                row.append(None if (not math.isfinite(v) or v == fill_v) else v)
            plane.append(row)
        out.append(plane)
    return out, ys, xs


class EarthdataService:
    def __init__(self, client: DaymetHttpClient, opendap_root: str) -> None:
        self.client = client
        self.root = opendap_root

    async def daily_cube(
        self,
        region: Region,
        variable: str,
        year: int,
        rows: tuple[int, int],
        cols: tuple[int, int],
        expected_x: Sequence[float],
        expected_y: Sequence[float],
        stats: UpstreamStats,
    ) -> list[list[list[float | None]]]:
        url, params = subset_request(self.root, region, variable, year, rows, cols)
        response = await self.client.get(
            url, params=params, group="earthdata", stats=stats, endpoint=ENDPOINT, auth=True
        )
        values, ys, xs = read_subset(response.content, variable)
        if [round(v) for v in xs] != [round(v) for v in expected_x] or [round(v) for v in ys] != [
            round(v) for v in expected_y
        ]:
            raise UpstreamError(
                "drift",
                "subset cell centres differ from the computed grid",
                host="opendap.earthdata.nasa.gov",
                details={"drift": {"x": xs[:3], "y": ys[:3]}},
            )
        return values


def describe_backend(token: bool, transport: str, allow_http: bool) -> str:
    if not grid_extra_available():
        return "extra_missing"
    if transport == "http" and not allow_http:
        return "disabled_in_http_mode"
    return "configured" if token else "not_configured"


__all__: list[Any] = [
    "EarthdataService",
    "describe_backend",
    "granule_ur",
    "grid_extra_available",
    "read_subset",
    "require_grid_extra",
    "subset_request",
]
