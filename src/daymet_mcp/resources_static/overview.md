# daymet-mcp overview

Daymet V4 R1 (ORNL DAAC) estimates daily surface weather on a 1 km Lambert Conformal Conic
grid for continental North America, Hawaii and Puerto Rico, 1980 to the latest published
year: day length (dayl), precipitation (prcp), shortwave radiation (srad), snow water
equivalent (swe), maximum and minimum air temperature (tmax, tmin) and vapour pressure (vp).

## Backends

* **single-pixel** (default, no login): the ORNL DAAC single-pixel API returns the daily
  record of the 1 km cell containing a point. daymet-mcp uses it for points and for small
  areas (one request per cell, up to `limits.pixel_mosaic_max_cells`, default 121).
* **earthdata** (experimental, needs an operator token): NASA Earthdata OPeNDAP subsetting
  of the daily granules for larger areas. Every gridded endpoint answers 401 without
  Earthdata Login; see `daymet://guide/earthdata-credentials`.
* **CMR** (no login): the latest published year per product.

## What the server guarantees

* Variables are validated locally (upstream silently ignores unknown names).
* Years outside 1980..latest are refused (upstream returns the whole record instead).
* Every response is checked for the requested years and 365 rows per year.
* Monthly and annual values are computed from daily data and state their aggregation and
  units (`daymet://guide/aggregation`).
* All Daymet data are provisional and subject to revision.
