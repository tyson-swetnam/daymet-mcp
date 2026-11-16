#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Record (``record``) or verify (``check``) the hermetic test fixtures.

``record`` sends a small, fixed set of real GETs (single pixels, one 3x3 mosaic, 2-day
windows, three CMR lookups, the unauthenticated Earthdata redirect chain) with the generic
daymet-mcp User-Agent and **no credentials**, shrinks/scrubs them, and writes
``tests/fixtures/<host>/<name>_<status>_<hash>.json`` plus ``tests/fixtures/manifest.json``.
The request parameters are built with the package's own helpers so that they are exactly
what the server sends.

``check`` (run in CI) verifies sizes (each file <= 64 KB, total <= 1 MB), allow-listed hosts,
that no stored header carries credentials, and that every manifest entry has a file.

Usage: uv run python scripts/record_fixtures.py record|check
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
MANIFEST = FIX / "manifest.json"
MAX_FILE = 64 * 1024
MAX_TOTAL = 1024 * 1024
KEEP_HEADERS = {"content-type", "location", "www-authenticate", "retry-after"}
CREDENTIAL_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-token"}

DEM_CENTRE = (35.802997, -106.624036)  # EEMT sample DEM (S1 grid.log)
HAWAII = (21.3, -157.8)
OCEAN = (30.0, -130.0)


def fixture_key(method: str, url: str, params: dict[str, Any] | None) -> str:
    parts = urlsplit(url)
    query = urlencode(sorted((params or {}).items())) if params else parts.query
    base = f"{method} {parts.hostname}{parts.path}"
    return f"{base}?{query}" if query else base


def _file_for(key: str, status: int, name: str) -> Path:
    host = urlsplit("https://" + key.split(" ", 1)[1]).hostname or "unknown"
    digest = hashlib.sha256(key.encode()).hexdigest()[:10]
    return FIX / host / f"{name}_{status}_{digest}.json"


def record() -> None:
    import httpx

    sys.path.insert(0, str(ROOT / "src"))
    from daymet_mcp import USER_AGENT
    from daymet_mcp.daymet import lcc
    from daymet_mcp.daymet.catalog import COLLECTIONS
    from daymet_mcp.daymet.earthdata import subset_request
    from daymet_mcp.daymet.single_pixel import ALL_VARS, location_for

    sp = "https://daymet.ornl.gov/single-pixel/api/data"
    today = dt.date.today().isoformat()
    entries: list[dict[str, Any]] = []
    client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=False)

    def pixel_params(lat: float, lon: float, **extra: str) -> dict[str, str]:
        return {
            "lat": f"{lat:.6f}",
            "lon": f"{lon:.6f}",
            "vars": ALL_VARS,
            "format": "json",
            **extra,
        }

    def get(
        name: str,
        url: str,
        params: dict[str, str] | None,
        transform: str = "none",
        shrink: Any = None,
    ) -> httpx.Response:
        r = client.get(url, params=params)
        key = fixture_key("GET", url if params else str(r.request.url), params)
        ctype = r.headers.get("content-type", "")
        body: Any
        if "json" in ctype:
            body = r.json()
            if shrink is not None:
                body = shrink(body)
        else:
            body = r.text[:500]
        path = _file_for(key, r.status_code, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        stored = {
            "status": r.status_code,
            "headers": {k: v for k, v in r.headers.items() if k.lower() in KEEP_HEADERS},
            "json" if "json" in ctype else "text": body,
        }
        path.write_text(json.dumps(stored, separators=(",", ":")) + "\n", encoding="utf-8")
        entries.append(
            {
                "key": key,
                "file": str(path.relative_to(FIX)),
                "status": r.status_code,
                "contentType": ctype,
                "transform": transform,
                "origin": "recorded",
                "recordedOn": today,
            }
        )
        print(f"{r.status_code} {len(r.content):>8} B  {name}")
        return r

    # 1-2. Two points, 2020 (leap year): the EEMT sample DEM cell and Hawaii.
    centre = location_for(*DEM_CENTRE, "na")
    get("pixel_dem_centre_2020", sp, pixel_params(centre.query_lat, centre.query_lon, years="2020"))
    hi = location_for(*HAWAII, "hi")
    get("pixel_hawaii_2020", sp, pixel_params(hi.query_lat, hi.query_lon, years="2020"))
    # 3. The other 8 cells of the 3x3 mosaic around the DEM centre cell.
    assert centre.cell is not None
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == dc == 0:
                continue
            cell = lcc.Cell(centre.cell.col + dc, centre.cell.row + dr)
            lat, lon = cell.centre_latlon()
            get(
                f"pixel_mosaic_c{cell.col}_r{cell.row}_2020",
                sp,
                pixel_params(round(lat, 6), round(lon, 6), years="2020"),
            )
    # 4. daymet_ping probe window.
    get(
        "pixel_ping_window",
        sp,
        pixel_params(centre.query_lat, centre.query_lon, start="2020-01-01", end="2020-01-02"),
    )
    # 5. Off-grid (ocean inside the NA bbox) -> HTTP 400.
    ocean = location_for(*OCEAN, "na")
    get("pixel_ocean_2020", sp, pixel_params(ocean.query_lat, ocean.query_lon, years="2020"))
    # 6. Unpublished year -> whole record with HTTP 200 (truncated to 2 rows of 2 years).

    def truncate(body: dict[str, Any]) -> dict[str, Any]:
        data = body["data"]
        keep = [i for i, y in enumerate(data["year"]) if int(y) in (1980, 1981)]
        keep = [i for i in keep if int(data["yday"][i]) <= 2]
        body["data"] = {k: [v[i] for i in keep] for k, v in data.items()}
        return body

    get(
        "pixel_unpublished_year",
        sp,
        pixel_params(centre.query_lat, centre.query_lon, years="2026"),
        transform="truncated: kept yday 1-2 of 1980 and 1981",
        shrink=truncate,
    )
    # 7. CMR latest granule per collection (shrunk to the fields the server reads).

    def shrink_cmr(body: dict[str, Any]) -> dict[str, Any]:
        items = body.get("items") or []
        return {
            "hits": body.get("hits"),
            "items": [
                {
                    "meta": {"concept-id": i["meta"].get("concept-id")},
                    "umm": {
                        "GranuleUR": i["umm"].get("GranuleUR"),
                        "TemporalExtent": i["umm"].get("TemporalExtent"),
                    },
                }
                for i in items[:1]
            ],
        }

    for coll in COLLECTIONS:
        get(
            f"cmr_latest_{coll.product}",
            "https://cmr.earthdata.nasa.gov/search/granules.umm_json",
            {"collection_concept_id": coll.concept_id, "sort_key": "-start_date", "page_size": "1"},
            transform="shrunk: hits, items[0].meta.concept-id, umm.GranuleUR, umm.TemporalExtent",
            shrink=shrink_cmr,
        )
    # 8. Earthdata OPeNDAP subset without credentials: record each redirect hop.
    url, params = subset_request(
        "https://opendap.earthdata.nasa.gov/collections",
        "na",
        "tmax",
        2020,
        (5671, 5673),
        (3984, 3986),
    )
    r = get("edl_opendap_subset", url, params, transform="body truncated to 500 chars")
    hops = 0
    while r.status_code in (301, 302, 303, 307, 308) and hops < 5:
        nxt = str(r.request.url.join(r.headers["location"]))
        host = urlsplit(nxt).hostname or ""
        if host not in {"opendap.earthdata.nasa.gov", "urs.earthdata.nasa.gov"}:
            break
        hops += 1
        r = get(f"edl_hop{hops}", nxt, None, transform="body truncated to 500 chars")

    MANIFEST.write_text(
        json.dumps(
            {
                "note": (
                    "Daymet V4 R1 extracts (DOI 10.3334/ORNLDAAC/2129) via the ORNL DAAC single-pixel API "
                    "and NASA CMR metadata, fetched without credentials; see NOTICE for data terms."
                ),
                "fixtures": sorted(entries, key=lambda e: e["key"]) + _synthetic_entries(),
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )


def _synthetic_entries() -> list[dict[str, Any]]:
    if not MANIFEST.exists():
        return []
    old = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [e for e in old.get("fixtures", []) if e.get("origin") == "synthetic"]


def check() -> int:
    from daymet_mcp.daymet.client import ALLOWED_HOSTS  # type: ignore[import-not-found]

    problems: list[str] = []
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    total = 0
    for entry in manifest["fixtures"]:
        path = FIX / entry["file"]
        if not path.is_file():
            problems.append(f"missing file {entry['file']}")
            continue
        size = path.stat().st_size
        total += size
        if size > MAX_FILE:
            problems.append(f"{entry['file']} is {size} B (> {MAX_FILE})")
        if entry.get("origin") == "synthetic":
            continue
        host = urlsplit("https://" + entry["key"].split(" ", 1)[1]).hostname
        if host not in ALLOWED_HOSTS:
            problems.append(f"{entry['file']}: host {host} not allow-listed")
        if not entry["key"].startswith("GET "):
            problems.append(f"{entry['file']}: only GET fixtures are allowed")
        stored = json.loads(path.read_text(encoding="utf-8"))
        bad = [h for h in stored.get("headers", {}) if h.lower() in CREDENTIAL_HEADERS]
        if bad:
            problems.append(f"{entry['file']}: credential headers {bad}")
    if total > MAX_TOTAL:
        problems.append(f"fixtures total {total} B (> {MAX_TOTAL})")
    for p in problems:
        print("ERROR", p)
    print(f"{len(manifest['fixtures'])} fixtures, {total} bytes, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "record":
        record()
    else:
        sys.exit(check())
