# CLAUDE.md

Guidance for Claude Code in this repository. Read `AGENTS.md` first; it holds the commands and
rules. This file adds what is specific to working with Claude.

## What this is

daymet-mcp: an MCP 2026-07-28 server (Python, `mcp` 2.x low-level `Server`) that retrieves
Daymet V4 R1 data on demand for the EEMT pipelines and AI agents. `src/daymet_mcp/server.py` is
the only module that imports the SDK server API; tools are registered with
`registry.register_tool` and are `async (args, ctx) -> OutputModel`.

## Facts to keep straight

- Monthly/annual prcp = **sum** (mm/month, mm/year); tmax/tmin/vp/swe/srad/dayl = **mean**;
  swe `last` and srad `total` (MJ/m2) only on request. Field labels: `prcp_monthly_total_mm`, ...
- 365-day years; leap-year December has 30 days.
- The single-pixel API fails silently (unknown variables ignored; unpublished years return the
  whole record with HTTP 200); the guards in `daymet/single_pixel.py` exist for that.
- NA grid: cell centres `x = -4560250 + 1000*col`, `y = 4984000 - 1000*row`; EEMT sample DEM
  centre (35.802997, -106.624036) is cell c3985/r5672.
- The Earthdata backend is experimental and untested with credentials.

## Working rules

- Run tests and checks in a container or `uv run`; never install into the system Python.
- Do not make network requests in hermetic tests; use the fixture router. Keep live requests
  small (single pixels, at most a 3x3 mosaic).
- Never put credentials, personal names, e-mail addresses or local paths into upstream requests;
  the User-Agent is the generic `daymet-mcp/<version> (+https://github.com/idss-mesa)`.
- Report only what was run and seen; label inferences.
- Do not create GitHub repositories, push or open pull requests unless the owner asks.
