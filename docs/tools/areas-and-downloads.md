---
title: "Areas and downloads"
description: "Small-area Daymet grids returned in results or written to files, the two backends, and the limits that keep requests polite."
type: Guide
tags:
  - areas
  - downloads
  - limits
generated:
  by: "claude/opus-5.5"
  at: "2026-11-15T00:00:00Z"
sources:
  - id: design
    resource: "DESIGN.md"
    title: "daymet-mcp design"
    author: "team:daymet-mcp"
  - id: research
    resource: "RESEARCH.md"
    title: "daymet-mcp research notes"
    author: "team:daymet-mcp"
status: stable
---

# Areas and downloads

`daymet_get_area` returns values for every Daymet cell whose centre falls inside a WGS84 bounding
box, on the native 1 km grid (no resampling). Values are indexed `values[time][row][col]`, rows
north to south. `temporal` is `daily`, `monthly` or `annual`, with the same aggregation rules as
points. `include_elevation=true` adds the Daymet 1 km cell elevation from the single-pixel header.

`daymet_download_area` (stdio only) writes the same grids under `downloads.dir`:

* `aaigrid` (default): one ESRI ASCII grid plus `.prj` (Daymet LCC) per variable and period,
  readable by GDAL and GRASS `r.in.gdal`;
* `csv`: one long table;
* `netcdf`: one file per variable and year (needs the `grid` extra).

It also writes `manifest.json` with the request, backend, upstream endpoints, aggregation table,
calendar, citations and the sha256 of every file. File names are deterministic; existing files are
refused unless `overwrite=true`. Subfolders are confined to `downloads.dir`, and symbolic links are
refused.

## Backends and limits

| Backend | When | Limit (default / ceiling) |
| --- | --- | --- |
| single-pixel mosaic | `auto` within the limits, or `single_pixel` | 121 / 400 cells; 605 / 2000 cell-years |
| Earthdata OPeNDAP (experimental) | `auto` above the limits with a token, or `earthdata` | 25 million / 200 million values |

The single-pixel mosaic sends one request per cell, at most 2 requests per second and 4 at a time.
A request that exceeds a limit is refused before any upstream call with `query_too_large`, naming
the limit and the requested amount. Above the limits without a token the answer is
`auth_required`; see [Earthdata credentials](../getting-started/earthdata-credentials.md).
