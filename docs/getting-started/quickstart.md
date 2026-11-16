---
title: "Quickstart"
description: "Five tool calls that locate a Daymet cell, read daily data, total monthly precipitation and cite the dataset."
type: Tutorial
tags:
  - quickstart
  - tutorial
generated:
  by: "claude/opus-5.5"
  at: "2026-11-15T00:00:00Z"
sources:
  - id: design
    resource: "DESIGN.md"
    title: "daymet-mcp design"
    author: "team:daymet-mcp"
  - id: daily-guide
    resource: "https://doi.org/10.3334/ORNLDAAC/2129"
    title: "Daymet V4 R1 daily data user guide"
    author: "team:ornl-daac"
status: stable
---

# Quickstart

The example point is the centre of the EEMT sample DEM in the Valles Caldera, New Mexico
(35.802997, -106.624036).

1. **Check the server**: `daymet_ping()` returns the version, protocol version and backends.
2. **Locate the cell**: `daymet_locate_cell(lat=35.802997, lon=-106.624036)` returns column 3985,
   row 5672 of the North America grid, the cell centre (x = -575250 m, y = -688000 m) and the
   distance from the point to the centre (352.5 m).
3. **Daily values**: `daymet_get_point_daily(lat=35.802997, lon=-106.624036, years=[2020])` returns
   365 days. 2020 is a leap year, so February 29 is present and December 31 is not.
4. **Monthly totals**: `daymet_get_point_summary(lat=35.802997, lon=-106.624036, period="monthly",
   start_year=2020, end_year=2020, variables=["prcp"])` returns twelve values labelled
   `prcp_monthly_total_mm`, with `aggregation: "sum"` and `units: "mm/month"`. December has
   `dayCount: 30`.
5. **Cite**: `daymet_get_citation()` returns the dataset, tool and method citations with DOIs and
   BibTeX.

The twelve monthly totals add up to the sum of the 365 daily values (to the 3-decimal rounding of
each monthly value). The [aggregation page](../tools/aggregation.md) explains every rule.
