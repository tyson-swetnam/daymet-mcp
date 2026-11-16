---
title: "Monthly and annual aggregation"
description: "Exactly how daymet-mcp turns daily Daymet values into monthly and annual values: sum versus mean, units, labels and calendar."
type: Reference
tags:
  - aggregation
  - precipitation
  - calendar
generated:
  by: "claude/opus-5.5"
  at: "2026-11-15T00:00:00Z"
sources:
  - id: daily-guide
    resource: "https://doi.org/10.3334/ORNLDAAC/2129"
    title: "Daymet V4 R1 daily data user guide"
    author: "team:ornl-daac"
  - id: monthly-guide
    resource: "https://doi.org/10.3334/ORNLDAAC/2131"
    title: "Daymet V4 R1 monthly climate summaries"
    author: "team:ornl-daac"
  - id: design
    resource: "DESIGN.md"
    title: "daymet-mcp design"
    author: "team:daymet-mcp"
status: stable
stale_after: "2027-11-15T00:00:00Z"
---

# Monthly and annual aggregation

daymet-mcp computes every monthly and annual value from Daymet **daily** data (DOI
10.3334/ORNLDAAC/2129). Each summary series states its `aggregation`, its `units`, the daily units
it came from, a `definition`, and a machine-readable `fieldLabel`.

| Variable | Daily units | Monthly | Annual | Alternative |
| --- | --- | --- | --- | --- |
| prcp | mm/day | **sum**, mm/month (`prcp_monthly_total_mm`) | **sum**, mm/year (`prcp_annual_total_mm`) | none |
| tmax | degC | mean, degC (`tmax_monthly_mean_degC`) | mean, degC | none |
| tmin | degC | mean, degC (`tmin_monthly_mean_degC`) | mean, degC | none |
| vp | Pa | mean, Pa (`vp_monthly_mean_Pa`) | mean, Pa | none |
| swe | kg/m2 | mean, kg/m2 (`swe_monthly_mean_kg_m2`) | mean, kg/m2 | `last`: value on the last Daymet day of the period |
| srad | W/m2 (daylight average) | mean, W/m2 (`srad_monthly_mean_W_m2`) | mean, W/m2 | `total`: sum of srad x dayl / 1e6, MJ/m2/month or MJ/m2/year |
| dayl | s/day | mean, s/day (`dayl_monthly_mean_s`) | mean, s/day | none |

**Monthly precipitation is the total of the daily values in the month (mm/month), never a mean.**
The ORNL monthly product (DOI 10.3334/ORNLDAAC/2131) uses the same definitions for prcp, tmax,
tmin, vp and swe; it has no srad or dayl and its latest year lags the daily product.

Alternatives are opt-in with `aggregation_overrides`, for example `{"swe": "last", "srad":
"total"}`; every other variable's aggregation is fixed.

## Calendar

Every Daymet year has 365 days: leap years keep February 29 and drop December 31. A leap-year
December therefore has 30 days and its precipitation total covers December 1-30. Each period in a
result reports `dayCount`, `firstDate` and `lastDate`. The server never imputes December 31, never
rescales a sum to a nominal month length, and never fills gaps: a period with a missing daily value
has `complete: false` and value `null`.

## Rounding

Daily values are rounded to 2 decimals (the precision of the Daymet CSV). Aggregates are computed
from the unrounded upstream values and rounded to 3 decimals, so the sum of twelve monthly totals
can differ from the sum of 365 rounded daily values by a few thousandths of a millimetre.

## Provenance

Every summary result lists the computed series in `source.derived` with the note "computed by
daymet-mcp from Daymet daily V4 R1 (DOI 10.3334/ORNLDAAC/2129); not the ORNL monthly product
(2131)". Cite DOI 2129 for these values.
