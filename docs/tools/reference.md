---
title: "Tool reference"
description: "Every daymet-mcp tool with its inputs, bounds, result fields, upstream endpoints and annotations, generated from the registry."
type: MCP Tool Reference
tags:
  - tools
  - reference
generated:
  by: "process:scripts/gen_tools_reference.py"
  at: "2026-11-15T00:00:00Z"
sources:
  - id: registry
    resource: "src/daymet_mcp/registry.py"
    title: "daymet-mcp tool registry"
    author: "team:daymet-mcp"
status: stable
---

# Tool reference

Generated from the tool registry by `scripts/gen_tools_reference.py`; do not edit by hand. Every result also carries the envelope fields `resolved`, `notes`, `nextSteps` and `source`, and errors are tool results with `structuredContent.error = {code, message, details, hint?}`.

| Tool | Title | Transports | Earthdata token |
| --- | --- | --- | --- |
| [`daymet_download_area`](#daymet_download_area) | Download a Daymet area to files | stdio | optional |
| [`daymet_get_area`](#daymet_get_area) | Daymet grid for a small area | http, stdio | optional |
| [`daymet_get_citation`](#daymet_get_citation) | Cite Daymet data | http, stdio | no |
| [`daymet_get_point_daily`](#daymet_get_point_daily) | Daily Daymet values at a point | http, stdio | no |
| [`daymet_get_point_summary`](#daymet_get_point_summary) | Monthly or annual Daymet summaries at a point | http, stdio | no |
| [`daymet_list_variables`](#daymet_list_variables) | List Daymet variables and aggregation rules | http, stdio | no |
| [`daymet_locate_cell`](#daymet_locate_cell) | Locate the Daymet grid cell | http, stdio | no |
| [`daymet_ping`](#daymet_ping) | Ping daymet-mcp | http, stdio | no |

## daymet_download_area

**Download a Daymet area to files.** Write a small-area Daymet grid to files under the configured downloads.dir (stdio only): AAIGrid .asc+.prj per variable and time step (GDAL-readable), one CSV table, or NetCDF ([grid] extra). Same inputs and aggregation rules as daymet_get_area; writes manifest.json with sha256, URLs and citation. Next: import the files (e.g. r.in.gdal), then daymet_get_citation.

- Surface: `area`; transports: stdio; Earthdata token: optional (large areas).
- Annotations: readOnly=false, destructive=false, idempotent=true, openWorld=true.
- Upstream: `GET daymet.ornl.gov/single-pixel/api/data`, `GET opendap.earthdata.nasa.gov/collections/{concept}/granules/{granule}.dap.nc4`.

| Argument | Type | Required | Default | Bounds | Description |
| --- | --- | --- | --- | --- | --- |
| `bbox` | object (BBox) | yes |  |  | WGS84 bounding box in decimal degrees; every Daymet cell whose centre falls inside is included. |
| `variables` | array of `dayl` \| `prcp` \| `srad` \| `swe` \| `tmax` \| `tmin` \| `vp` | yes |  | items >= 1 | Daymet variables (dayl, prcp, srad, swe, tmax, tmin, vp). |
| `start_year` | integer | yes |  | >= 1980 | Year (inclusive). Max = latest published year (checked at call time). |
| `end_year` | integer | yes |  | >= 1980 | Year (inclusive). Max = latest published year (checked at call time). |
| `temporal` | `daily` \| `monthly` \| `annual` | yes |  |  | daily values, or monthly/annual summaries computed from daily data. |
| `aggregation_overrides` | object (AggregationOverrides) \| null | no | `null` |  | Only swe (mean\|last) and srad (mean\|total) have alternatives. |
| `include_elevation` | boolean | no | `false` |  | Add the Daymet 1 km cell elevation grid (m). |
| `backend` | `auto` \| `single_pixel` \| `earthdata` | no | `"auto"` |  | auto = single_pixel when within its cell limit, else earthdata if a token is configured. |
| `format` | `aaigrid` \| `csv` \| `netcdf` | no | `"aaigrid"` |  | aaigrid: one .asc+.prj per variable and time step (GDAL-readable, no extra deps); csv: one long table; netcdf: one file per variable and year (needs the [grid] extra). |
| `subdir` | string \| null | no | `null` | pattern `^[A-Za-z0-9._-]{1,64}$` | Folder under the configured downloads.dir (default: derived from the request). |
| `overwrite` | boolean | no | `false` |  | Replace existing files with the same names. |

Result fields: `resolved`, `notes`, `nextSteps`, `source`, `directory`, `files`, `grid`, `manifestPath`, `backend`, `cellsRequested`.

## daymet_get_area

**Daymet grid for a small area.** Daymet values on the native 1 km LCC grid for a small WGS84 bbox, returned in the result: daily values or monthly/annual summaries (prcp = sum mm/month, others = mean). values[time][row][col], rows north to south. Credential-free up to 121 cells via single-pixel; larger areas need an operator Earthdata token. Time axis paged. Next: call daymet_download_area for files, then daymet_get_citation.

- Surface: `area`; transports: http, stdio; Earthdata token: optional (large areas).
- Annotations: readOnly=true, destructive=false, idempotent=true, openWorld=true.
- Upstream: `GET daymet.ornl.gov/single-pixel/api/data`, `GET opendap.earthdata.nasa.gov/collections/{concept}/granules/{granule}.dap.nc4`.

| Argument | Type | Required | Default | Bounds | Description |
| --- | --- | --- | --- | --- | --- |
| `bbox` | object (BBox) | yes |  |  | WGS84 bounding box in decimal degrees; every Daymet cell whose centre falls inside is included. |
| `variables` | array of `dayl` \| `prcp` \| `srad` \| `swe` \| `tmax` \| `tmin` \| `vp` | yes |  | items >= 1 | Daymet variables (dayl, prcp, srad, swe, tmax, tmin, vp). |
| `start_year` | integer | yes |  | >= 1980 | Year (inclusive). Max = latest published year (checked at call time). |
| `end_year` | integer | yes |  | >= 1980 | Year (inclusive). Max = latest published year (checked at call time). |
| `temporal` | `daily` \| `monthly` \| `annual` | yes |  |  | daily values, or monthly/annual summaries computed from daily data. |
| `aggregation_overrides` | object (AggregationOverrides) \| null | no | `null` |  | Only swe (mean\|last) and srad (mean\|total) have alternatives. |
| `include_elevation` | boolean | no | `false` |  | Add the Daymet 1 km cell elevation grid (m). |
| `backend` | `auto` \| `single_pixel` \| `earthdata` | no | `"auto"` |  | auto = single_pixel when within its cell limit, else earthdata if a token is configured. |
| `offset` | integer | no | `0` | >= 0 | Index of the first time step to return. |
| `limit` | integer | no | `366` | >= 1; <= 1000 | Max time steps to return. |

Result fields: `resolved`, `notes`, `nextSteps`, `source`, `grid`, `time`, `series`, `elevationM`, `backend`, `cellsRequested`, `calendar`, `page`.

## daymet_get_citation

**Cite Daymet data.** Citation text, DOI and BibTeX for Daymet V4 R1 data: the dataset (required; server-computed monthly/annual values cite the daily product 2129), the single-pixel tool when used (required), and method papers (recommended; extra ones for srad/vp). No network. Next: paste the citations into your methods section.

- Surface: `citation`; transports: http, stdio; Earthdata token: no.
- Annotations: readOnly=true, destructive=false, idempotent=true, openWorld=false.
- Upstream: none (local).

| Argument | Type | Required | Default | Bounds | Description |
| --- | --- | --- | --- | --- | --- |
| `products` | array of `daily` \| `monthly` \| `annual` | no |  |  | Products the values came from. Server-computed monthly/annual values come from the daily product, so cite 'daily' for them. |
| `access` | array of `single_pixel` \| `earthdata` | no |  |  | How the data were retrieved (adds the single-pixel tool citation). |
| `variables` | array of `dayl` \| `prcp` \| `srad` \| `swe` \| `tmax` \| `tmin` \| `vp` \| null | no | `null` | items >= 1 | Daymet variables (dayl, prcp, srad, swe, tmax, tmin, vp). Default: all seven. |
| `include_method_papers` | boolean | no | `true` |  | Add the recommended method papers. |
| `accessed_on` | string \| null | no | `null` |  | Access date. Default: today (UTC). |

Result fields: `resolved`, `notes`, `nextSteps`, `source`, `citations`, `accessedOn`, `dataPolicyUrl`.

## daymet_get_point_daily

**Daily Daymet values at a point.** Daily Daymet V4 R1 values (dayl, prcp, srad, swe, tmax, tmin, vp) for the 1 km cell containing a point, via the credential-free ORNL single-pixel API. Give whole years or a start/end date. Units sit next to every series; years have 365 days (leap years drop Dec 31). Paged by offset/limit. Next: call daymet_get_point_summary for monthly totals/means, then daymet_get_citation.

- Surface: `point`; transports: http, stdio; Earthdata token: no.
- Annotations: readOnly=true, destructive=false, idempotent=true, openWorld=true.
- Upstream: `GET daymet.ornl.gov/single-pixel/api/data`.

| Argument | Type | Required | Default | Bounds | Description |
| --- | --- | --- | --- | --- | --- |
| `lat` | number | yes |  | >= -90; <= 90 | Latitude, decimal degrees WGS84. |
| `lon` | number | yes |  | >= -180; <= 180 | Longitude, decimal degrees WGS84 (west negative). |
| `variables` | array of `dayl` \| `prcp` \| `srad` \| `swe` \| `tmax` \| `tmin` \| `vp` \| null | no | `null` | items >= 1 | Daymet variables (dayl, prcp, srad, swe, tmax, tmin, vp). Default: all seven. |
| `years` | array of integer \| null | no | `null` | items >= 1; items <= 46 | Whole years. Give either years or start_date+end_date. |
| `start_date` | string \| null | no | `null` |  | YYYY-MM-DD, inclusive; must exist in the Daymet calendar. |
| `end_date` | string \| null | no | `null` |  | YYYY-MM-DD, inclusive. |
| `offset` | integer | no | `0` | >= 0 | Index of the first time step to return. |
| `limit` | integer | no | `366` | >= 1; <= 1000 | Max time steps to return. |

Result fields: `resolved`, `notes`, `nextSteps`, `source`, `location`, `calendar`, `dataVersion`, `doi`, `time`, `series`, `page`.

## daymet_get_point_summary

**Monthly or annual Daymet summaries at a point.** Monthly or annual summaries computed from Daymet daily data at a point. prcp is a SUM (mm/month, mm/year); tmax, tmin, vp, swe, srad and dayl are MEANS of daily values (swe 'last' and srad 'total' MJ/m2 on request). Every series states its aggregation, units and a field label such as prcp_monthly_total_mm. Covers the latest daily year. Next: call daymet_get_citation.

- Surface: `point`; transports: http, stdio; Earthdata token: no.
- Annotations: readOnly=true, destructive=false, idempotent=true, openWorld=true.
- Upstream: `GET daymet.ornl.gov/single-pixel/api/data`.

| Argument | Type | Required | Default | Bounds | Description |
| --- | --- | --- | --- | --- | --- |
| `lat` | number | yes |  | >= -90; <= 90 | Latitude, decimal degrees WGS84. |
| `lon` | number | yes |  | >= -180; <= 180 | Longitude, decimal degrees WGS84 (west negative). |
| `variables` | array of `dayl` \| `prcp` \| `srad` \| `swe` \| `tmax` \| `tmin` \| `vp` \| null | no | `null` | items >= 1 | Daymet variables (dayl, prcp, srad, swe, tmax, tmin, vp). Default: all seven. |
| `period` | `monthly` \| `annual` | yes |  |  | monthly = calendar months; annual = Daymet 365-day year. |
| `start_year` | integer | yes |  | >= 1980 | Year (inclusive). Max = latest published year (checked at call time). |
| `end_year` | integer | yes |  | >= 1980 | Year (inclusive). Max = latest published year (checked at call time). |
| `months` | array of integer \| null | no | `null` |  | Optional month filter 1-12 (monthly only). |
| `aggregation_overrides` | object (AggregationOverrides) \| null | no | `null` |  | Only swe and srad have alternatives; every other variable's aggregation is fixed (see daymet_list_variables). |
| `offset` | integer | no | `0` | >= 0 | Index of the first time step to return. |
| `limit` | integer | no | `366` | >= 1; <= 1000 | Max time steps to return. |

Result fields: `resolved`, `notes`, `nextSteps`, `source`, `location`, `calendar`, `dataVersion`, `doi`, `period`, `periods`, `series`, `page`.

## daymet_list_variables

**List Daymet variables and aggregation rules.** List Daymet V4 R1 variables with daily units and the exact monthly/annual aggregation the server uses (prcp = sum, others = mean), regions, year ranges, the 365-day calendar and collection DOIs. Next: call daymet_get_point_summary or daymet_locate_cell.

- Surface: `catalog`; transports: http, stdio; Earthdata token: no.
- Annotations: readOnly=true, destructive=false, idempotent=true, openWorld=true.
- Upstream: `GET cmr.earthdata.nasa.gov/search/granules.umm_json`.

No arguments.

Result fields: `resolved`, `notes`, `nextSteps`, `source`, `variables`, `regions`, `calendar`, `collections`, `grid`.

## daymet_locate_cell

**Locate the Daymet grid cell.** Map a WGS84 lat/lon to Daymet's Lambert Conformal Conic projection and the 1 km grid cell that contains it (column, row, cell-centre x/y and lat/lon, distance to centre). Pure computation; no network. Next: call daymet_get_point_daily or daymet_get_point_summary for that point.

- Surface: `cell`; transports: http, stdio; Earthdata token: no.
- Annotations: readOnly=true, destructive=false, idempotent=true, openWorld=false.
- Upstream: none (local).

| Argument | Type | Required | Default | Bounds | Description |
| --- | --- | --- | --- | --- | --- |
| `lat` | number | yes |  | >= -90; <= 90 | Latitude, decimal degrees WGS84. |
| `lon` | number | yes |  | >= -180; <= 180 | Longitude, decimal degrees WGS84 (west negative). |

Result fields: `resolved`, `notes`, `nextSteps`, `source`, `region`, `inCoverage`, `query`, `cell`, `crs`, `gridDefinition`.

## daymet_ping

**Ping daymet-mcp.** Report the daymet-mcp version, MCP protocol version, transport and which backends are usable (single-pixel always; Earthdata only with an operator token). With check_upstream=true it makes one tiny live single-pixel request and reports latency. Next: call daymet_list_variables to see variables, units and aggregation rules.

- Surface: `core`; transports: http, stdio; Earthdata token: no.
- Annotations: readOnly=true, destructive=false, idempotent=true, openWorld=true.
- Upstream: `GET daymet.ornl.gov/single-pixel/api/data`.

| Argument | Type | Required | Default | Bounds | Description |
| --- | --- | --- | --- | --- | --- |
| `check_upstream` | boolean | no | `false` |  | Also make one tiny live single-pixel request (2-day window). |

Result fields: `resolved`, `notes`, `nextSteps`, `source`, `server`, `backends`, `upstream`.
