# Changelog

All notable changes to daymet-mcp are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-15

### Added

- MCP 2026-07-28 server (stateless core, `mcp` 2.x) with eight tools: `daymet_ping`,
  `daymet_list_variables`, `daymet_locate_cell`, `daymet_get_point_daily`,
  `daymet_get_point_summary`, `daymet_get_area`, `daymet_download_area` (stdio only) and
  `daymet_get_citation`; six resources, two resource templates and three prompts.
- Explicit aggregation: monthly/annual precipitation is a sum (mm/month, mm/year), the other
  variables are means, with swe `last` and srad `total` (MJ/m2) on request; every series states
  aggregation, units, field label and definition.
- Daymet 365-day calendar handling (leap years drop Dec 31).
- Credential-free single-pixel backend with guards against silent upstream failures; latest
  published year from NASA CMR; pure-Python LCC projection and grid snapping.
- Experimental Earthdata OPeNDAP backend (`grid` extra, env-only token), untested with credentials.
- stdio and stateless Streamable HTTP transports (`/mcp`, `/healthz`, `/readyz`).
- Hermetic tests on recorded fixtures, MCP protocol tests (in-process, stdio subprocess, HTTP),
  network-marked live tests; OKF v0.2 documentation with `llms.txt` and `llms-full.txt`;
  Dockerfile (digest-pinned bases, non-root, hashed install), docker-compose and CI workflows.
