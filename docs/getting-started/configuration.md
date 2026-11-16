---
title: "Configuration"
description: "Every daymet-mcp setting with its environment variable, type and default; precedence is CLI flag, environment, YAML, default."
type: Reference
tags:
  - configuration
  - environment
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

# Configuration

Precedence: **command-line flag > environment > YAML file (`--config`) > default**. Environment
variables are `DAYMET_MCP_<SECTION>__<FIELD>`; `__` descends one level and list values are
comma-separated. `.env` files are never loaded automatically (use `uv run --env-file .env`).

```bash
daymet-mcp --print-config         # effective configuration, token shown as "***"
daymet-mcp --check                # offline self-test
daymet-mcp --check --live         # plus one tiny live request
```

Configuration errors name the setting, never its value, and exit with code 2. The Earthdata token
is accepted only from `DAYMET_MCP_EARTHDATA__TOKEN`; a `token` key in YAML is an error.

## Settings

<!-- BEGIN GENERATED CONFIG (scripts/gen_config_reference.py; do not edit) -->

| Setting (YAML path) | Environment variable | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `server.transport` | `DAYMET_MCP_SERVER__TRANSPORT` | `stdio` \| `http` | `stdio` | stdio or http. |
| `server.host` | `DAYMET_MCP_SERVER__HOST` | str | `127.0.0.1` | HTTP bind address. |
| `server.port` | `DAYMET_MCP_SERVER__PORT` | int | `8080` | HTTP port. |
| `server.public_base_url` | `DAYMET_MCP_SERVER__PUBLIC_BASE_URL` | str \| null | unset | Public URL when behind a proxy. |
| `server.allowed_hosts` | `DAYMET_MCP_SERVER__ALLOWED_HOSTS` | list[str] | `[]` | Extra Host values accepted (DNS-rebinding guard). |
| `server.allowed_origins` | `DAYMET_MCP_SERVER__ALLOWED_ORIGINS` | list[str] | `[]` | Extra Origin values accepted. |
| `server.dns_rebinding_protection` | `DAYMET_MCP_SERVER__DNS_REBINDING_PROTECTION` | bool | `true` | Validate Host/Origin headers. |
| `server.json_response` | `DAYMET_MCP_SERVER__JSON_RESPONSE` | bool | `true` | Plain JSON responses instead of SSE. |
| `server.log_level` | `DAYMET_MCP_SERVER__LOG_LEVEL` | str | `INFO` | DEBUG, INFO, WARNING or ERROR. |
| `server.instructions_extra` | `DAYMET_MCP_SERVER__INSTRUCTIONS_EXTRA` | str \| null | unset | Text appended to the server instructions. |
| `daymet.single_pixel_url` | `DAYMET_MCP_DAYMET__SINGLE_PIXEL_URL` | str | `https://daymet.ornl.gov/single-pixel/api/data` | Single-pixel API endpoint. |
| `daymet.cmr_url` | `DAYMET_MCP_DAYMET__CMR_URL` | str | `https://cmr.earthdata.nasa.gov/search` | CMR search root. |
| `daymet.latest_year_fallback.daily` | `DAYMET_MCP_DAYMET__LATEST_YEAR_FALLBACK__DAILY` | int | `2025` | Latest daily year if CMR cannot be reached. |
| `daymet.first_year` | `DAYMET_MCP_DAYMET__FIRST_YEAR` | int | `1980` | First year served (D8). |
| `earthdata.token (env only)` | `DAYMET_MCP_EARTHDATA__TOKEN` | SecretStr \| null | unset | EDL user token; environment only (DAYMET_MCP_EARTHDATA__TOKEN). |
| `earthdata.opendap_url` | `DAYMET_MCP_EARTHDATA__OPENDAP_URL` | str | `https://opendap.earthdata.nasa.gov/collections` | Hyrax OPeNDAP root. |
| `earthdata.allow_in_http_mode` | `DAYMET_MCP_EARTHDATA__ALLOW_IN_HTTP_MODE` | bool | `false` | Let anonymous HTTP callers use the operator's token (D17). |
| `cache.max_cell_years` | `DAYMET_MCP_CACHE__MAX_CELL_YEARS` | int | `20000` | In-memory cell-year entries. |
| `cache.ttl_s.pixel` | `DAYMET_MCP_CACHE__TTL_S__PIXEL` | int | `604800` | Single-pixel cell-year TTL (s). |
| `cache.ttl_s.cmr` | `DAYMET_MCP_CACHE__TTL_S__CMR` | int | `86400` | CMR latest-year TTL (s). |
| `cache.stale_if_error_s` | `DAYMET_MCP_CACHE__STALE_IF_ERROR_S` | int | `86400` | Serve stale entries on errors (s). |
| `cache.disk_dir` | `DAYMET_MCP_CACHE__DISK_DIR` | str \| null | unset | Optional gzip-JSON disk cache directory. |
| `limits.max_result_bytes` | `DAYMET_MCP_LIMITS__MAX_RESULT_BYTES` | int | `50000` | Result budget (fixed). |
| `limits.hard_max_result_bytes` | `DAYMET_MCP_LIMITS__HARD_MAX_RESULT_BYTES` | int | `200000` | Hard result cap (fixed). |
| `limits.max_years_per_point` | `DAYMET_MCP_LIMITS__MAX_YEARS_PER_POINT` | int | `46` | Years per point call. |
| `limits.pixel_mosaic_max_cells` | `DAYMET_MCP_LIMITS__PIXEL_MOSAIC_MAX_CELLS` | int | `121` | Cells via single-pixel. |
| `limits.pixel_mosaic_max_cell_years` | `DAYMET_MCP_LIMITS__PIXEL_MOSAIC_MAX_CELL_YEARS` | int | `605` | Cell-years via single-pixel per call. |
| `limits.earthdata_max_values` | `DAYMET_MCP_LIMITS__EARTHDATA_MAX_VALUES` | int | `25000000` | cells x days x variables (Earthdata). |
| `limits.tool_timeout_s` | `DAYMET_MCP_LIMITS__TOOL_TIMEOUT_S` | float | `120.0` | Per-tool wall clock (s). |
| `downloads.dir` | `DAYMET_MCP_DOWNLOADS__DIR` | str | `./daymet-downloads` | Download root (stdio only). |
| `downloads.max_bytes` | `DAYMET_MCP_DOWNLOADS__MAX_BYTES` | int | `524288000` | Bytes per call. |

<!-- END GENERATED CONFIG -->
