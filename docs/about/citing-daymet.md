---
title: "Citing Daymet"
description: "Which Daymet DOIs and method papers to cite for values that daymet-mcp retrieved or computed, with access dates."
type: Policy
tags:
  - citation
  - doi
generated:
  by: "claude/opus-5.5"
  at: "2026-11-15T00:00:00Z"
sources:
  - id: daymet-citations
    resource: "https://daymet.ornl.gov/citations"
    title: "Daymet citation guidance"
    author: "team:ornl-daac"
  - id: daily-guide
    resource: "https://doi.org/10.3334/ORNLDAAC/2129"
    title: "Daymet V4 R1 daily data user guide"
    author: "team:ornl-daac"
status: stable
---

# Citing Daymet

`daymet_get_citation` renders these citations with DOIs and BibTeX; the templates live in
`daymet://guide/citing-daymet`.

* **Dataset (required)**: Thornton, M.M., R. Shrestha, Y. Wei, P.E. Thornton, and S-C. Kao. 2022.
  Daymet: Daily Surface Weather Data on a 1-km Grid for North America, Version 4 R1. ORNL DAAC.
  https://doi.org/10.3334/ORNLDAAC/2129. Monthly and annual values computed by daymet-mcp come from
  the daily product and cite this DOI, not the ORNL monthly (2131) or annual (2130) products.
* **Tool (required when the single-pixel API was used)**: Thornton, M.M., and R. Devarakonda.
  2011. Daymet Single Pixel Extraction Tool. https://doi.org/10.3334/ORNLDAAC/2361.
* **Method (recommended)**: the general methods reference is Thornton et al. 2021, Scientific
  Data 8:190, https://doi.org/10.1038/s41597-021-00973-0, together with Thornton, Running and
  White 1997, Journal of Hydrology 190:214-251, https://doi.org/10.1016/S0022-1694(96)03128-9;
  with srad or vp also Thornton et al. 2000 and Thornton and Running 1999.

The citation embedded in single-pixel responses adds B.E. Wilson as an author; the user guide
does not, and daymet-mcp uses the user-guide form. All Daymet data are provisional and subject to
revision, so record the access date.
