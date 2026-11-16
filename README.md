# daymet-mcp

A [Model Context Protocol](https://modelcontextprotocol.io/) server (MCP 2026-07-28, stateless
core) that retrieves [Daymet V4 R1](https://daymet.ornl.gov/) surface weather data on demand:
daily values at a point, monthly and annual summaries, the 1 km grid cell for a point, small-area
grids, file downloads and citations. It was written so that the EEMT (Effective Energy and Mass
Transfer) pipelines and AI agents can pull Daymet when they need it instead of managing files by
hand.

**Every summary says how it was computed.** Monthly and annual precipitation are **totals** of
daily values (`prcp_monthly_total_mm`, mm/month; mm/year). Temperature, vapour pressure, snow water
equivalent, radiation and day length are **means** of daily values, with opt-in alternatives for
swe (`last`) and srad (`total`, MJ/m2). Each series carries `aggregation`, `units`, `fieldLabel`
and a `definition`. Every Daymet year has 365 days: leap years keep February 29 and drop
December 31, so a leap-year December has 30 days.

| Tool | What it does |
| --- | --- |
| `daymet_ping` | Version, protocol, backends; optional tiny live check |
| `daymet_list_variables` | Variables, units, aggregation rules, regions, latest years (CMR), grid |
| `daymet_locate_cell` | lat/lon to the Daymet LCC cell (offline) |
| `daymet_get_point_daily` | Daily values for the cell containing a point |
| `daymet_get_point_summary` | Monthly or annual summaries at a point |
| `daymet_get_area` | Small-area grid on the native 1 km grid, in the result |
| `daymet_download_area` | The same grid as AAIGrid+.prj, CSV or NetCDF files (stdio only) |
| `daymet_get_citation` | Dataset, tool and method citations with DOIs and BibTeX |

Points and areas up to 121 cells use the ORNL single-pixel API and need **no credentials**.
Larger areas use NASA Earthdata (OPeNDAP), which needs an operator token in
`DAYMET_MCP_EARTHDATA__TOKEN` and the `grid` extra; that backend is **experimental** (no
credentialed request has been tested).

## Quick start

```bash
uv sync                                   # installs from the hash-pinned uv.lock
uv run daymet-mcp --check                 # offline self-test
claude mcp add daymet -s user -- uv --directory "$PWD" run daymet-mcp
```

Then, for example: monthly precipitation totals for 2020 at the EEMT sample DEM centre:

```json
{"name": "daymet_get_point_summary",
 "arguments": {"lat": 35.802997, "lon": -106.624036, "period": "monthly",
               "start_year": 2020, "end_year": 2020, "variables": ["prcp"]}}
```

HTTP: `uv run daymet-mcp --transport http` serves `http://127.0.0.1:8080/mcp` (plus `/healthz` and
`/readyz`). Container: `docker build -t daymet-mcp:local .` and
`docker run --rm -p 127.0.0.1:8080:8080 daymet-mcp:local`.

## Development

```bash
uv sync --all-extras
uv run pytest                          # hermetic (recorded fixtures, no network)
uv run pytest -m network tests/live    # live tests against ORNL DAAC and NASA CMR
uv run ruff check src tests scripts && uv run mypy src
python scripts/okf_validate.py docs && python scripts/gen_llms_txt.py
```

Documentation is an OKF v0.2 bundle under [`docs/`](docs/index.md) (agents: `docs/llms.txt`,
`docs/llms-full.txt`). Design decisions are in [`DESIGN.md`](DESIGN.md), the verified upstream
facts in [`RESEARCH.md`](RESEARCH.md), agent rules in [`AGENTS.md`](AGENTS.md).

## Licence and data terms

Code: MIT (see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE); parts are adapted from
[idss-mesa/neon-mcp](https://github.com/idss-mesa/neon-mcp)). Documentation: CC BY 4.0.
**Daymet data are not covered by the MIT licence**: cite Thornton et al. 2022,
https://doi.org/10.3334/ORNLDAAC/2129 (and the single-pixel tool,
https://doi.org/10.3334/ORNLDAAC/2361, when it was used). All Daymet data are provisional and
subject to revision. `daymet_get_citation` produces the citations.
