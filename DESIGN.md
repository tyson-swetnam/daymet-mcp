# daymet-mcp design

Status: design for v0.1.0, written 2026-11-15, before any code exists. This file becomes the repository's `DESIGN.md`.
Repository: `tyson-swetnam/daymet-mcp`, built locally in `/home/tswetnam/github/daymet-mcp` (owner decisions, 2026-11-15).

It is based on two research notes: `research-conventions.md` (conventions of idss-mesa/neon-mcp and ameriflux-mcp)
and `research-daymet-access.md` (live tests of every Daymet V4 R1 access path, without credentials). Labels used below:

- **[seen]**: a fact observed in those notes, in the S1 artefacts (`s1-artifacts/data-and-toolchains/daymet/`), or in eemt code.
- **[inferred]**: a reading or assumption that has not been verified.
- **[decision]**: a design choice made here. Each one is listed in §19.
- **[not run]**: something nobody has tested yet.

---

## 0. Purpose, scope, non-goals

daymet-mcp is an MCP server that fetches Daymet V4 R1 surface weather data when it is asked for: daily data, plus monthly
and annual summaries that the server computes. EEMT pipelines and AI agents can then get Daymet values on demand,
without managing data files by hand. The owner raised the question "is monthly precipitation a total or a mean?"
(owner decision Q4). In this server that question cannot come up, because every summary value carries its
aggregation method and units.

In scope (v0.1):
- a variable and metadata catalogue
- point daily time series
- point monthly and annual summaries, with explicit aggregation
- grid-cell lookup
- small-area subsets
- area downloads to disk (stdio only)
- citations
- resources and prompts

Non-goals (v0.1):
- reprojection or resampling to a user grid (EEMT already does this in `Tiff.py`)
- the sub-daily Puerto Rico product
- the station cross-validation product (2132)
- Daymet V4.0 or the Planetary Computer copy (V4.0 only, ends in 2020 [seen])
- the Earth Engine copy (needs an account)
- TESViS (fixed sites only, 9–27 s per request [seen])
- writing GeoTIFF (no GDAL dependency; see D14)
- MCP sampling, roots, logging/setLevel, SSE, sessions, tasks and elicitation

## 1. Names and package layout

Names follow the reference servers' pattern [seen: neon `registry.py` `NAME_RE`; amf D1]:

| Item | Value |
|---|---|
| Distribution / CLI | `daymet-mcp` (bare `daymet-mcp` = stdio) |
| Python package | `daymet_mcp` |
| Tool names | `^daymet_[a-z_]+$`, enforced at import by `register_tool` |
| URI scheme | `daymet://` |
| `_meta` keys | `io.daymet-mcp/surface`, `io.daymet-mcp/endpoints`, `io.daymet-mcp/stdioOnly`, `io.daymet-mcp/requiresToken`, `io.daymet-mcp/upstream`, `io.daymet-mcp/kind` |
| Env vars | `DAYMET_MCP_<SECTION>__<FIELD>` (`__` descends one level; lists are comma-separated) |
| User-Agent | `daymet-mcp/{__version__} (+https://github.com/idss-mesa)`. This is generic, as the safety rules require. It does not carry the owner's GitHub URL [decision D20]. |

Layout (neon §5, adapted; `daymet/` is the upstream package):

```
pyproject.toml uv.lock LICENSE NOTICE .gitignore .env.example config.yaml.example CHANGELOG.md
README.md CLAUDE.md AGENTS.md DESIGN.md RESEARCH.md zensical.toml Dockerfile docker-compose.yml server.json
.github/workflows/{ci,docs,release}.yml
scripts/{okf_validate,gen_llms_txt,postbuild_agent_surface}.py   (vendored, ruff-excluded)
scripts/{gen_tools_reference,gen_config_reference,record_fixtures}.py
docs/**                                   OKF v0.2 bundle
src/daymet_mcp/
  __init__.py  __main__.py  config.py  errors.py  logging.py  context.py  registry.py
  server.py                                the ONLY module that imports the MCP SDK
  instructions.py  resources.py  prompts.py  resources_static/*.md|*.json
  models/common.py                         ToolResultBase, Page, Source, shared Annotated types
  models/{catalog,point,area,cell,citation}.py
  daymet/
    client.py      one httpx.AsyncClient, host allow-list, retries, rate limits
    ratelimit.py   token buckets (local policy; upstream publishes no limits)
    cache.py       TTL+LRU, single-flight, stale-if-error, optional disk layer
    catalog.py     variable table, regions, aggregation rules, collection ids
    calendar.py    Daymet 365-day calendar (yday <-> date)
    lcc.py         pure-Python LCC forward/inverse (WGS84) + grid snapping
    single_pixel.py  request builder, parser, the four silent-failure guards
    cmr.py         latest-year discovery
    earthdata.py   OPeNDAP (Hyrax) index subsetting; optional extra [grid]
    aggregate.py   monthly/annual reductions
    writers.py     AAIGrid(.asc+.prj), CSV, NetCDF (NetCDF needs [grid])
  tools/__init__.py _common.py core.py catalog.py cell.py point.py area.py citation.py
  transport/{stdio,streamable_http,healthz}.py
tests/  (see §14)
```

## 2. MCP spec, SDK and features

- **Spec 2026-07-28, stateless core.** `protocolVersion` always comes from `mcp.types.LATEST_PROTOCOL_VERSION`; it is
  never written as a literal (neon D33) [seen].
- **SDK:** `mcp>=2.0,<3`, using the low-level `mcp.server.Server` with constructor callbacks, not `MCPServer`.
  `uv.lock` pins the newest 2.x at implementation time (the references lock 2.2.0 and 2.3.0 [seen]).
- **Python** `>=3.11`, with classifiers for 3.11–3.13. Build backend: hatchling. Runtime dependencies:
  - `httpx>=0.28,<1`
  - `pydantic>=2.7`
  - `pyyaml>=6`
  - `structlog>=24`
  - `anyio>=4`
  - `starlette>=0.40`
  - `uvicorn>=0.30`
- **Optional extra `[grid]`:** `numpy`, `h5netcdf`. It is needed for the Earthdata backend (reading NetCDF-4 subsets)
  and for NetCDF output. The default install has no numeric or geospatial dependencies [decision D13].
- **Dev extras:** pytest, pytest-asyncio, pytest-cov, hypothesis, jsonschema, ruff, mypy, types-PyYAML, and `pyproj`
  (dev only, for cross-checking `lcc.py`).
- **Docs extra:** `zensical>=0.0.60`, `pyyaml`.

| MCP feature | Use |
|---|---|
| Tools | 8 tools (§4), sorted by name. Membership depends on transport: `daymet_download_area` is stdio-only. |
| Structured output | Every tool declares an `outputSchema` (with `$schema` `https://json-schema.org/draft/2020-12/schema`) and returns the same compact JSON as `TextContent` and as `structuredContent`. |
| Annotations | Every tool carries all four hints plus a `title`. |
| Resources | Static guides, JSON references and 2 resource templates (§10). |
| Prompts | 3 (§10). |
| Cache hints | `public`, at the reference durations: `tools/list` 5 min, resources 1 h, `prompts/list` 24 h, `server/discover` 5 min. |
| Pagination | offset/limit inputs plus a `page` object in the result, not MCP cursors. |
| Elicitation, progress, sampling, roots, logging, SSE, sessions | Not used. CI greps `src/` for them and fails if it finds any (neon/amf) [decision D18]. |

## 3. Daymet facts the server encodes

### 3.1 Variables and aggregation (the core of the owner's question)

Daily units are from the V4 R1 daily guide, Table 1, and the single-pixel column labels [seen]. The ORNL monthly and
annual definitions are from the V4 R1 monthly and annual guides [seen, quoted in research-daymet-access §4]:

- prcp is a **total**.
- tmax, tmin, vp and swe are **means of daily values**.
- No monthly or annual product exists for srad or dayl.

| Variable | Daily value and units | Monthly default | Monthly units | Annual default | Annual units | Allowed alternative | In ORNL monthly/annual product |
|---|---|---|---|---|---|---|---|
| `prcp` | daily total precipitation, all forms as water equivalent, `mm/day` | **sum** | `mm/month` | **sum** | `mm/year` | none | yes, total (`monttl`) |
| `tmax` | daily maximum 2 m air temperature, `degC` | mean | `degC` | mean | `degC` | none | yes, mean |
| `tmin` | daily minimum 2 m air temperature, `degC` | mean | `degC` | mean | `degC` | none | yes, mean |
| `vp` | daily mean water vapour partial pressure, `Pa` | mean | `Pa` | mean | `Pa` | none | yes, mean |
| `swe` | snow water equivalent, `kg/m2` | mean | `kg/m2` | mean | `kg/m2` | `last` (value on the last Daymet day of the period, `kg/m2`) | yes, mean |
| `srad` | incident shortwave **averaged over the daylight period**, `W/m2` | mean | `W/m2` (daylight-period average) | mean | `W/m2` | `total`: Σ(srad·dayl)/1e6 → `MJ/m2/month` or `MJ/m2/year` (formula from the daily guide) | no |
| `dayl` | daylight duration, `s/day` | mean | `s/day` | mean | `s/day` | none | no |

**SWE choice [decision D7]:** the default is **mean**. This is the statistic the ORNL monthly and annual products
publish [seen], so a server value can be checked against, or swapped for, the official 2131/2130 files with the
same meaning. End-of-month SWE is a snapshot of a state variable. It is useful for snowmelt timing but depends on a
single day. It is available only on request (`aggregation_overrides: {"swe": "last"}`) and is always labelled `last`.

**srad:** the mean of daylight-average W m-2 keeps the upstream quantity. The `total` alternative is the energy
quantity that EEMT-style energy balances usually want. Both are labelled.

**Field labels** are machine-readable and repeat the aggregation and units. Examples:

- `prcp_monthly_total_mm`
- `tmax_monthly_mean_degC`
- `vp_annual_mean_Pa`
- `srad_monthly_mean_W_m2`
- `srad_monthly_total_MJ_m2`
- `swe_monthly_last_kg_m2`
- `dayl_monthly_mean_s`

Every summary output also lists each computed field in `source.derived` with the text
`"computed by daymet-mcp from Daymet daily V4 R1 (DOI 10.3334/ORNLDAAC/2129); not the ORNL monthly product (2131)"`.

### 3.2 Calendar

"All Daymet years, including leap years, have 1–365 days … December 31 is discarded from leap years" [seen in all three
guides; confirmed live: in 2024 Feb 29 is present and Dec 31 is absent; the 2020 S1 probe returned 2 rows for Dec 29–31].

`calendar.py` maps `yday` to a date:

- Non-leap years: the usual mapping.
- Leap years: yday 60 = Feb 29 and yday 365 = Dec 30.

Consequences, all stated in the output:

- Leap-year **December has 30 days** (`dayCount: 30`). The prcp sum covers Dec 1–30, and the server does not impute
  Dec 31.
- Leap-year February has 29 days.
- Annual sums and means cover 365 days.
- A request for `YYYY-12-31` in a leap year is refused with `invalid_argument`
  (`details.reason = "not_in_daymet_calendar"`).
- Every output carries `calendar: {"daysPerYear": 365, "rule": "leap years keep Feb 29 and drop Dec 31"}`.

### 3.3 Coverage, versions and collections

| Region | Bounding box (lon, lat) [seen, daily guide] | Daily years via single-pixel | Notes |
|---|---|---|---|
| `na` | -178.1333..-53.0567, 14.0749..82.9143 | 1980..latest | |
| `hi` | -160.3056..-154.772, 17.9539..23.5186 | 1980..latest | worked live at (21.3, -157.8) [seen] |
| `pr` | -67.9927..-64.1196, 16.8444..19.9382 | 1980..latest | Gridded PR starts in 1950. Single-pixel PR before 1980 is [not run], so v0.1 refuses years before 1980 everywhere [decision D8]. |

- **Latest year:** daily = 2025; monthly and annual = 2024 (CMR, sorted `-start_date`) [seen].
  - The server learns the latest year from CMR (no auth, 0.2–0.6 s [seen]) and caches it for 24 h. The configured
    fallback is `{daily: 2025}`.
  - The server never trusts single-pixel for this, because asking it for an unpublished year returns the whole record
    with HTTP 200 [seen].
- **Collections** [seen]:
  - daily `C2532426483-ORNL_CLOUD`, DOI 10.3334/ORNLDAAC/2129
  - monthly `C2532007210-ORNL_CLOUD`, DOI 2131
  - annual `C2531982907-ORNL_CLOUD`, DOI 2130
- **Version label:** outputs say `dataVersion: "4 R1"`, taken from the citation the service embeds (DOI 2129). The CSV
  header line still says "Daymet Software Version 4.0" [seen]. The server records that string in `notes` and does
  not use it as the version. If the embedded citation stops naming DOI 2129, the result carries `details.drift`.
- "All Daymet data are provisional and subject to revision" [seen]. This goes into the guide and into the `notes`
  of summary results.

### 3.4 Projection and grid

- **CRS:** `+proj=lcc +lat_1=25 +lat_2=60 +lat_0=42.5 +lon_0=-100 +x_0=0 +y_0=0 +ellps=WGS84 +units=m +no_defs`
  [seen, guides].
- **NA grid**, cell centres:
  - `x = -4560250 + 1000·col`, `y = 4984000 - 1000·row`
  - 7814 columns × 8075 rows
  - The constants match `scripts/download_seaz_daymet.py` in eemt [seen in code]. Cell centres at x ≡ 250 and
    y ≡ 0 (mod 1000) were confirmed by the TESViS corner and by the S1 probe [seen].
- **Snapping:** `col = floor((x + 4560750) / 1000)`, `row = floor((4984500 - y) / 1000)`. Each cell is ±500 m around
  its centre. The S1 edge probe supports this [seen, `grid.log`]: +480 m stays in the same cell and +520 m reaches the
  neighbour, in both x and y.
- **The service echoes the projected query point, not the cell centre.** A query at LCC (-574850, -687600) was reported
  as `-574850.02 -687600.04` [seen, `grid.log`]. The server therefore computes cell centres itself.
- **Hawaii and Puerto Rico** are reported in the same LCC [seen]. Hawaii x ≈ -5 643 437 lies west of the NA origin.
  Their mosaics' own origins and dimensions have not been read (they need granule metadata, behind EDL). In v0.1,
  `daymet_locate_cell` returns LCC coordinates for hi/pr and `cell: null` with a note [decision D9]. The hi/pr area
  tools work only through `backend=earthdata`, once that is verified.
- **`lcc.py`** is a pure-Python implementation of the Snyder (1987) ellipsoidal LCC formulas [decision D12]. Tests
  check it against values the service reported [seen]:
  - (35.802997, -106.624036) → (-575071.13, -688303.76)
  - (21.3, -157.8) → (-5643436.98, -258972.42)
  - a dev-only pyproj comparison over random points, with a 0.05 m tolerance.
- Finding for eemt, not fixed here: in `scripts/download_seaz_daymet.py`, `DAYMET_GRID` has `x_last = 3251750`
  together with `x_size = 7814`. Since -4560250 + 7813·1000 = 3252750, the derived `x_step` is 999.87 m, which shifts
  column indices by up to about one cell at the east edge [seen in code; arithmetic]. daymet-mcp uses `step = 1000`
  exactly.

## 4. Tools

### 4.0 Common rules (all tools)

- **Registration:** `@register_tool(name, title, description, input_model, output_model, surface, endpoints,
  read_only, destructive, idempotent, open_world, transports)`.
  - Descriptions are at most 600 characters and end with `Next: …`.
  - Handlers have the form `async (args, ctx) -> OutputModel`.
- **Inputs:**
  - pydantic, `extra="forbid"`, snake_case, every field described.
  - Unknown fields → `invalid_argument`, listing the valid argument names.
  - `variables` is an **enum** validated by the server. Upstream silently ignores unknown variables [seen].
- **Outputs:**
  - camelCase. Every model subclasses `ToolResultBase`, which provides `resolved[]`, `notes[]`, `nextSteps[]` (1–3
    concrete calls; for data tools the last one is `daymet_get_citation`) and
    `source{endpoints[], via, cached, derived[]}`.
  - `via` is one of `single-pixel`, `single-pixel-mosaic`, `earthdata-opendap`, `cmr`, `local`.
- **Every numeric series carries its units next to the values.** No bare numbers.
  - Daily values are rounded to 2 decimals, the CSV precision.
  - Aggregates are computed from the unrounded JSON floats and rounded to 3 decimals [decision D10].
  - A note states both rules.
- **Result `_meta`:** `io.daymet-mcp/upstream = {requests, cacheHits, rateLimitRemaining: null, rateLimitLimit: null,
  backend}`, merged with the SDK's `io.modelcontextprotocol/serverInfo`.
- **Tool `_meta`:** `surface`, `endpoints`, `stdioOnly`, `requiresToken` (`"optional"` for the area tools).
- **Size:** the result budget is 50 000 B of compact JSON. `fit_to_budget` trims the time axis from the tail and sets
  `page.truncatedReason = "budget"`. The hard cap is 200 000 B (`result_too_large`). Pre-flight size estimates (§6)
  refuse a call **before** any upstream request.

`Page` = `{total, returned, offset, limit, truncated, nextOffset, truncatedReason: "limit"|"budget"|null}`.

Shared input fragments (JSON Schema 2020-12; the published schemas inline these):

```json
{
  "lat": {"type": "number", "minimum": -90, "maximum": 90, "description": "Latitude, decimal degrees WGS84."},
  "lon": {"type": "number", "minimum": -180, "maximum": 180, "description": "Longitude, decimal degrees WGS84 (west negative)."},
  "variables": {"type": "array", "uniqueItems": true, "minItems": 1,
    "items": {"enum": ["dayl", "prcp", "srad", "swe", "tmax", "tmin", "vp"]},
    "description": "Daymet variables. Default: all seven."},
  "start_year": {"type": "integer", "minimum": 1980, "description": "First year (inclusive). Max = latest published year."},
  "end_year": {"type": "integer", "minimum": 1980, "description": "Last year (inclusive), >= start_year."},
  "offset": {"type": "integer", "minimum": 0, "default": 0, "description": "Index of the first time step to return."},
  "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 366, "description": "Max time steps to return."},
  "bbox": {"type": "object", "additionalProperties": false, "required": ["west", "south", "east", "north"],
    "properties": {"west": {"type": "number"}, "south": {"type": "number"}, "east": {"type": "number"}, "north": {"type": "number"}},
    "description": "WGS84 bounding box in decimal degrees; every Daymet cell whose centre falls inside is included."}
}
```

The upper bound on years (the latest published year) is checked at call time against the CMR value, because it changes
each spring. The error names the current bound.

### 4.1 `daymet_ping` (core)

Returns the server version, `protocolVersion`, transport, and backend status (`singlePixel: "available"`,
`earthdata: "configured" | "not_configured" | "disabled_in_http_mode" | "extra_missing"`). With `check_upstream=true`
it also returns one tiny live single-pixel request (2-day window) and its latency.

- Input: `{"check_upstream": {"type":"boolean","default":false}}`
- Annotations: `readOnlyHint=true, destructiveHint=false, idempotentHint=true, openWorldHint=true`
- Output: `{server:{name,version,protocolVersion,transport}, backends:{...}, upstream:{ok,latencyMs,status}|null}` plus
  the envelope.

### 4.2 `daymet_list_variables`

Returns:

- the §3.1 table
- regions with bboxes and year ranges
- the calendar rule
- the collections with DOIs and the latest year per product (from CMR, cached for 24 h; if CMR fails, the configured
  fallback with a note)
- the grid definition

Description draft: "List Daymet V4 R1 variables with daily units and the exact monthly/annual aggregation the server
uses (prcp = sum, others = mean), regions, year ranges, the 365-day calendar and collection DOIs. Next: call
daymet_get_point_summary or daymet_locate_cell."

- Input: `{}` (no arguments; `additionalProperties:false`).
- Annotations: `readOnlyHint=true, destructiveHint=false, idempotentHint=true, openWorldHint=true` (CMR).
- Output:

```json
{"variables": [{"name":"prcp","longName":"precipitation","dailyUnits":"mm/day","description":"...",
   "monthly":{"aggregation":"sum","units":"mm/month","fieldLabel":"prcp_monthly_total_mm"},
   "annual":{"aggregation":"sum","units":"mm/year","fieldLabel":"prcp_annual_total_mm"},
   "alternatives":[], "inOrnlSummaryProducts":true}],
 "regions":[{"code":"na","bbox":{...},"firstYear":1980,"latestDailyYear":2025}],
 "calendar":{"daysPerYear":365,"rule":"leap years keep Feb 29 and drop Dec 31"},
 "collections":[{"product":"daily","conceptId":"C2532426483-ORNL_CLOUD","doi":"10.3334/ORNLDAAC/2129","latestYear":2025,"latestYearSource":"cmr|fallback"}],
 "grid":{"crs":"+proj=lcc ...","xFirstCentreM":-4560250,"yFirstCentreM":4984000,"stepM":1000,"nCols":7814,"nRows":8075}}
```

### 4.3 `daymet_locate_cell`

A pure computation (no network) that maps lat/lon to the Daymet LCC cell.

- Input:
  `{"lat":…, "lon":…}`, both required.
- Annotations: `readOnlyHint=true, destructiveHint=false, idempotentHint=true, openWorldHint=false`
- Output:

```json
{"region":"na|hi|pr|null", "inCoverage":true,
 "query":{"lat":35.802997,"lon":-106.624036,"xM":-575071.13,"yM":-688303.76},
 "cell":{"col":3985,"row":5672,"xCentreM":-575250.0,"yCentreM":-688000.0,
         "latCentre":35.805702,"lonCentre":-106.626365,"distanceToCentreM":352.5},
 "crs":"+proj=lcc +lat_1=25 +lat_2=60 +lat_0=42.5 +lon_0=-100 +x_0=0 +y_0=0 +ellps=WGS84 +units=m +no_defs",
 "gridDefinition":{"region":"na","xFirstCentreM":-4560250,"yFirstCentreM":4984000,"stepM":1000,"nCols":7814,"nRows":8075}}
```

The example values are the S1 DEM centre and its cell [seen in `grid.log`; `distanceToCentreM` is arithmetic].
- A point outside every region bbox gives `inCoverage:false`, `region:null`, `cell:null` and a note. This is not an
  error.
- For hi/pr, `cell` is `null` (D9).
- A point inside a bbox but over the ocean cannot be detected offline. The data tools report it as
  `not_found` / `off_grid`.

### 4.4 `daymet_get_point_daily`

A daily time series for the Daymet cell that contains the point, from the single-pixel API.

- Input:

```json
{"type":"object","additionalProperties":false,"required":["lat","lon"],
 "properties":{"lat":{}, "lon":{}, "variables":{},
  "years":{"type":"array","uniqueItems":true,"minItems":1,"maxItems":46,"items":{"type":"integer","minimum":1980},
           "description":"Whole years. Give either years or start_date+end_date."},
  "start_date":{"type":"string","format":"date","description":"YYYY-MM-DD, inclusive; must exist in the Daymet calendar."},
  "end_date":{"type":"string","format":"date","description":"YYYY-MM-DD, inclusive."},
  "offset":{}, "limit":{}}}
```

Exactly one of `years` or (`start_date`, `end_date`) must be given; anything else is `invalid_argument`.

- Annotations: `readOnlyHint=true, destructiveHint=false, idempotentHint=true, openWorldHint=true`
- Output:

```json
{"location":{"requestedLat":..,"requestedLon":..,"region":"na","cell":{"col":..,"row":..,"xCentreM":..,"yCentreM":..},
             "tile":"11197","elevationM":2545,"elevationSource":"single-pixel header (Daymet 1 km cell elevation)"},
 "calendar":{...}, "dataVersion":"4 R1", "doi":"10.3334/ORNLDAAC/2129",
 "time":{"date":["2020-01-01",...],"year":[2020,...],"yday":[1,...]},
 "series":{"prcp":{"units":"mm/day","description":"daily total precipitation (water equivalent)","values":[0.0,...]},
           "tmax":{"units":"degC","values":[...]}},
 "page":{...}, "resolved":[...], "notes":[...], "nextSteps":[...], "source":{...}}
```

`elevationSource` is [inferred] to be the Daymet 1 km DEM value. The header says "Elevation: 2545 meters" [seen].

**Guards against upstream silent failures** [seen behaviours → decision D6]:

1. Variables are validated locally (upstream ignores unknown ones).
2. Years must be ≥ 1980 and ≤ the latest year (an unpublished year or a pre-1980 start returns the **entire record**
   with HTTP 200).
3. After every response, the server checks that the set of years returned equals the set requested and that there
   are 365 rows per year (or the exact count for a date window). Any mismatch → `upstream_error` with
   `details.drift = {expectedYears, returnedYears, expectedRows, returnedRows}`.
4. Leap-year Dec 31 → `invalid_argument` (§3.2).

**Upstream call:** one GET per cell for the requested years, **always with all 7 variables**, in JSON format
[decision D11]. A year of all variables is about 46 KB and 0.6 s [seen]. The cost is the same as a single variable,
and the cache (§9) then serves any variable mix for that cell and year.

### 4.5 `daymet_get_point_summary`

Monthly or annual summaries at a point, computed from daily data. This also covers 2025, which the ORNL monthly
product does not have yet [seen].

- Input:

```json
{"type":"object","additionalProperties":false,"required":["lat","lon","period","start_year","end_year"],
 "properties":{"lat":{}, "lon":{}, "variables":{},
  "period":{"enum":["monthly","annual"],"description":"monthly = calendar months; annual = Daymet 365-day year."},
  "start_year":{}, "end_year":{},
  "months":{"type":"array","uniqueItems":true,"items":{"type":"integer","minimum":1,"maximum":12},
            "description":"Optional month filter (monthly only)."},
  "aggregation_overrides":{"type":"object","additionalProperties":false,
    "properties":{"swe":{"enum":["mean","last"]},"srad":{"enum":["mean","total"]}},
    "description":"Only swe and srad have alternatives; every other variable's aggregation is fixed (see daymet_list_variables)."},
  "offset":{}, "limit":{}}}
```

- Annotations: `readOnlyHint=true, destructiveHint=false, idempotentHint=true, openWorldHint=true`
- Output:

```json
{"location":{...}, "calendar":{...}, "period":"monthly",
 "periods":[{"label":"2024-12","year":2024,"month":12,"dayCount":30,"complete":true,"firstDate":"2024-12-01","lastDate":"2024-12-30"}],
 "series":{
   "prcp":{"aggregation":"sum","dailyUnits":"mm/day","units":"mm/month","fieldLabel":"prcp_monthly_total_mm",
           "definition":"sum of daily prcp over the Daymet days in the month","values":[23.417]},
   "tmax":{"aggregation":"mean","dailyUnits":"degC","units":"degC","fieldLabel":"tmax_monthly_mean_degC",
           "definition":"arithmetic mean of daily tmax over the Daymet days in the month","values":[6.112]}},
 "page":{...}, "notes":["Leap-year December has 30 days in Daymet (Dec 31 is not in the product); totals cover Dec 1-30.", "..."],
 "source":{"via":"single-pixel","derived":["series.prcp","series.tmax"],"endpoints":["GET daymet.ornl.gov/single-pixel/api/data"],"cached":false}}
```

The numbers above are placeholders that show the shape only.

- **Missing or NaN daily values:** the period gets `complete:false` and `value:null`. The server never imputes. No gaps
  are expected inside coverage [inferred].
- **No nodata substitution.** Means are arithmetic over the days present. Sums do not rescale to a nominal month length.

### 4.6 `daymet_get_area`

A small-area subset returned in the result (no files). It is read-only and available on both transports.

- Input:

```json
{"type":"object","additionalProperties":false,"required":["bbox","variables","start_year","end_year","temporal"],
 "properties":{"bbox":{}, "variables":{}, "start_year":{}, "end_year":{},
  "temporal":{"enum":["daily","monthly","annual"]},
  "aggregation_overrides":{},
  "include_elevation":{"type":"boolean","default":false,"description":"Add the Daymet 1 km cell elevation grid (m)."},
  "backend":{"enum":["auto","single_pixel","earthdata"],"default":"auto",
             "description":"auto = single_pixel when within its cell limit, else earthdata if a token is configured."},
  "offset":{}, "limit":{}}}
```

- Annotations: `readOnlyHint=true, destructiveHint=false, idempotentHint=true, openWorldHint=true`
- Output:

```json
{"grid":{"region":"na","crs":"+proj=lcc ...","colRange":[3982,3988],"rowRange":[5669,5675],
         "xCentresM":[...],"yCentresM":[...],"shape":{"time":12,"rows":7,"cols":7},"cellOrder":"row-major, north to south, west to east"},
 "time":{"labels":["2020-01",...],"dayCount":[31,...]},
 "series":{"prcp":{"aggregation":"sum","units":"mm/month","fieldLabel":"prcp_monthly_total_mm","values":[[[...]]]}},
 "elevationM":[[...]] , "backend":"single-pixel-mosaic", "cellsRequested":49,
 "calendar":{...}, "page":{...}, "notes":[...], "nextSteps":[...], "source":{...}}
```

`values` is indexed `[time][row][col]`. A missing cell is `null`.

**Backends:**

- **`single_pixel` (credential-free).**
  - Each cell centre is converted to lat/lon with `lcc.py` and queried once (all variables, all requested years). This
    is the method validated in S1 [seen: centre and ±400/450 m queries returned identical data; neighbours differed].
  - Bounded by `limits.pixel_mosaic_max_cells` and `limits.pixel_mosaic_max_cell_years` (§6).
  - Cells that come back off-grid (ocean) are `null`, with a count in `notes`.
- **`earthdata` (EDL token required; experimental until a credentialed live test passes [not run]).**
  - Hyrax OPeNDAP index subsetting on the daily granules:
    `https://opendap.earthdata.nasa.gov/collections/C2532426483-ORNL_CLOUD/granules/Daymet_Daily_V4R1.daymet_v4_daily_<region>_<var>_<year>.nc`
    with a DAP constraint on `[time][y][x]` index ranges, response as NetCDF-4. This is the URL form the existing eemt
    script uses [seen in code]; its behaviour after login is [not run].
  - Monthly and annual values are computed by the same `aggregate.py` from the daily subset, so both backends give
    identical definitions and the latest year [decision D5].
  - Needs the `[grid]` extra.
- **Without a token**, when `auto` would need earthdata, or `backend=earthdata` is given: `auth_required` (§8).

**In-result size:** the daily area volume exceeds the budget almost at once. A 7×7 grid × 1 variable is about 0.3 KB
per day. The time axis is paged, and `nextSteps` suggests `temporal=monthly` or `daymet_download_area`.

### 4.7 `daymet_download_area` (stdio only)

Same inputs as `daymet_get_area` (except `offset`/`limit`), plus:

```json
{"format":{"enum":["aaigrid","csv","netcdf"],"default":"aaigrid",
   "description":"aaigrid: one .asc+.prj per variable and time step (GDAL-readable, no extra deps); csv: one long table; netcdf: one file per variable and year (needs the [grid] extra)."},
 "subdir":{"type":"string","pattern":"^[A-Za-z0-9._-]{1,64}$","description":"Folder under the configured downloads.dir."},
 "overwrite":{"type":"boolean","default":false}}
```

- Annotations: `readOnlyHint=false, destructiveHint=false, idempotentHint=true, openWorldHint=true`.
  - Deterministic file names mean the same inputs produce the same files.
  - Existing files are refused unless `overwrite=true`, and in that case are replaced with identical content.
- Tool `_meta`: `io.daymet-mcp/stdioOnly: true`. The tool is absent from `tools/list` over HTTP. A call to it over HTTP
  gets `not_available_in_http_mode` (neon D3, amf D18).
- **Confinement:** writes go only under `downloads.dir`. Paths are resolved with symlinks refused, and anything outside
  the directory is rejected.
- **Output:**
  - `{directory, files:[{path, format, variable, label, aggregation, units, bytes, sha256}], grid:{…}, manifestPath}`
  - `manifest.json` records the request, the server version, the backend, the upstream URLs (with any token removed),
    the aggregation table and the citation text.
- **File names:** `daymet_<region>_<var>_<monthly_total|monthly_mean|annual_total|annual_mean|daily>_<label>_c<col0>-<col1>_r<row0>-<row1>.<ext>`
- **`.prj`:** contains the ESRI WKT of the Daymet LCC, also served at `daymet://reference/grid`.
- **AAIGrid:** written with `xllcorner = xCentre_min - 500`, `yllcorner = yCentre_min - 500`, `cellsize 1000` and
  `NODATA_value -9999`.

### 4.8 `daymet_get_citation`

Rendered locally from templates in `resources_static/citing-daymet.md`, whose docs twin is
`docs/about/citing-daymet.md` (neon D23, amf D9).

- Input:

```json
{"type":"object","additionalProperties":false,
 "properties":{
  "products":{"type":"array","uniqueItems":true,"items":{"enum":["daily","monthly","annual"]},"default":["daily"]},
  "access":{"type":"array","uniqueItems":true,"items":{"enum":["single_pixel","earthdata"]},"default":["single_pixel"]},
  "variables":{},
  "include_method_papers":{"type":"boolean","default":true},
  "accessed_on":{"type":"string","format":"date","description":"Default: today (UTC)."}}}
```

- Annotations: `readOnlyHint=true, destructiveHint=false, idempotentHint=true, openWorldHint=false`
- Output: `{citations:[{role:"dataset"|"tool"|"method", requirement:"required"|"recommended", text, doi, doiUrl, bibtex}],
  accessedOn, dataPolicyUrl, notes}`.

Citation rules:

- **Dataset (required).** The daily citation, as in the daily user guide [seen]: Thornton, M.M., R. Shrestha, Y. Wei,
  P.E. Thornton, and S-C. Kao. 2022. *Daymet: Daily Surface Weather Data on a 1-km Grid for North America, Version 4
  R1.* ORNL DAAC. https://doi.org/10.3334/ORNLDAAC/2129.
  - **Server-computed monthly or annual values cite 2129**, because the source data are the daily product. A note says
    they are not the 2131/2130 products.
  - 2131/2130 are cited only for `products` that were read from those collections (not in v0.1).
- **Tool (required when single-pixel was used):** Thornton, M.M., and R. Devarakonda. 2011. Daymet Single Pixel
  Extraction Tool. https://doi.org/10.3334/ORNLDAAC/2361 [seen].
- **Method (recommended):** Thornton et al. 2021, *Scientific Data* 8:190, https://doi.org/10.1038/s41597-021-00973-0,
  and Thornton, Running & White 1997, *J. Hydrology* 190:214–251, https://doi.org/10.1016/S0022-1694(96)03128-9; the
  citations page names both as the general methods reference [seen; added after review].
  When `srad` or `vp` are among the variables, add Thornton et al. 2000 (AFM 104:255–271) and Thornton & Running 1999
  (AFM 93:211–228), as daymet.ornl.gov/citations asks [seen].
- **Author discrepancy:** the citation embedded in the single-pixel response adds B.E. Wilson; the user guide does not
  [seen]. The server uses the user-guide form and mentions the difference in `notes` [decision D16].

## 5. Errors

Tool failures are `CallToolResult(isError=true)` with `structuredContent = {"error": {code, message, details, hint?}}`.
Only protocol faults are JSON-RPC errors (SDK). Tracebacks never reach the wire; an unexpected exception becomes
`internal_error` with `details.correlationId`. Codes reuse the reference vocabulary, with the specifics in
`details.reason` (amf D24); the final list is aligned with amf `errors.py` at implementation.

| Code | When (reason examples) |
|---|---|
| `invalid_argument` | Schema violation, unknown field, both or neither of years/dates, `end_year < start_year`, year > latest (`details.latestYear`), year < 1980, `not_in_daymet_calendar`, bbox with west ≥ east, `out_of_coverage` (point or bbox outside every region) |
| `not_found` | `off_grid`: upstream HTTP 400 "Daymet Tile was not found" [seen]; unknown resource URI (JSON-RPC -32602 with `didYouMean`, neon D32) |
| `auth_required` | `token_missing` (earthdata needed, no token configured), `token_rejected` (EDL 401) |
| `upstream_forbidden` | EDL 403 (e.g. the account has not accepted the application) [inferred] |
| `rate_limited` | upstream 429 after retries (`details.retryAfterS`) |
| `upstream_error` | 4xx other than the above; unparseable body; `drift` (year/row mismatch, missing keys, citation no longer DOI 2129) |
| `upstream_unavailable` | 5xx or transport errors after 3 attempts; timeout |
| `feature_unavailable` | `extra_missing` (the `[grid]` extra is not installed), `region_cells_unverified` (hi/pr cell indices, D9) |
| `not_available_in_http_mode` | download tool, or the earthdata backend over HTTP when not enabled |
| `query_too_large` | Pre-flight estimate over a limit. `details = {limit, limitName, requested, unit, suggestion}` |
| `result_too_large` | Over the 200 000 B hard cap after trimming |
| `download_limit_exceeded` | Download bytes estimate > `downloads.max_bytes` |
| `unknown_tool`, `internal_error` | as in the reference |

Example `auth_required` message, written so that it never echoes a token value:
"This request needs gridded Daymet data from NASA Earthdata (area of 900 cells exceeds the credential-free limit of 121
cells). No Earthdata token is configured. Set the environment variable DAYMET_MCP_EARTHDATA__TOKEN before starting the
server (stdio), or reduce the bbox."

## 6. Limits

All limits can be set in the config, below a hard ceiling. Every refusal states the limit, the requested amount and a
smaller alternative.

| Limit | Default | Ceiling | Why |
|---|---|---|---|
| Result budget / hard cap | 50 000 B / 200 000 B | fixed | reference convention |
| Years per point call | 46 (full record) | 46 | One upstream GET returns the full record in 2.4 s / 0.9 MB [seen] |
| `limit` (time steps per page) | 366 | 1000 | |
| `pixel_mosaic_max_cells` | 121 (11×11 km) | 400 | 1 GET per cell. At 2 req/s, 121 cells take about 60 s, inside the call timeout [inferred] |
| `pixel_mosaic_max_cell_years` | 605 (e.g. 121 cells × 5 yr) | 2000 | About 46 KB per cell-year upstream [seen], so the default is about 28 MB per call |
| `earthdata_max_values` (cells × days × variables) | 25 000 000 (≈100 MB float32) | 200 000 000 | [decision] |
| `downloads.max_bytes` per call | 500 MB | 5 GB | |
| Per-tool wall clock | 120 s | 600 s | → `upstream_unavailable` (`reason: timeout`) |
| HTTP request body (hosted) | 1 MiB | fixed | reference convention |

**Upstream politeness [decision D19].** Upstream publishes no limits (no `X-RateLimit-*` or `Retry-After` seen [seen]),
so the server applies its own:

| Host group | Rate | Concurrency |
|---|---|---|
| single-pixel | 2 req/s | 4 |
| CMR | 1 req/s | 2 |
| Earthdata | 2 req/s | 2 |

Retry policy: 429 honours `Retry-After`; 5xx and transport errors back off as `0.5·2^n` plus jitter, with at most 3
attempts. Only GET and HEAD are allowed.

## 7. Upstream client

- One `httpx.AsyncClient` per process, with `follow_redirects=False`. Redirects are followed manually, one hop at a
  time, and only to allow-listed hosts.
- Allow-listed hosts:
  - `daymet.ornl.gov`
  - `cmr.earthdata.nasa.gov`
  - `opendap.earthdata.nasa.gov`
  - `urs.earthdata.nasa.gov`
  - `data.ornldaac.earthdata.nasa.gov`
- The `Authorization` header is attached **only** to EDL hosts (`opendap.earthdata.nasa.gov`, `urs.earthdata.nasa.gov`,
  `data.ornldaac.earthdata.nasa.gov`). It is dropped on any hop to another host, for example a pre-signed S3 or
  CloudFront location [decision D15].
- Timeouts: connect 10 s, read 60 s. `max_connections=8`. Test seams for injecting a transport, clock and sleep.
- **Single-pixel parser:**
  - Parses the JSON keys `loc`, `Tile`, `Elevation`, `LCC`, `citation`, `data{year, yday, "<var> (<units>)"}` [seen].
  - The units in each column key are checked against the catalogue (e.g. `prcp (mm/day)`, `vp (Pa)`). A mismatch is
    reported as drift. **The server never silently relabels units.**
- **CMR:** `granules.umm_json?collection_concept_id=…&sort_key=-start_date&page_size=1` gives the latest year per
  product.

## 8. Credentials (Earthdata)

- **Only source:** the environment variable `DAYMET_MCP_EARTHDATA__TOKEN`, holding an EDL user token. It is stored as a
  pydantic `SecretStr` [decision D15]. Not accepted from:
  - CLI flags
  - YAML (a `token` key in YAML is a `ConfigError` that names the setting without echoing it)
  - MCP arguments
  - HTTP headers
- **Never read:** `~/.netrc`, `~/.urs_cookies`, `EARTHDATA_USERNAME`/`PASSWORD`. The existing eemt script uses
  `curl --netrc` and cookies [seen in code]; the server deliberately does not.
- **Never logged or echoed:**
  - The token is registered with the `redact_secrets` structlog processor.
  - httpx and httpcore loggers are forced to WARNING.
  - Error messages and `details` never include request headers.
  - `--print-config` shows `"***"` (set) or `null`.
  - Download manifests strip query strings that look like credentials.
- **Sent as** `Authorization: Bearer <token>` to EDL hosts. That Hyrax and the protected HTTPS endpoints accept bearer
  tokens is [inferred from Earthdata documentation; not run]. A credentialed live test (`network and edl` markers,
  §14) must pass before the backend loses its "experimental" label.
- **Hosted HTTP:** the earthdata backend is **disabled** unless the operator sets `earthdata.allow_in_http_mode=true`.
  If that is set, every anonymous caller can use the operator's EDL quota, and the docs page says so. There is no
  per-request token header in v0.1 [decision D17]. The task requires env-only credentials, so there is none of neon's
  `X-API-Token`.

## 9. Caching

- **In-memory TTL+LRU cache**, with single-flight per key and stale-if-error of 24 h (neon `cache.py`).
- **Single-pixel key:** `(region, col, row, year)` → the parsed 365-row record of all 7 variables plus header metadata.
  The key is the **cell, not lat/lon**, so nearby points share entries.
  - A multi-year request fetches only the missing years. Years are fetched as one `years=` list, so the call stays a
    single GET.
  - TTL is 7 days. Daymet years change only through revisions; data are "provisional" [seen].
  - Maximum 20 000 cell-years, about 160 MB in parsed form [inferred estimate].
- **CMR latest-year:** TTL 24 h.
- **Optional disk layer** (`cache.disk_dir`; default off; amf D22): atomic writes of gzip JSON per cell-year. A disk
  error never fails a call. Disk caching is off over HTTP unless a volume is configured.
- **Earthdata subsets:** never cached in memory beyond the call. With a disk cache configured, per-(granule, index
  window) NetCDF files are kept.
- **Results report** `source.cached` and `_meta …/upstream.cacheHits`. The cache never changes values. Aggregates are
  recomputed from cached daily data.

## 10. Resources, prompts, instructions

Resources (`_meta io.daymet-mcp/kind`):

| URI | Kind | Content |
|---|---|---|
| `daymet://guide/overview` | static md | What Daymet is, backends, when credentials are needed |
| `daymet://guide/aggregation` | static md | §3.1 + §3.2 rules, including "monthly prcp = total of daily values, mm/month" |
| `daymet://guide/citing-daymet` | static md | Citation templates (source for `daymet_get_citation`) |
| `daymet://guide/earthdata-credentials` | static md | How to create an EDL token and set the env var; security notes |
| `daymet://reference/variables` | static json | The variable/aggregation table |
| `daymet://reference/grid` | static json | proj4, ESRI WKT, NA grid definition, region bboxes |
| `daymet://cell/{lat}/{lon}` | template, derived | → `daymet_locate_cell` |
| `daymet://point/{lat}/{lon}/monthly/{year}` | template, derived | → `daymet_get_point_summary` (all variables, one year) |

An unknown URI returns `-32602` with `data={"code":"not_found","didYouMean":[…]}`.

Prompts (neon style, prefixed, one user message, arguments validated):

- `daymet_site_climate(lat, lon, start_year, end_year)`: locate the cell, get monthly summaries, describe climate
  normals, and cite.
- `daymet_eemt_inputs(west, south, east, north, year)`: locate the bbox, check the size against limits, then
  `daymet_download_area` with monthly tmin/tmax/prcp/vp and elevation, and cite.
- `daymet_monthly_precip_check(lat, lon, year)`: show daily prcp and the monthly totals side by side, and explain
  sum vs mean.

`SERVER_INSTRUCTIONS` (≤ 1 200 chars) must say:

- Daymet V4 R1, 1 km, North America, Hawaii and Puerto Rico, 1980 to the latest year.
- Point data needs no login; large areas need an Earthdata token set by the operator.
- Monthly and annual prcp are sums (mm/month, mm/year); the other variables are means unless overridden; every field
  states its aggregation.
- Every year has 365 days (leap years drop Dec 31).
- Cite with `daymet_get_citation`.

## 11. Transports

As in neon (§4 of the conventions note):

- **stdio** is the default. Logs go to stderr; a test asserts that stdout carries only protocol framing.
- **Stateless Streamable HTTP** at `/mcp`:
  - `stateless_http=True`, body cap 1 MiB.
  - `/healthz` returns `{"status":"ok","version","protocolVersion","transport":"http"}`.
  - `/readyz` returns 503 while prewarming (the CMR latest-year lookup) and 200 after it, `degraded` if CMR failed.
  - `GET`/`DELETE /mcp` → 405.
  - DNS-rebinding protection via `public_base_url`, `allowed_hosts`, `allowed_origins`.
- **Hosted HTTP auth: no OAuth/OIDC**, as in the reference. The server holds no user data, so anonymous read access is
  the model.
  - The download tool is not offered over HTTP.
  - The earthdata backend is off over HTTP by default (§8).
  - Deployers who need access control put the server behind a reverse proxy; `docs/deploy/security.md` explains this.
- **Docker:**
  - Two stages from `python:3.13-slim`, **pinned by digest**, with a pinned `uv` image, also by digest.
  - Non-root uid 10001. Env selects HTTP on `0.0.0.0:8080`. `HEALTHCHECK` on `/healthz`.
  - Compose publishes `127.0.0.1:8080:8080` only.
  - Local builds in this work are tagged `eemt-work/daymet-mcp:<tag>` and run with `--user "$(id -u):$(id -g)"`
    (safety rules).

## 12. Configuration

Precedence: **CLI flag > env > YAML (`--config`) > defaults**. `.env` is not loaded automatically
(`uv run --env-file .env`). The CLI offers `--check` (offline: config + schema self-test; `--check --live` adds one
`daymet_ping(check_upstream=true)`), `--print-config` (redacted) and `--version`. Config errors are value-free and exit
with code 2 (amf D32). The settings table in `docs/getting-started/configuration.md` is generated.

| Section | Fields (defaults) |
|---|---|
| `server` | `transport` (stdio), `host` (127.0.0.1), `port` (8080), `public_base_url`, `allowed_hosts`, `allowed_origins`, `dns_rebinding_protection` (true), `json_response` (true), `log_level` (INFO), `instructions_extra` |
| `daymet` | `single_pixel_url` (`https://daymet.ornl.gov/single-pixel/api/data`), `cmr_url` (`https://cmr.earthdata.nasa.gov/search`), `latest_year_fallback` (daily 2025), `first_year` (1980) |
| `earthdata` | `token` (**env only**), `opendap_url` (`https://opendap.earthdata.nasa.gov/collections`), `allow_in_http_mode` (false) |
| `cache` | `max_cell_years` (20000), `ttl_s.pixel` (604800), `ttl_s.cmr` (86400), `stale_if_error_s` (86400), `disk_dir` (null) |
| `limits` | as in §6 |
| `downloads` | `dir` (`./daymet-downloads`, resolved to absolute at start), `max_bytes` (500 MB) |

## 13. Logging

- structlog: a console renderer on stderr (stdio), JSON with `request_id` (HTTP).
- Events:
  - `daymet.http {host, path, status, ms, attempt}`. Query strings are logged with lat/lon rounded to 3 decimals.
    The token is never logged.
  - `tool.call {tool, ms, ok, code, result_bytes, upstream_requests, cache_hits, request_id}`.
- `redact_secrets` masks credential-like keys and the registered token value.

## 14. Testing

Hermetic by default. `addopts = "-ra -m 'not network'"`.

1. **Unit tests with recorded fixtures.**
   - `tests/fixture_router.py` is an `httpx.MockTransport` that replays fixtures, records `router.calls` and **fails
     the test on any unrouted request**.
   - Fixtures live in `tests/fixtures/<host>/<path>_<status>_<hash>.json` with a `manifest.json` entry for each
     (`key, status, contentType, transform, origin, recordedOn`).
   - They are recorded by `scripts/record_fixtures.py record` from real GETs, then shrunk and scrubbed.
     `scripts/record_fixtures.py check` runs in CI and checks:
     - each file ≤ 64 KB, total ≤ 1 MB
     - only allow-listed hosts
     - no headers carrying credentials
   - Planned fixtures:
     - single-pixel JSON at one NA cell for **2020** (leap year) and **2023**, all variables (~46 KB each [seen size])
     - a 3×3 mosaic for 2020 with `prcp` only (9 small files)
     - Hawaii and Puerto Rico 2-day windows
     - off-grid 400
     - `vars=foo` → all-variable response (shrunk)
     - `years=2026` → full-record response, **truncated** and marked `transform:"truncated"`, to test the year-set guard
     - a CMR latest-granule response per collection
     - the EDL 302 → 401 chain (headers only)
   - The OPeNDAP NetCDF-4 subset cannot be recorded without credentials. It is a **hand-built** synthetic fixture,
     flagged `origin:"synthetic"`, until a credentialed recording replaces it.
   - **Fixture data licence:** these are Daymet data. NOTICE and the manifest carry the DOI and the data terms (§16).
2. **Science tests.**
   - Calendar: yday ↔ date for leap and non-leap years; leap Dec has 30 days; Feb 29 is present.
   - Aggregation golden values from the 2020 fixture, computed by an independent straightforward loop in the test,
     including leap December (30 days).
   - Hypothesis properties:
     - annual prcp sum = Σ monthly sums
     - annual mean = day-weighted mean of monthly means
     - `srad total` = Σ srad·dayl / 1e6
   - LCC: round trip; the service-reported points (§3.4); the S1 edge cases (±480/520 m, `grid.log`); a dev-only
     pyproj comparison.
3. **Contract tests against the MCP SDK.**
   - In-process client session (the SDK's in-memory client/server pair), plus an ASGI harness for HTTP and a real stdio
     subprocess.
   - `tests/test_spec_conformance_2026_07_28.py` checks:
     - `tools/list` sorted and size-bounded (measured × 1.25)
     - every input and output schema valid under JSON Schema 2020-12
     - every `structuredContent` validates against its `outputSchema` (via `call_ok`/`call_err`)
     - text and structured content are equal
     - annotations and `_meta` present
     - result `_meta` contains both `io.daymet-mcp/upstream` and serverInfo
     - cache hints
     - `server/discover`
     - stateless behaviour in both eras
     - `-32020`/`-32022` handling
     - host allow-list
     - the download tool absent over HTTP
     - `-32602` with `didYouMean`
4. **Security tests.**
   - With a dummy token value set, assert that it never appears in logs, errors, `structuredContent`, manifests or
     `--print-config`.
   - `Authorization` is absent on redirects to non-EDL hosts and on all daymet.ornl.gov and CMR requests.
   - A YAML `token` key → ConfigError without the value.
   - Download path traversal and symlinks are refused.
5. **Live tests: marker `network`** [decision D21; neon calls its marker `live`, and this task asks for `network`].
   - One per tool, run with `pytest -m network`. They diff key sets against the fixtures to detect drift, and keep
     volume small (single pixels, ≤ 3×3 mosaics, 2-day windows).
   - `-m "network and edl"` also requires `DAYMET_MCP_EARTHDATA__TOKEN` and is skipped otherwise.
   - Nightly or manual in CI, never on PRs.
   - Also live: a single-pixel PR request for 1979, to settle D8.
6. `test_integration_meta.py`: every tool has a unit test and a live test.
7. Coverage `fail_under = 85`, `mypy --strict src`, ruff `E,F,I,UP,B,SIM,S,RUF`, line length 100.

## 15. Docs, CI, release

- **Docs:** OKF v0.2 bundle under `docs/`, built with Zensical `--strict`.
  - Frontmatter rules as in neon (`title`, `description` of 50–160 chars, `type`, `tags`,
    `generated{by,at}`, `sources[]`, `stale_after` for upstream facts; never `verified:`).
  - Sections: getting-started (install, quickstart, clients, configuration, earthdata-credentials), tools (generated
    `reference.md`, aggregation, resources-and-prompts), mcp, deploy, develop, about (ai-agents, citing-daymet, license).
  - `docs/log.md`, plus generated and committed `docs/llms.txt` and `docs/llms-full.txt`, with a CI drift check.
  - `AGENTS.md`, `CLAUDE.md`, `DESIGN.md` (this file) and `RESEARCH.md` (the verified facts from the two research
    notes) at the root.
- **CI** (written, not pushed in this work):
  - `ci.yml`: py3.11–3.13 matrix, macOS subset, a "MCP 2026-07-28 conformance" job, and a nightly `network` job.
  - `docs.yml`: OKF validation, drift check, Pages deploy.
  - `release.yml`: tag → PyPI trusted publishing. It checks that tag = `__version__` = `server.json` and that
    `CHANGELOG.md` has a dated entry.
- `server.json` for the MCP registry, with the env var `DAYMET_MCP_EARTHDATA__TOKEN` marked `isSecret: true`. The
  registry name depends on the final GitHub owner.
- No GitHub repository is created and nothing is pushed by this work. Creating and pushing the repo happens only after
  the build and an independent review, as the owner decided.

## 16. Licence and data terms

- **Code:** MIT (`license = "MIT"`, `license-files = ["LICENSE", "NOTICE"]`), as in the reference servers. **Docs:**
  CC BY 4.0.
  - Every source file starts with SPDX lines: `SPDX-License-Identifier: MIT` plus a `SPDX-FileCopyrightText` line.
  - The copyright holder is an **open owner decision** (O1). The reference servers name "The Regents of the University
    of New Mexico"; the eemt rule names the owner, and the eemt rule's licence is BSD-3-Clause.
  - Until the owner decides, the MIT text and the holder from the eemt rule are used, and O1 stays open.
- **Daymet data terms, stated separately** (in `docs/about/license.md`, `NOTICE` and the README):
  - Daymet data are not covered by the MIT licence.
  - Sources disagree on the exact terms [seen]:
    - NASA UMM-C points to the NASA Earth Science Data and Information Policy ("full and open sharing"; the linked URL
      now returns 404).
    - The AWS registry says CC BY 4.0.
    - Earth Engine says public domain.
  - All of them ask for the DOI citation.
  - The server returns data under the provider's terms. Users must cite the dataset DOI (and the tool DOI for
    single-pixel), and the data are provisional.
  - Committed test fixtures are small Daymet extracts, attributed in `NOTICE` with DOI 10.3334/ORNLDAAC/2129, the
    access URL and the fetch date.

## 17. How EEMT uses it

What EEMT needs, read from `eemt/eemt/reemt.sh` [seen in code]:

- Daymet `tmin`, `tmax`, `prcp`, `vp` rasters per period, imported with `r.in.gdal`.
- The Daymet 1 km DEM (`dem_1km`), for the lapse-rate correction `tmin_loc = tmin - 0.00649·(dem_10m - dem_1km)`.

Owner decision Q4: pipeline code must define monthly prcp as a total of daily values. daymet-mcp's default
(`prcp_monthly_total_mm`) matches that.

1. **Agents and interactive work.** EEMT developers add daymet-mcp to their MCP client (stdio; `uvx daymet-mcp` once
   published, `uv run daymet-mcp` from the local checkout before that). Typical calls:
   - `daymet_locate_cell` for a study site
   - `daymet_get_point_summary(period="monthly")` to check monthly totals and means
   - `daymet_get_citation` for papers
   - the `daymet_eemt_inputs` prompt for a job
2. **Pipeline (proposed adapter; Area C owns `eemt/**` and `scripts/`).** A small `eemt/eemt/daymet_fetch.py` starts
   `daymet-mcp` over stdio with the MCP Python SDK client and calls `daymet_download_area` with:
   - `temporal="monthly"`
   - `variables=["tmin","tmax","prcp","vp"]`
   - `include_elevation=true`
   - `format="aaigrid"`
   - the DEM bbox plus a 2-cell buffer
   - output into the job's work directory

   AAIGrid with `.prj` is a GDAL-readable format, so `reemt.sh` can import it with `r.in.gdal` unchanged [inferred:
   standard GDAL AAIGrid driver; not run in the EEMT container]. The adapter:
   - copies `manifest.json` (aggregation table, upstream URLs, sha256s, citation) into the job's provenance
   - selects the source with a `--daymet-source mcp|files|fixture` option on the workflow
   - depends only on the tool contracts (names, input schemas, `outputSchema`), with the daymet-mcp version pinned

   The S1 DEM needs 5×5 cells with a 1-cell buffer, or 7×7 with 2 [seen, `grid.log`]. That fits the credential-free
   limit (121 cells), so typical EEMT watersheds of a few km do not need Earthdata credentials. Larger domains
   (e.g. the SEAZ runs) need `DAYMET_MCP_EARTHDATA__TOKEN` and the `[grid]` extra.
3. **Grids stay native.** daymet-mcp returns Daymet cells snapped to the native 1 km LCC grid, with no resampling.
   Reprojection to the DEM grid stays in EEMT (`Tiff.py`/GRASS), as today [inferred].
4. **CI.** The EEMT repository **keeps its own committed fixture** and runs with `--daymet-source fixture`. EEMT CI
   never contacts the network or depends on daymet-mcp being installed.
   - The S1 extract `fixture_7x7_2020.json` is 930 KB [seen], too large to commit as is. EEMT should commit a reduced
     form, such as monthly aggregates of the 7×7 grid for 2020 plus elevation, or gzip.
   - An optional, `network`-marked EEMT test can compare that fixture with live `daymet-mcp` output for the same cells
     to detect upstream revisions.

## 18. Implementation order (for the build step)

1. Scaffold: pyproject, config, errors, logging, registry, server adapter, `daymet_ping`, conformance tests.
2. `calendar.py`, `lcc.py`, `catalog.py` with science tests; `daymet_locate_cell`, `daymet_list_variables`
   (CMR fixture).
3. `single_pixel.py` with its guards and the cache; `daymet_get_point_daily`; fixture recording.
4. `aggregate.py`; `daymet_get_point_summary`.
5. Mosaic backend; `daymet_get_area`; `daymet_download_area` + writers (AAIGrid/CSV).
6. Citation tool, resources, prompts, instructions.
7. Earthdata backend behind `[grid]` (synthetic fixture; marked experimental).
8. Docs bundle, llms.txt, CI files, Dockerfile.

## 19. Decision register

| Id | Decision | Basis |
|---|---|---|
| D1 | Follow neon-mcp conventions (layout, low-level SDK server, envelope, errors, budgets, OKF docs) | research-conventions checklist |
| D2 | Spec 2026-07-28 stateless; `mcp>=2.0,<3`; version from `LATEST_PROTOCOL_VERSION` | neon D33 |
| D3 | Single-pixel API is the default backend for points and small areas | only credential-free current path [seen] |
| D4 | Monthly/annual values always computed by the server from daily data; each field states aggregation + units; `source.derived` lists them | owner Q4; ORNL product lacks 2025 and srad/dayl [seen] |
| D5 | The earthdata backend also aggregates from daily, so both backends share definitions | consistency |
| D6 | Validate variables, year bounds and the returned year/row set against upstream silent failures | four silent failures [seen] |
| D7 | swe monthly/annual = mean (default), `last` optional | matches ORNL 2131/2130 [seen] |
| D8 | Years before 1980 refused everywhere in v0.1 | PR pre-1980 via single-pixel [not run] |
| D9 | Cell indices for NA only; hi/pr return LCC and `cell:null` | hi/pr grid origins unread |
| D10 | Daily values rounded to 2 dp, aggregates computed unrounded and rounded to 3 dp | CSV precision [seen] |
| D11 | Always fetch all 7 variables per cell-year; cache by cell | same cost [seen sizes/latency] |
| D12 | Pure-Python LCC (no pyproj at runtime), tested against service values and pyproj | lean install |
| D13 | Numeric deps (`numpy`, `h5netcdf`) only in the `[grid]` extra | lean install |
| D14 | Outputs AAIGrid+.prj / CSV / NetCDF; no GeoTIFF in v0.1 | avoid GDAL dependency |
| D15 | EDL token from env only (`DAYMET_MCP_EARTHDATA__TOKEN`, SecretStr); never netrc; Authorization only to EDL hosts | task safety rules |
| D16 | Citation text from the user guide (no B.E. Wilson); discrepancy noted | guide vs API [seen] |
| D17 | Hosted HTTP: no OAuth, no per-request token, earthdata off unless operator opts in, downloads stdio-only | neon D3, amf D18/D25; env-only rule |
| D18 | No elicitation/progress/sampling/roots/sessions | amf D13 |
| D19 | Local rate limits (2 req/s, concurrency 4 for single-pixel) | no published limits [seen] |
| D20 | Generic User-Agent `daymet-mcp/<ver> (+https://github.com/idss-mesa)` | safety rules |
| D21 | Live-test marker named `network` (neon uses `live`) | task requirement |

## 20. Open questions and things not run

- **O1** Copyright holder for the MIT licence (owner, or Regents of UNM as in idss-mesa). Owner decision.
- **O2** Hawaii and Puerto Rico grid origins and dimensions (needed for cell indices); read from granule metadata once
  EDL is available.
- [not run] Any Earthdata request with credentials (OPeNDAP, Harmony, HTTPS, S3); bearer-token acceptance by Hyrax.
- [not run] Single-pixel PR data before 1980.
- [not run] Comparison of server-computed monthly sums with the ORNL 2131 monthly product. Planned as a `network and edl`
  live test: one cell, one year, prcp and tmax.
- [not run] Single-pixel behaviour under 4 concurrent requests (all research calls were sequential).
- [not run] `r.in.gdal` import of the AAIGrid+.prj output inside the EEMT GRASS container.
