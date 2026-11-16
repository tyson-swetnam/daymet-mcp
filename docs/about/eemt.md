---
title: "Using daymet-mcp with EEMT"
description: "How the EEMT pipelines and their developers use daymet-mcp to get Daymet tmin, tmax, prcp, vp and elevation on demand."
type: Guide
tags:
  - eemt
  - workflow
generated:
  by: "claude/opus-5.5"
  at: "2026-11-15T00:00:00Z"
sources:
  - id: design
    resource: "DESIGN.md"
    title: "daymet-mcp design"
    author: "team:daymet-mcp"
status: draft
---

# Using daymet-mcp with EEMT

The Effective Energy and Mass Transfer (EEMT) pipeline reads Daymet `tmin`, `tmax`, `prcp` and `vp`
per period and the Daymet 1 km DEM for its lapse-rate correction. daymet-mcp provides all of them
with the aggregation stated: **monthly prcp is a total of daily values (mm/month)**, matching the
pipeline's definition; tmin, tmax and vp are monthly means.

* **Interactive work**: add daymet-mcp to your MCP client and call `daymet_locate_cell`,
  `daymet_get_point_summary(period="monthly")` and `daymet_get_citation`, or use the
  `daymet_eemt_inputs` prompt.
* **Pipeline (proposed, not yet implemented in EEMT)**: a small adapter starts `daymet-mcp` over
  stdio with the MCP Python SDK and calls `daymet_download_area` with `temporal="monthly"`,
  `variables=["tmin","tmax","prcp","vp"]`, `include_elevation=true`, `format="aaigrid"` and the DEM
  bounding box plus a 2-cell buffer. The `.asc` + `.prj` files are GDAL-readable; importing them
  with `r.in.gdal` inside the EEMT container has not been tested yet. The adapter copies
  `manifest.json` into the job's provenance.
* **Grids stay native**: values come on the 1 km Lambert Conformal Conic grid; reprojection to the
  DEM stays in EEMT.
* **CI**: EEMT keeps its own committed fixture and never needs the network or daymet-mcp.

The EEMT sample DEM needs a 7x7 cell area with a 2-cell buffer, well inside the credential-free
limit of 121 cells.
