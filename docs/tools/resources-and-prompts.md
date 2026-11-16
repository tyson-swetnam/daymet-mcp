---
title: "Resources and prompts"
description: "The daymet:// guides and JSON references, the two resource templates, and the three task prompts daymet-mcp offers."
type: Reference
tags:
  - resources
  - prompts
generated:
  by: "claude/opus-5.5"
  at: "2026-11-15T00:00:00Z"
sources:
  - id: design
    resource: "DESIGN.md"
    title: "daymet-mcp design"
    author: "team:daymet-mcp"
status: stable
---

# Resources and prompts

## Resources

| URI | Content |
| --- | --- |
| `daymet://guide/overview` | What Daymet is, the backends, when credentials are needed |
| `daymet://guide/aggregation` | The aggregation rules (monthly prcp is a total, mm/month) |
| `daymet://guide/citing-daymet` | Citation templates used by `daymet_get_citation` |
| `daymet://guide/earthdata-credentials` | How an operator sets an Earthdata token |
| `daymet://reference/variables` | The variable and aggregation table (JSON) |
| `daymet://reference/grid` | proj4, ESRI WKT, the NA grid definition and region bboxes (JSON) |
| `daymet://cell/{lat}/{lon}` | Template: the cell containing a point |
| `daymet://point/{lat}/{lon}/monthly/{year}` | Template: monthly summaries of all variables for a year |

An unknown URI returns JSON-RPC error `-32602` with `data.code = "not_found"` and `didYouMean`.

## Prompts

* `daymet_site_climate(lat, lon, start_year, end_year)`: locate the cell, summarise monthly
  climate (precipitation as totals, the rest as means) and cite.
* `daymet_eemt_inputs(west, south, east, north, year)`: download monthly tmin, tmax, prcp and vp
  grids plus elevation for an EEMT domain.
* `daymet_monthly_precip_check(lat, lon, year)`: show daily precipitation and monthly totals
  side by side and explain sum versus mean.
