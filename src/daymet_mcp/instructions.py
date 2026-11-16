# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Server instructions (≤ 1 200 characters; DESIGN.md §10)."""

SERVER_INSTRUCTIONS = (
    "daymet-mcp serves Daymet V4 R1 surface weather (ORNL DAAC): 1 km daily grids for North "
    "America, Hawaii and Puerto Rico, 1980 to the latest published year. Variables: dayl, prcp, "
    "srad, swe, tmax, tmin, vp. Point data need no login (single-pixel API); large areas need "
    "an Earthdata token set by the operator. Monthly and annual prcp are SUMS of daily values "
    "(mm/month, mm/year); the other variables are MEANS unless overridden (swe 'last', srad "
    "'total' MJ/m2); every summary field states its aggregation and units, e.g. "
    "prcp_monthly_total_mm. Every Daymet year has 365 days: leap years keep Feb 29 and drop "
    "Dec 31. Start with daymet_list_variables or daymet_locate_cell; use "
    "daymet_get_point_daily / daymet_get_point_summary for points and daymet_get_area for small "
    "bboxes. Cite with daymet_get_citation."
)

assert len(SERVER_INSTRUCTIONS) <= 1200  # noqa: S101 - import-time guard
