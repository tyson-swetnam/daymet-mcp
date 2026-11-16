#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Build the SYNTHETIC NetCDF-4 fixture for the experimental Earthdata backend.

No Earthdata subset can be recorded without credentials (every gridded endpoint answers
302 -> 401), so ``tests/fixtures/synthetic/opendap_tmax_2020_3x3.nc4`` is hand-built: the
3x3 cells around the EEMT sample DEM cell (cols 3984-3986, rows 5671-5673), 365 days of
``tmax`` = 10 + 0.01*day + row_offset + 0.1*col_offset (degC), float32, _FillValue -9999.
It is NOT Daymet data. The manifest entry is marked ``origin: synthetic``.

Usage: uv run --extra grid python scripts/make_synthetic_netcdf.py
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import h5netcdf
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures" / "synthetic" / "opendap_tmax_2020_3x3.nc4"
COLS, ROWS = (3984, 3986), (5671, 5673)


def build() -> bytes:
    xs = np.array([-4560250.0 + 1000.0 * c for c in range(COLS[0], COLS[1] + 1)])
    ys = np.array([4984000.0 - 1000.0 * r for r in range(ROWS[0], ROWS[1] + 1)])
    t = np.arange(365, dtype="float64")
    data = np.empty((365, 3, 3), dtype="float32")
    for r in range(3):
        for c in range(3):
            data[:, r, c] = 10.0 + 0.01 * t + r + 0.1 * c
    data[0, 2, 2] = -9999.0  # one fill value to exercise null handling
    buf = io.BytesIO()
    with h5netcdf.File(buf, "w") as nc:
        nc.attrs["title"] = "SYNTHETIC test fixture for daymet-mcp (not Daymet data)"
        nc.dimensions = {"time": 365, "y": 3, "x": 3}
        nc.create_variable("x", ("x",), "f8")[...] = xs
        nc.create_variable("y", ("y",), "f8")[...] = ys
        nc.create_variable("time", ("time",), "f8")[...] = t + 0.5
        v = nc.create_variable("tmax", ("time", "y", "x"), "f4", fillvalue=np.float32(-9999.0))
        v[...] = data
        v.attrs["units"] = "degrees C"
    return buf.getvalue()


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT))
    from daymet_mcp.daymet.earthdata import subset_request
    from scripts.record_fixtures import fixture_key

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build())
    url, params = subset_request(
        "https://opendap.earthdata.nasa.gov/collections", "na", "tmax", 2020, ROWS, COLS
    )
    manifest_path = ROOT / "tests" / "fixtures" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = [e for e in manifest["fixtures"] if e.get("origin") != "synthetic"]
    entries.append(
        {
            "key": fixture_key("GET", url, params),
            "file": str(OUT.relative_to(OUT.parents[1])),
            "status": 200,
            "contentType": "application/x-netcdf4",
            "transform": "hand-built; see scripts/make_synthetic_netcdf.py",
            "origin": "synthetic",
            "recordedOn": None,
        }
    )
    manifest["fixtures"] = entries
    manifest_path.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
