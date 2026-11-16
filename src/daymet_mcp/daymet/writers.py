# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""File writers for ``daymet_download_area`` (DESIGN.md §4.7, D14).

* ``aaigrid`` — ESRI ASCII grid + ``.prj`` (Daymet LCC, ESRI WKT); GDAL-readable,
  no extra dependencies. ``xllcorner = min x centre - 500``, ``cellsize 1000``,
  ``NODATA_value -9999``; rows north to south.
* ``csv`` — one long table.
* ``netcdf`` — one file per variable and year; needs the ``[grid]`` extra.
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from daymet_mcp.daymet.catalog import ESRI_WKT, PROJ4

NODATA = -9999


def _fmt(v: float | None) -> str:
    return str(NODATA) if v is None else repr(round(float(v), 3))


def aaigrid_text(
    grid: Sequence[Sequence[float | None]], x_centres: Sequence[float], y_centres: Sequence[float]
) -> str:
    """ESRI ASCII grid text; ``grid[row][col]`` with row 0 = north."""
    lines = [
        f"ncols {len(x_centres)}",
        f"nrows {len(y_centres)}",
        f"xllcorner {min(x_centres) - 500:.1f}",
        f"yllcorner {min(y_centres) - 500:.1f}",
        "cellsize 1000",
        f"NODATA_value {NODATA}",
    ]
    lines += [" ".join(_fmt(v) for v in row) for row in grid]
    return "\n".join(lines) + "\n"


def prj_text() -> str:
    return ESRI_WKT + "\n"


def csv_text(rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in columns})
    return buf.getvalue()


def netcdf_bytes(
    variable: str,
    cube: Sequence[Sequence[Sequence[float | None]]],
    labels: Sequence[str],
    x_centres: Sequence[float],
    y_centres: Sequence[float],
    attrs: dict[str, str],
) -> bytes:
    """NetCDF-4 file with ``variable[time][y][x]`` (float32, fill -9999)."""
    from daymet_mcp.daymet.earthdata import require_grid_extra

    require_grid_extra()
    import h5netcdf
    import numpy as np

    data = np.array(
        [[[NODATA if v is None else v for v in row] for row in plane] for plane in cube],
        dtype="float32",
    )
    buf = io.BytesIO()
    with h5netcdf.File(buf, "w") as nc:
        nc.dimensions = {"time": len(labels), "y": len(y_centres), "x": len(x_centres)}
        nc.attrs["Conventions"] = "CF-1.8"
        nc.attrs["crs_proj4"] = PROJ4
        nc.attrs["crs_wkt"] = ESRI_WKT
        xv = nc.create_variable("x", ("x",), "f8")
        xv[...] = np.array(x_centres, dtype="float64")
        xv.attrs["units"] = "m"
        yv = nc.create_variable("y", ("y",), "f8")
        yv[...] = np.array(y_centres, dtype="float64")
        yv.attrs["units"] = "m"
        tv = nc.create_variable("time", ("time",), "i4")
        tv[...] = np.array([int(lab.replace("-", "")) for lab in labels], dtype="int32")
        tv.attrs["description"] = "period label as YYYY, YYYYMM or YYYYMMDD"
        var = nc.create_variable(variable, ("time", "y", "x"), "f4", fillvalue=np.float32(NODATA))
        var[...] = data
        for key, value in attrs.items():
            var.attrs[key] = value
    return buf.getvalue()


def write_file(path: Path, content: bytes | str) -> tuple[int, str]:
    """Write atomically; return (bytes, sha256)."""
    blob = content.encode("utf-8") if isinstance(content, str) else content
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(blob)
    tmp.replace(path)
    return len(blob), hashlib.sha256(blob).hexdigest()
