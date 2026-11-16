---
title: "Points and grid cells"
description: "How daymet-mcp maps a point to its 1 km Daymet cell and fetches daily values and summaries for that cell."
type: Guide
tags:
  - points
  - grid
  - single-pixel
generated:
  by: "claude/opus-5.5"
  at: "2026-11-15T00:00:00Z"
sources:
  - id: single-pixel
    resource: "https://daymet.ornl.gov/web_services"
    title: "Daymet single-pixel web service"
    author: "team:ornl-daac"
  - id: research
    resource: "RESEARCH.md"
    title: "daymet-mcp research notes"
    author: "team:daymet-mcp"
  - id: design
    resource: "DESIGN.md"
    title: "daymet-mcp design"
    author: "team:daymet-mcp"
status: stable
---

# Points and grid cells

## The grid

Daymet uses a Lambert Conformal Conic projection
(`+proj=lcc +lat_1=25 +lat_2=60 +lat_0=42.5 +lon_0=-100 +x_0=0 +y_0=0 +ellps=WGS84`). The North
America grid has 7814 columns by 8075 rows of 1 km cells with centres at
`x = -4560250 + 1000 * col` and `y = 4984000 - 1000 * row` metres. daymet-mcp projects points
itself (a pure-Python implementation checked against values the single-pixel service reported and
against pyproj) and snaps them to the cell whose centre is within 500 m in x and y.

`daymet_locate_cell` does this offline. For Hawaii and Puerto Rico it returns the projected
coordinates but no cell indices, because those mosaics' origins have not been verified.

## Daily values and summaries

`daymet_get_point_daily` and `daymet_get_point_summary` query the ORNL single-pixel API at the
**cell centre**, always for all seven variables and whole years, and cache the result per cell and
year; any nearby point in the same cell is served from the cache. The single-pixel API fails
silently in several ways, so the server checks every response:

* unknown variable names are ignored upstream, so variables are validated locally;
* asking for an unpublished year returns the whole record with HTTP 200, so years are checked
  against the latest year published in NASA CMR, and the years and row counts returned are
  compared with the request;
* the units in each column name (for example `prcp (mm/day)`, `vp (Pa)`) are compared with the
  catalogue and never relabelled;
* a point over water returns HTTP 400 "Daymet Tile was not found", reported as `not_found`
  with reason `off_grid`.

A date in the request must exist in the Daymet calendar: `2020-12-31` is refused with reason
`not_in_daymet_calendar`.
