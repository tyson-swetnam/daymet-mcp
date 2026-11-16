# daymet-mcp research notes

This file collects the two research notes the design (`DESIGN.md`) is based on, copied
unchanged from the build inputs on 2026-11-15:

1. **Research A** — conventions of the reference MCP servers (idss-mesa/neon-mcp and
   idss-mesa/ameriflux-mcp).
2. **Research B** — every way to get Daymet V4 R1 data, tested live without credentials.

Labels: **[seen]** = observed by the researcher; **[inferred]** = a reading not verified;
**[not run]** = not tested. Paths under `/tmp/...` refer to the researchers' scratch space
and are not part of this repository.


---

# daymet-mcp: conventions of the reference MCP servers (Research A)

Date: 2026-11-15. Sources read with `gh api repos/idss-mesa/<repo>/contents/<path>` (raw), saved under
`/tmp/claude-57275/-home-tswetnam-github-eemt/5f7c764c-7e9c-4e13-8e3a-28e873e17aac/scratchpad/daymet-mcp/research-a/{neon,amf}/`.
Primary model: **idss-mesa/neon-mcp** (`main`). Secondary: **idss-mesa/ameriflux-mcp** (`main`), which states it
ports its core from **idss-mesa/edi-mcp** and its ratelimit/resolve/downloads/prompts/Docker/release from neon-mcp
(ameriflux `DESIGN.md` D2). edi-mcp and mesa-mcp were not read (GitHub API rate limit reached at the end of the read;
they appear in the org listing).

Labels: **[seen]** = read in the file named; **[inferred]** = my reading of how it applies to Daymet, not verified.

Owner decision relevant here (`owner-decisions.log` line 18): the repo is `tyson-swetnam/daymet-mcp`, built locally in
`/home/tswetnam/github/daymet-mcp`, not under idss-mesa. URLs below that say `idss-mesa/...` are the reference
servers' values; daymet-mcp substitutes its own.

---

## 1. Package layout [seen: neon `DESIGN.md` §5, tree listing; amf tree listing]

```
pyproject.toml uv.lock LICENSE [NOTICE] .gitignore .env.example config.yaml.example CHANGELOG.md
README.md CLAUDE.md AGENTS.md DESIGN.md RESEARCH.md zensical.toml
Dockerfile docker-compose.yml [server.json]
.github/workflows/{ci,docs,release}.yml        (amf adds live-download.yml)
.claude/agents/mcp-reviewer.md                 (neon only)
scripts/okf_validate.py gen_llms_txt.py postbuild_agent_surface.py   (vendored from UNM-CARC/docs, ruff-excluded)
scripts/gen_tools_reference.py gen_config_reference.py record_fixtures.py   (amf adds probe_api.py, install.sh)
docs/**                                         OKF v0.2 bundle
src/<pkg>/
  __init__.py      __version__ = "0.1.0" (hatch dynamic version source)
  __main__.py      argparse CLI -> load_config -> setup_logging -> server.run; --check, --print-config, --version
  config.py        pydantic Config + YAML/env loader
  errors.py        ErrorCode Literal, ToolError, InputRequired, <Upstream>ApiError, map_api_error
  logging.py       structlog setup, secret redaction
  context.py       ToolContext dataclass, UpstreamStats, contextvars
  registry.py      ToolSpec, @register_tool, invoke, fit_to_budget, requestState codec
  server.py        the ONLY SDK-coupled module (low-level mcp.server.Server adapter)
  instructions.py  SERVER_INSTRUCTIONS (<= 1 200 chars)
  models/common.py base input/output models, Page, Source, ToolResultBase, shared Annotated types
  <upstream>/      client.py cache.py ratelimit.py catalog.py resolve.py ... (neon: neon/, amf: ameriflux/)
  projections/     upstream payload -> compact output models (neon)
  tools/           __init__.py (imports every family module) _common.py core.py <family>.py ...
  resources.py prompts.py resources_static/*.md|*.json
  transport/       stdio.py streamable_http.py healthz.py
tests/
  conftest.py fixture_router.py helpers/ (call_ok, call_err, ASGI AppHarness)
  fixtures/ (+ MANIFEST.md or manifest.json)
  test_config.py test_errors.py test_logging_redaction.py test_registry.py test_server_adapter.py
  test_smoke.py test_spec_conformance_2026_07_28.py test_docs_generation.py test_integration_meta.py
  test_resources.py test_prompts.py  <upstream>/test_*.py  tools/test_*.py  transport/test_*.py
  live/conftest.py live/test_live*.py
```

## 2. MCP SDK and spec [seen]

- `mcp>=2.0,<3`; `uv.lock` pins **mcp 2.2.0** (neon) and **2.3.0** (amf). Python `>=3.11`; classifiers 3.11-3.13
  (neon `pyproject.toml`).
- Low-level `mcp.server.Server` with constructor callbacks (`on_list_tools`, `on_call_tool`, `on_list_resources`,
  `on_list_resource_templates`, `on_read_resource`, `on_list_prompts`, `on_get_prompt`), not `MCPServer`
  (neon `server.py::NeonServer.build_mcp_server`; RESEARCH.md §3 "prefer the low-level Server + our own registry").
- Spec **2026-07-28 stateless core**. `protocolVersion` always from `mcp.types.LATEST_PROTOCOL_VERSION`, never a literal
  (neon DESIGN D33; `tools/core.py`, `transport/healthz.py`).
- Other deps (neon `pyproject.toml`): `httpx>=0.28,<1`, `pydantic>=2.7`, `pyyaml>=6`, `structlog>=24`, `anyio>=4`,
  `starlette>=0.40`, `uvicorn>=0.30`. Build backend hatchling; dev extras pytest, pytest-asyncio, pytest-cov,
  hypothesis, jsonschema, ruff, mypy, types-PyYAML; `docs = ["zensical>=0.0.60", "pyyaml"]`.

## 3. MCP features used [seen: neon `server.py`, `registry.py`, `docs/mcp/spec-2026-07-28.md`, DESIGN §7]

| Feature | neon-mcp / ameriflux-mcp |
|---|---|
| Tools | Yes. Sorted by name, fixed per deployment (transport + downloads switch decide membership). |
| Structured output | Every tool has an `outputSchema` (pydantic serialization schema by alias) and returns the same compact JSON as `TextContent` **and** `structuredContent`. `$schema` = `https://json-schema.org/draft/2020-12/schema` on input and output schemas; pydantic `title` keys dropped, descriptions kept in input schemas only (`server.py::input_schema/output_schema`, `compact_schema`). |
| Annotations | All four hints on every tool + `title`. Read-only tools: `readOnlyHint=true, destructiveHint=false, idempotentHint=true, openWorldHint=true`. Download tools `readOnlyHint=false`; amf download `idempotentHint=false` (each call notifies PIs); amf local-file tools `openWorldHint=false`. |
| Tool `_meta` | `io.<server>/surface`, `io.<server>/requiresToken` (amf: `requiresIdentity`), `io.<server>/endpoints` (feeds the generated reference), `io.<server>/stdioOnly`. |
| Result `_meta` | `io.<server>/upstream = {requests, cacheHits, rateLimitRemaining, rateLimitLimit, identity}` merged with the SDK's `io.modelcontextprotocol/serverInfo` (test asserts both). |
| Resources | Yes: static guides (`<scheme>://guide/...`, markdown in `resources_static/`), references (`<scheme>://reference/...`, JSON), and resource templates backed by tool calls (`neon://products/{productCode}`; amf `ameriflux://site/{site_id}`). `_meta io.<server>/kind = static|derived`. Unknown URI -> JSON-RPC `-32602` with `data={"code":"not_found","didYouMean":[...]}` (DESIGN D32). |
| Prompts | Yes, 3 each. One user `TextContent` message, arguments validated. neon names carry the tool prefix (`neon_find_data`); amf names do not (`find_flux_sites`). |
| Cache hints | `CacheHint(scope="public")` on `tools/list` 5 min, `resources/list` and templates 1 h, `resources/read` 1 h (24 h static per read result), `prompts/list` 24 h, `server/discover` 5 min. |
| `server/discover`, instructions | SDK answers; `instructions` = `SERVER_INSTRUCTIONS` (<= 1 200 chars) + optional config extra. |
| Elicitation (MRTR) | neon: only `neon_get_sample`, gated on `clientCapabilities.elicitation`, else `ambiguous_input`; `requestState` base64url JSON <= 16 KiB, unsigned, no credential-like keys, 1 h expiry (`registry.py`). amf: **no elicitation** (D13: two-phase `confirm=false/true` instead). |
| Pagination | **Not** MCP cursors. Offset/limit inputs and a `page` object in each result: `{total, returned, offset, limit, truncated, nextOffset, truncatedReason: "limit"|"budget"}` (`models/common.py::Page`). |
| Progress, cancellation | Not used (grep for `progress`/`cancel`/`cursor` in both `src/` trees found only config-loader and task-group internals). |
| Sampling, roots, logging/setLevel, SSE, sessions, tasks | Not implemented; CI greps `src/` and fails on them (neon `ci.yml` spec-conformance job). |

## 4. Transports and HTTP auth [seen: neon `transport/*.py`, `docs/mcp/transports.md`, DESIGN §7.3-7.4]

- **stdio** default (bare `<cmd>` = stdio); logs to stderr only, a test asserts stdout carries only framing; SDK loop is
  dual-era (legacy 2024-11-05..2025-11-25 clients still work; `tests/transport/test_stdio_dual_era.py`).
- **Stateless Streamable HTTP** at `/mcp` via `Server.streamable_http_app(streamable_http_path="/mcp",
  stateless_http=True, json_response=..., max_request_body_size=1 MiB, transport_security=..., custom_starlette_routes=
  [/healthz, /readyz])`, served by `uvicorn.Server(...).serve()`. `GET`/`DELETE /mcp` -> 405; `/mcp/` served without 307.
  One raw ASGI `RequestContextMiddleware` (request id, header filtering, contextvars, structlog binding).
- `/healthz` = `{"status":"ok","version","protocolVersion","transport":"http"}`, no upstream inspection; `/readyz` = 503
  while prewarming, else 200 with `degraded`.
- DNS-rebinding protection: SDK default on loopback; `public_base_url`, `allowed_hosts`, `allowed_origins` build a
  `TransportSecuritySettings`; `dns_rebinding_protection=false` for proxies that rewrite Host.
- **Auth on hosted HTTP: no OAuth/OIDC.** neon accepts a per-request upstream token in `X-API-Token` only when
  `public_base_url` is `https://` (or a dev override), never `Authorization: Bearer` (collides with MCP OAuth); operator
  token not lent to anonymous callers by default. amf: no credentials over HTTP at all; identity-bearing and local-file
  tools are stdio-only (amf D25).
- Downloads / disk-writing tools exist only on stdio and are confined to a configured directory (neon D3, amf D18, D36).

## 5. Config pattern [seen: neon `config.py`, `.env.example`, `config.yaml.example`, DESIGN §6]

- pydantic models per section (`server`, `<upstream>`, `cache`, `limits`, `downloads`), sections `extra="ignore"` with
  loader warnings for unknown keys; secrets as `SecretStr`; `model_dump_redacted()` for `--print-config`.
- Precedence **CLI flag > env > YAML (`--config`) > defaults**. Env `<PKG>_MCP_<SECTION>__<FIELD>` (`__` descends any
  depth, comma-split lists). `.env` is **not** auto-loaded (`uv run --env-file .env`). No token flag on the CLI.
- amf adds value-free `ConfigError` (validation errors name the setting, never echo the value; exit 2) (amf D32).
- `--check`: neon runs `neon_ping(check_api=true)` in-process and prints JSON (one live request); amf `--check` is offline.
- Settings table in `docs/getting-started/configuration.md` is generated by `scripts/gen_config_reference.py` between
  `<!-- BEGIN GENERATED CONFIG -->` markers.

## 6. Error model [seen: neon `errors.py`, `registry.py`, `server.py`, DESIGN §3.5; amf `errors.py`]

- Tool failures are **tool results**, not JSON-RPC errors: `CallToolResult(is_error=True, structuredContent={"error":
  {code, message, details, hint?}})`. Only protocol failures (header mismatch -32020, unsupported version -32022,
  malformed JSON-RPC) are JSON-RPC errors (SDK). Tracebacks never reach the wire; unexpected exceptions ->
  `internal_error` with `details.correlationId`.
- Stable `ErrorCode` Literal. neon: 19 codes incl. `invalid_argument, not_found, ambiguous_input, auth_required,
  forbidden, rate_limited, upstream_error, upstream_unavailable, feature_unavailable, not_available_in_http_mode,
  download_limit_exceeded, download_denied, checksum_mismatch, query_too_large, result_too_large, unknown_tool,
  internal_error`. amf/edi: 16 codes, `upstream_forbidden` instead of `forbidden`, specifics in `details.reason`, no new
  codes (amf D24).
- pydantic validation -> `invalid_argument` naming the field; unknown field -> lists valid arguments (inputs are
  `extra="forbid"`).
- Upstream mapping table per server (status -> code). amf adds schema-drift detection: required-key set per endpoint;
  missing key -> `upstream_error` with `details.drift={endpoint, missing}` (amf D8).

## 7. Result envelope and size budget [seen: neon `models/common.py`, `registry.py`, DESIGN §1.1, §4.10]

- Every output model subclasses `ToolResultBase`: `resolved[]`, `notes[]` (human caveats), `nextSteps[]` (1-3 concrete
  follow-up calls), `source = {endpoints[], via, cached, derived[]}`. amf uses `source.backend` instead of `via`
  (amf D5). **`source.derived` lists fields the server computed rather than received** - the hook for Daymet monthly
  aggregates [inferred].
- Inputs snake_case, upstream camelCase accepted as aliases; outputs camelCase (neon D1; amf D1).
- Result budget 50 000 B compact JSON (`fit_to_budget` trims the model's `budget_list` from the tail, eliding URL
  fields first, sets `page.truncatedReason="budget"`, appends a `nextSteps` line); hard cap 200 000 B ->
  `result_too_large`.
- Tool descriptions <= 600 chars and end with a `Next:` sentence; names match `^<prefix>_[a-z_]+$` (enforced at
  import in `register_tool`). `tools/list` byte size bounded by a test at measured x 1.25 (neon 135 000 B; amf 85 000 B).

## 8. Caching [seen: neon `neon/cache.py` signatures, DESIGN §3.6; amf D22]

- In-memory `TTLCache` per family with LRU caps, **single-flight** per key, refresh-ahead (HTTP only) and
  stale-if-error (24 h); TTLs configurable per family (`cache.ttl_s.*`). Keys `METHOD path?sorted-params` (+ token
  identity for token endpoints). Never cached: escape-hatch queries, ping probe, downloads.
- amf adds an optional **disk layer** (`cache.disk_dir`, default `~/.cache/ameriflux-mcp`, atomic writes, never fails a
  call on disk error, off over HTTP unless a volume is configured) (amf D22, D33).

## 9. Rate limiting and HTTP client [seen: neon `neon/client.py`, `neon/ratelimit.py`, DESIGN §3.1-3.3; amf D21]

- One `httpx.AsyncClient` per process; `follow_redirects=False` (redirects checked against a host allow-list); explicit
  timeouts; `max_connections=8`; injectable `transport`, `clock`, `sleep` test seams.
- neon: per-identity token buckets 10 % under upstream published limits, `observe()` from `X-RateLimit-*`, low-water
  pre-wait, 429 honours `Retry-After`, 5xx/transport errors exponential backoff `0.5*2^n` + jitter, <= 3 attempts, one
  process-wide semaphore (4). amf: upstream publishes no limits -> local policy 2 req/s, concurrency 4, host and path
  allow-list checked before any socket, GET/HEAD only (amf D21, D33).
- User-Agent: `neon-mcp/{__version__} (+https://github.com/idss-mesa/neon-mcp)` (neon `client.py` line 171); amf the
  same pattern. For daymet-mcp the safety rules require a generic UA without the owner's name; a repo URL under
  `github.com/tyson-swetnam/` would contain the owner's username [inferred conflict -> use
  `daymet-mcp/0.1 (+https://github.com/idss-mesa)` per the safety rules].

## 10. Logging [seen: neon `logging.py`, DESIGN §3.10]

structlog; stdio -> console renderer on **stderr**, HTTP -> JSON with `request_id`; `redact_secrets` processor masks
credential-like keys and every registered secret; httpx/httpcore loggers forced to WARNING (they print full URLs).
Events `<upstream>.http`, `tool.call {tool, ms, ok, code, result_bytes, upstream_requests, cache_hits, request_id}`.

## 11. Test strategy [seen: neon `tests/conftest.py`, `tests/fixture_router.py`, `tests/tools/test_sites.py`,
`tests/live/conftest.py`, `tests/fixtures/MANIFEST.md`, `docs/develop/testing.md`; amf `tests/fixture_router.py`,
`tests/fixtures/manifest.json`]

- **Hermetic by default, recorded fixtures.** `FixtureRouter` is an `httpx.MockTransport` handler; it replays recorded,
  shrunk, scrubbed real responses, records every call (`router.calls`), and **fails the test on any unrouted request**
  (`conftest.router` asserts `not r.unexpected`). Fixed fake sleep/clock; no real waiting.
- Fixtures: neon `tests/fixtures/*.json` + `MANIFEST.md` (hand-written ones listed with origin); amf
  `tests/fixtures/<host>/<path>_<status>_<hash>.json` + `manifest.json` entries `{key, status, contentType, transform,
  file}`. `scripts/record_fixtures.py check` runs in CI (size, scrubbing, allow-listed GETs).
- Tool tests go through `tests.helpers.call_ok` / `call_err`, which validate `structuredContent` against the tool's
  `outputSchema`; per-tool checklist: happy path, each filter, paging, budget trim, error mapping, cache hit,
  `nextSteps` non-empty (DESIGN §8.1). `test_integration_meta.py` asserts every tool has a unit test and a live test.
- Conformance suite `tests/test_spec_conformance_2026_07_28.py` (schema dialect/validity, annotations + `_meta`,
  sorted bounded `tools/list`, alias acceptance, cache hints, discover, stateless both eras, result `_meta`, header
  routing, -32020/-32022, host allow-list, resources/prompts over HTTP, MRTR round trip, stateless session manager)
  plus `tests/transport/` (ASGI harness + real stdio subprocess).
- **Live tests** opt-in: marker `live`, `addopts = "-ra -m 'not live'"`, enabled with `<PKG>_MCP_LIVE=1`; one per
  tool; diff key sets against fixtures to detect drift; nightly in CI, never on PRs.
- Coverage `fail_under = 85`; `mypy --strict src`; ruff `E,F,I,UP,B,SIM,S,RUF`, line length 100.

## 12. CI and release [seen: neon `.github/workflows/{ci,docs,release}.yml`; amf `release.yml`, `ci.yml` steps]

- `ci.yml`: matrix py3.11/3.12/3.13 on ubuntu (`astral-sh/setup-uv@v7`, `uv sync --all-extras`, ruff check + format
  check, `mypy --strict src`, pytest with coverage, fixture check); macOS py3.12 subset; separate **"MCP 2026-07-28
  conformance"** job (asserts `mcp` major == 2, runs conformance + transport tests, greps for deprecated features,
  advisory `-W error::DeprecationWarning`); nightly `live` job on `schedule`/`workflow_dispatch`.
- `docs.yml`: `okf-conformance` (validator + regenerate llms/reference/config, `git diff --exit-code`) on PRs and main;
  `deploy` (zensical build `--clean --strict`, `postbuild_agent_surface.py site`, GitHub Pages) on main only.
- `release.yml`: on tag `v*`, environment `pypi`, PyPI trusted publishing, `gh release create` with dist. amf adds a
  check that tag == `__version__` == `server.json` versions and that `CHANGELOG.md` has a dated `## [x.y.z] - YYYY-MM-DD`.
- amf publishes an MCP-registry `server.json` (schema 2025-12-11, name `io.github.idss-mesa/ameriflux-mcp`, PyPI
  package, `runtimeHint: uvx`, stdio, env vars with `isSecret`) and a README comment `<!-- mcp-name: ... -->` (amf D29).
- Two logs: `CHANGELOG.md` (Keep a Changelog, package) and `docs/log.md` (OKF, docs). SemVer from 0.1.0.
- Docker: two-stage `python:3.13-slim`, `uv sync --frozen --no-dev`, non-root uid 10001, env sets HTTP transport on
  0.0.0.0:8080, `HEALTHCHECK` on `/healthz`; compose publishes `127.0.0.1:8080:8080` only. neon copies
  `ghcr.io/astral-sh/uv:latest`; amf pins `uv:0.12.9`. Under this session's safety rules base images must be pulled by
  digest and built images tagged `eemt-work/<name>:<tag>` [inferred for local builds].

## 13. Documentation (OKF v0.2 + Zensical + agent surface) [seen: neon `AGENTS.md`, `CLAUDE.md`, `docs/*`,
`zensical.toml`, RESEARCH §6]

- `docs/` is an OKF v0.2 bundle built with Zensical, deployed to `https://<owner>.github.io/<repo>/`.
- Every content page: frontmatter `title`, `description` (one plain sentence, 50-160 chars), `type` (`Guide | Tutorial |
  Reference | Policy | MCP Tool Reference`), `tags`, `generated: {by: "claude/<model>" | "human:<id>" |
  "process:<script>", at: ISO-8601Z}`, `sources[]` (`id, resource, title, author`; cited in text as `[^id]`), optional
  `status` (draft|stable|deprecated) and `stale_after` for facts upstream or MCP may change. **Never add `verified:`.**
- Section `index.md`: no frontmatter, `# Heading` + `* [Title](page.md) - description`. Root `docs/index.md`: only
  `okf_version: "0.2"`, `title`, `description`. `docs/log.md`: `# Directory Update Log`, `## YYYY-MM-DD` newest first,
  `* **Creation**:` / `* **Update**:` / `* **Deprecation**:`.
- Sections: getting-started (install, quickstart, clients, configuration, credential page), tools (generated
  `reference.md` + family pages + resources-and-prompts), mcp (spec-2026-07-28, transports), deploy (hosted-http,
  security), develop (architecture, adding-tools, testing, contributing), about (ai-agents, citing-<data>, license).
- `docs/llms.txt` and `docs/llms-full.txt` generated by `scripts/gen_llms_txt.py` and committed (CI drift check);
  `postbuild_agent_surface.py` writes a per-page `index.md` mirror, `okf:*` meta and `robots.txt`.
- Internal links relative; external links `{target=_blank}`; prose must not enumerate tools beyond the generated
  reference (AGENTS.md rule 9).

## 14. Licensing [seen: neon `LICENSE`, `pyproject.toml`, `docs/about/license.md`; amf `NOTICE`, D27]

- Code MIT, "Copyright (c) 2026 The Regents of the University of New Mexico"; `license = "MIT"`, `license-files`.
  Docs CC BY 4.0. Upstream data under the provider's own licence, stated on the license page.
- amf adds `NOTICE` crediting ported/derived third-party code and data (licence text, source URL, commit/ETag, fetch
  date) and lists it in `license-files`.
- **Conflict to resolve with the owner [inferred]:** `INTERFACES.md` "Commit rules" require SPDX headers
  `SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam` / `BSD-3-Clause` on every new source file *in the eemt work*, while
  the idss-mesa servers are MIT / Regents of UNM without SPDX headers, and the owner placed daymet-mcp under
  `tyson-swetnam/`. Which licence and copyright holder daymet-mcp uses is an owner decision.

## 15. Citation handling [seen: neon DESIGN D23, §1.3 `neon_get_citation`, `docs/about/citing-neon.md`;
amf D9, D10, `tools/citation.py`]

- A dedicated citation tool (`neon_get_citation`, `amf_get_citation`) returns citation text + BibTeX + DOI, rendered
  locally from templates kept in a static guide resource (`neon://guide/citing-neon-data`) whose docs twin is
  `docs/about/citing-<data>.md` (type `Policy`, provider policy pages in `sources`). Wording changes need no code.
- Outputs carry `doi`, `doiUrl`, `accessedOn` (default today UTC), `citationText`, `bibtex`, `dataPolicyUrl`; amf adds
  required acknowledgments and policy obligations tagged `required|recommended`, and marks constructed citations
  (`source: 'constructed'`) with a DataCite fallback flagged `versionMissing`.
- Every data-returning tool's `nextSteps` ends with the citation tool (neon instructions; Appendix B trace).

---

## Checklist for daymet-mcp

Each line: convention -> where it is in the reference servers.

1. Python >=3.11, hatchling, `mcp>=2.0,<3` low-level `Server` (lock the current 2.x), httpx, pydantic v2, structlog,
   pyyaml, anyio, starlette, uvicorn -> neon `pyproject.toml`, `CLAUDE.md`.
2. Names: dist/CLI `daymet-mcp`, package `daymet_mcp`, tool prefix e.g. `daymet_` with `NAME_RE`, URI scheme
   `daymet://`, `_meta` keys `io.daymet-mcp/*`, env `DAYMET_MCP_<SECTION>__<FIELD>` -> neon `registry.py`
   `NAME_RE`; amf D1.
3. `server.py` is the only SDK-coupled module; tools are `async (args, ctx) -> OutputModel` registered with
   `@register_tool(name, title, description<=600 ending "Next: ...", input_model, output_model, surface, endpoints,
   read_only, destructive, idempotent, open_world, transports)` -> neon `registry.py`, `docs/develop/adding-tools.md`.
4. Inputs `extra="forbid"`, snake_case advertised, every field described; outputs camelCase; `ToolResultBase`
   envelope `resolved/notes/nextSteps/source` -> neon `models/common.py`.
5. Every tool: `outputSchema` (2020-12 `$schema`), text + `structuredContent`, all four annotations + title, `_meta`
   surface/endpoints; result `_meta io.daymet-mcp/upstream` -> neon `server.py::tool_definitions`, `_on_call_tool`.
6. Offset/limit + `page` object, 50 KB budget via `fit_to_budget`, 200 KB hard cap; `tools/list` size test at
   measured x 1.25 -> neon `registry.py`, `docs/mcp/spec-2026-07-28.md`.
7. Errors as `isError` results `{"error":{code,message,details,hint}}` with a fixed `ErrorCode` Literal (reuse edi/amf's
   16 codes; reasons in `details.reason`); upstream status mapping table; drift detection on required keys -> neon
   `errors.py`; amf D8, D24.
8. **Daymet-specific, from this task:** monthly/annual aggregation must be explicit per variable in the output
   (e.g. `aggregation: "sum"` for prcp with units `mm/month`; `"mean"` for tmin/tmax/vp/srad/dayl with their daily
   units), listed in `source.derived`, with a `notes[]` line on the leap-year Dec 31 omission (365-day years) [inferred
   mapping onto `source.derived`/`notes`, neon `models/common.py::Source`].
9. Resources: static guides + JSON references in `resources_static/`, resource templates backed by tools,
   `-32602` + `didYouMean` for unknown URIs; 3 prompts; `SERVER_INSTRUCTIONS` <= 1 200 chars -> neon `resources.py`,
   `prompts.py`, `instructions.py`.
10. Cache hints `public` on all list/read/discover results -> neon `server.py::build_mcp_server`.
11. No elicitation unless needed (amf: none); never sampling/roots/logging/SSE/sessions; CI grep -> amf D13;
    neon `ci.yml` spec-conformance job.
12. Transports: stdio default (logs stderr) + stateless Streamable HTTP `/mcp`, `/healthz`, `/readyz`, DNS-rebinding
    settings, 1 MiB body cap; no OAuth; any credential only stdio or TLS-gated header; disk writes stdio-only and
    confined -> neon `transport/*.py`, `docs/mcp/transports.md`, `docs/deploy/security.md`.
13. Config precedence flag > env > YAML > default; `.env` not auto-loaded; `--check`, `--print-config`, `--version`;
    no secret flags; value-free config errors; generated config table -> neon `config.py`, `__main__.py`; amf D32.
14. One `httpx.AsyncClient`, no auto-redirects, host allow-list, timeouts, retries (429 Retry-After, 5xx/transport
    backoff, <= 3), polite local rate limit when upstream publishes none (amf: 2 req/s, concurrency 4), GET only ->
    neon `client.py`, `ratelimit.py`; amf D21. Generic User-Agent per the safety rules (not the owner's repo URL).
15. In-memory TTL cache with single-flight and stale-if-error; optional disk cache (stdio) for repeated pixel/year
    pulls -> neon `cache.py`; amf D22.
16. structlog to stderr, JSON over HTTP, secret redaction, httpx loggers at WARNING -> neon `logging.py`.
17. Tests: hermetic `FixtureRouter` failing on unrouted calls; recorded, shrunk fixtures with a manifest and a
    `record_fixtures.py check`; `call_ok` validates `outputSchema`; conformance suite + transport tests; `live`
    marker opt-in with `DAYMET_MCP_LIVE=1`; coverage >= 85; `mypy --strict`; ruff rule set -> neon `tests/`,
    `pyproject.toml`; amf `tests/fixtures/manifest.json`.
18. CI: `ci.yml` (3.11-3.13 matrix, macOS subset, conformance job, nightly live), `docs.yml` (OKF validate + drift +
    Pages deploy), `release.yml` (tag -> PyPI trusted publishing; version/CHANGELOG agreement check) -> neon and amf
    `.github/workflows/`. Not pushed in this work (no repo creation, no push).
19. Docs: OKF v0.2 frontmatter rules, section indexes without frontmatter, `docs/log.md`, generated
    `tools/reference.md`, `llms.txt`/`llms-full.txt`, Zensical `--strict`, agent surface; `AGENTS.md` + `CLAUDE.md` +
    `DESIGN.md` (D-register) + `RESEARCH.md` (verified facts) at the root -> neon `AGENTS.md`, `CLAUDE.md`, `docs/`.
20. Licence: reference servers are MIT / Regents of UNM (+ `NOTICE` for third-party material); the eemt SPDX/BSD-3
    rule differs -> owner decision needed (neon `LICENSE`; amf `NOTICE`; `INTERFACES.md` Commit rules).
21. Citation: a dedicated citation tool rendering text + BibTeX + DOI from templates in a guide resource, docs twin
    `docs/about/citing-daymet.md` (type Policy, ORNL DAAC policy pages in `sources`), `accessedOn`, every data result's
    `nextSteps` pointing to it -> neon D23, `docs/about/citing-neon.md`; amf D9.
22. Docker: two-stage python slim + pinned uv, non-root uid 10001, HTTP on 8080 with `/healthz` HEALTHCHECK, compose on
    127.0.0.1 only; locally pull bases by digest and tag `eemt-work/<name>:<tag>` -> neon/amf `Dockerfile`,
    `docker-compose.yml`; `INTERFACES.md` Safety rules.

---

# daymet-mcp: every way to get Daymet V4 R1 today (Research B)

Date: 2026-11-15. All requests were sent from `python@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f`
(the local `python:3.14-slim`, used by digest, not pulled), run as the invoking UID:GID, using only the stdlib (`http.client`/`urllib`),
with the User-Agent `daymet-mcp/0.1 (+https://github.com/idss-mesa)`, **no credentials**. Redirects were followed hop by hop and logged.
Raw evidence (status chain, selected headers, first bytes, full bodies) lives in
`/tmp/claude-57275/-home-tswetnam-github-eemt/5f7c764c-7e9c-4e13-8e3a-28e873e17aac/scratchpad/daymet-mcp/research-b/`
(`<tag>.log`, `<tag>.body`, `index.tsv` = tag -> final status; `guide_*.txt` = `pdftotext -layout` of the user guides).
Probe scripts: `.../scratchpad/daymet-mcp/research-b-scripts/{fetch.py,run.sh,mpc_zarr.py,strip.py}`.
About 90 requests in total, each a single pixel, a 2-day subset, or metadata.

Labels: **[seen]** = I ran it and saw the output quoted; **[inferred]** = my reading, not verified; **[not run]** = not tested.

---

## 0. Decision table

| Need | Without Earthdata Login (EDL) | With EDL credentials (server-side `EARTHDATA_TOKEN` or netrc) |
|---|---|---|
| **Point time series (daily, any of the 7 variables)** | **Single-pixel API** `https://daymet.ornl.gov/single-pixel/api/data` [seen: 200, no auth, 0.4-0.9 s per year, 2.4 s / 0.9 MB for the full 1980-2025 record of all 7 variables]. Primary path. | Same. The single-pixel API is still best for a point. |
| **Point *monthly* or *annual* values** | Compute them from single-pixel daily data inside the server, using the ORNL rule (prcp **sum**, mm/month; tmax, tmin, vp, swe **mean**). This also gives 2025, which the ORNL monthly product does not have yet. [inferred: method; ORNL definitions seen in §4] | Can also read the ORNL monthly/annual granules (2131/2130) via OPeNDAP/Harmony for 1980-2024, but computing from daily is simpler and covers the latest year. |
| **Small-area daily grid (a few km to tens of km)** | **Many single-pixel calls**, one per 1 km cell centre (x = -4560250 + 1000 i, y = 4984000 - 1000 j in Daymet LCC; see the earlier S1 grid artefact). Practical for about 7x7 to 15x15 cells. [seen: method validated earlier in `s1-artifacts/data-and-toolchains/daymet/grid.log`; cell grid re-confirmed by the TESViS subset corner -456750 / -250500, §6c]. ORNL TESViS fixed sites only cover predefined sites (§6c). | **NASA cloud OPeNDAP (Hyrax)** `https://opendap.earthdata.nasa.gov/collections/C2532426483-ORNL_CLOUD/granules/<GranuleUR>.dap?dap4.ce=...` with index subsetting, or **Harmony HOSS** bbox+time subset to NetCDF-4, or whole-granule HTTPS/S3 download. [seen: all three answer 302 -> EDL 401/login without credentials; behaviour with credentials **not run**] |
| **Monthly summary grids** | No credential-free path to current V4 R1 monthly grids. MPC has V4.0 monthly Zarr for **1980-2020 only** (needs an anonymous SAS token). [seen] | **Daymet_Monthly_V4R1_2131** granules (NetCDF or COG, 1980-2024; PR from 1950) via Harmony/OPeNDAP/HTTPS. [seen: listing in CMR; access **not run**] |
| **Discovery / "what is the latest year"** | **CMR** `https://cmr.earthdata.nasa.gov/search/granules.umm_json?collection_concept_id=...&sort_key=-start_date` [seen: 200, no auth, 0.2-0.6 s] | Same. |

Practical recommendation for the MCP server [inferred]:

1. Default backend = single-pixel API (no credentials, covers na/hi/pr, 1980 to the latest full year; PR before 1980 untested, see §1).
2. Monthly and annual values are always computed by the server from daily data, and each output field states its aggregation and units (`prcp_monthly_total_mm`, `tmax_monthly_mean_degC`, ...). The ORNL monthly product is used only as an optional cross-check when EDL is configured.
3. An optional EDL-gated backend (Hyrax OPeNDAP or Harmony) for grids larger than a few hundred cells. It is off unless a token is configured, and the server must never read `~/.netrc` itself.
4. Use CMR to learn the latest available year. Do not trust the single-pixel API for this, because it silently returns **all** years when asked for a year that does not exist (§1).

---

## 1. ORNL DAAC Daymet single-pixel API (credential-free) [seen]

- **Base URL**: `https://daymet.ornl.gov/single-pixel/api/data`. OpenAPI (Swagger 2.0, "version 1.0.2") at
  `https://daymet.ornl.gov/single-pixel/static/swagger.json`, UI at `https://daymet.ornl.gov/single-pixel/api`. There is also `/single-pixel/preview` (HTML table)
  and `/single-pixel/send/saveData`, which has the same parameters as `/api/data`.
- **Parameters**: `lat`, `lon` (decimal degrees, required); `vars` (comma list of `dayl,prcp,srad,swe,tmax,tmin,vp`; all by default);
  `years` (comma list) **or** `start`/`end` (`YYYY-MM-DD`); `format=csv|json` (the spec says required; CSV is returned when it is omitted).
  `years` takes precedence over dates: `years=2023,2024&start=2025-01-01&end=2025-01-05` returned 2023 and 2024, 365 rows each.
- **Returns** the nearest 1 km cell. **CSV**: 6 header lines (Latitude/Longitude, `X & Y on Lambert Conformal Conic`, `Tile`, `Elevation`,
  "All years; all variables; Daymet Software Version 4.0" (this text is printed even when subsetting), `How to cite: ...`), then
  `year,yday,dayl (s),prcp (mm/day),srad (W/m^2),swe (kg/m^2),tmax (deg c),tmin (deg c),vp (Pa)`. **JSON**: `{"loc","Tile","Elevation","LCC",
  "citation","data":{"year":[...],"yday":[...],"prcp (mm/day)":[...],...}}` with floats (e.g. `7.329999923706055`). `Content-Disposition:
  attachment; filename=<tile>_lat_<lat>_lon_<lon>_<date>_<time>.csv`.
- **Temporal coverage**: daily data. **Latest year = 2025** (1980..2025, 365 rows per year at the test cell; a full-record request returned
  46 years x 365 rows). Whether the API serves PR data before 1980 (the gridded PR product starts in 1950) was **not run**.
  The Swagger text still says `[1980..2019]` and the web-services page still talks about "version 3" and "lat 52.0N-14.5N, lon -131 to -53".
  That documentation is stale: Hawaii (21.3, -157.8) worked.
- **Regions**: na, hi (21.3,-157.8 -> tile 9912, LCC -5643436.98,-258972.42) and pr (18.2,-66.5 -> tile 9777) all returned 200. Hawaii and PR
  coordinates are reported in the same North-America LCC.
- **Leap years** [seen]: `start=2024-02-27&end=2024-03-02` -> 5 rows, yday 58..62 (Feb 29 = yday 60 is present). `start=2024-12-29&end=2024-12-31`
  -> 2 rows (yday 364, 365); **Dec 31 is not returned**. A whole-year 2024 JSON had 365 rows.
- **Error behaviour (important for the server)** [seen]:
  - outside the grid (`lat=0&lon=0`, or `lat=30&lon=-130` over the ocean) -> **HTTP 400** `{"message":"Daymet Tile was not found with input lat and lon: ..."}`
  - unknown variable `vars=foo` -> **200 with all 7 variables** (silently ignored)
  - year not yet published `years=2026` -> **200 with the entire 1980-2025 record** (242 KB for one variable)
  - `start` before 1980 (`1979-12-30..1980-01-02`) -> **200 with the entire record**
  - The server must therefore validate variables and the date range itself, and check the years actually returned.
- **Limits / rate limits**: no limit is documented on the API page, Swagger or batch-script README. No `X-RateLimit-*` or `Retry-After`
  headers were seen. `Cache-Control: max-age=1`, `Server: Apache`. Max request = one point, any number of years. [seen]
- **Latency**: one year, all variables, JSON: 0.56-0.58 s (3 runs, 46 138 bytes); one year CSV 0.69 s; full record, all variables 2.39 s / 900 791 bytes;
  small date window 0.40-0.44 s. [seen]
- **Auth**: none (HTTP 200 without credentials). [seen]
- **Citation it embeds** [seen, verbatim]: "Thornton; M.M.; R. Shrestha; Y. Wei; P.E. Thornton; S-C. Kao; and B.E. Wilson. 2022. Daymet: Daily
  Surface Weather Data on a 1-km Grid for North America; Version 4 R1. ORNL DAAC; Oak Ridge; Tennessee; USA. https://doi.org/10.3334/ORNLDAAC/2129".
  It adds B.E. Wilson as an author; the user guide citation (§7) does not. Tool citation (web-services and citations pages): "Thornton, M.M., and
  R. Devarakonda. 2011. Daymet Single Pixel Extraction Tool. ORNL DAAC, Oak Ridge, Tennessee, USA. https://doi.org/10.3334/ORNLDAAC/2361".
- **Stability**: the tool has existed since 2011 (tool DOI) and its documentation lags behind the service. No deprecation notice was seen. [seen / inferred]

## 2. THREDDS / NetCDF Subset Service (NCSS) [seen]

- The Daymet site still points to `https://thredds.daac.ornl.gov/thredds/...` (web-services page example:
  `.../thredds/ncss/ornldaac/1840/daymet_v4_daily_na_tmin_2015.nc?var=lat&var=lon&var=tmin&north=..&west=..&east=..&south=..&disableProjSubset=on&horizStride=1&time_start=..&time_end=..&timeStride=1&accept=netcdf`).
- Live behaviour: **every** `thredds.daac.ornl.gov` URL answers `301` -> `opendap.earthdata.nasa.gov/thredds/...`.
  - NCSS daily `/ncss/grid/ornldaac/2129/daymet_v4_daily_na_tmax_2025.nc?...` -> 301 -> 302 `/login/urs` -> **401** at `urs.earthdata.nasa.gov`
    (`WWW-Authenticate: Basic realm="Please enter your Earthdata Login credentials..."`), about 1.0 s.
  - NCSS monthly `/ncss/grid/ornldaac/2131/daymet_v4_prcp_monttl_na_2024.nc?...` -> the same chain -> **401**.
  - `DAYMET_COLLECTIONS.html` catalog -> the same chain -> **401**.
  - `catalog.xml` / `catalog.html` under `/thredds/catalog/ornldaac/{2129,2131}/` -> **400 "Hyrax - Bad Request ... DAP response suffix '.xml' is not recognized"**.
- So the THREDDS server has been replaced by NASA's **Hyrax** OPeNDAP server behind EDL [inferred from the 400 page text, which is Hyrax's]. Whether NCSS-style query strings still
  work after login was **not run**. Do not build on NCSS.
- Collection ids (THREDDS path numbers = ORNL dataset ids): daily **2129**, annual **2130**, monthly **2131**, station cross-validation 2132. V4.0 (superseded) daily is 1840.

## 3. NASA Earthdata cloud (CMR, HTTPS, S3, OPeNDAP, Harmony) [seen]

**CMR** (`https://cmr.earthdata.nasa.gov/search/collections.json?keyword=daymet`, 200, no auth, 0.26 s, 9 hits). The V4 R1 collections:

| Concept id | Short name | Version | DOI | CMR temporal | Granules | User guide |
|---|---|---|---|---|---|---|
| C2532426483-ORNL_CLOUD | Daymet_Daily_V4R1_2129 | 4.1 | 10.3334/ORNLDAAC/2129 | 1950-01-01 to 2025-12-31 | 1176 | `https://data.ornldaac.earthdata.nasa.gov/public/daymet/Daymet_Daily_V4R1/comp/Daymet_Daily_V4R1.pdf` |
| C2532007210-ORNL_CLOUD | Daymet_Monthly_V4R1_2131 | 4.1 | 10.3334/ORNLDAAC/2131 | 1950-01-01 to 2024-12-31 | 1650 | `.../Daymet_Monthly_V4R1/comp/Daymet_Monthly_V4R1.pdf` |
| C2531982907-ORNL_CLOUD | Daymet_Annual_V4R1_2130 | 4.1 | 10.3334/ORNLDAAC/2130 | 1950-01-01 to 2024-12-31 | 1650 | `.../Daymet_Annual_V4R1/comp/Daymet_Annual_V4R1.pdf` |
| C2531991823-ORNL_CLOUD | Daymet_xval_V4R1_2132 | 4.1 | 10.3334/ORNLDAAC/2132 | 1950 to 2023-12-31 | - | - |
| C4295322197-ORNL_CLOUD | Daymet_Daily_V4_1840 (V4.0, superseded) | - | 10.3334/ORNLDAAC/1840 | 1950 to 2021-12-31 | 0 | - |

- **Latest year** (granules sorted `-start_date`) [seen]: daily = **2025** (21 granules = 3 regions x 7 variables, provider update 2026-05-22;
  2024 granules end **2024-12-30**). Monthly and annual = **2024** (monthly updated 2025-11-11, annual 2025-09-15). There are no 2025 monthly or annual granules yet.
  The guide revision log says: "May 22nd, 2026: This release added daily gridded mosaics for 2025".
  Granule arithmetic [inferred]: daily 1176 = 7 vars x (46 yrs x 3 regions + 30 extra PR years 1950-1979); monthly 1650 = 5 vars x 2 formats x 165.
- **File names**: daily `daymet_v4_daily_<na|hi|pr>_<var>_<yyyy>.nc` (NetCDF only); monthly `daymet_v4_<var>_mon<avg|ttl>_<region>_<yyyy>.<nc|tif>`;
  annual `daymet_v4_<var>_ann<avg|ttl>_<region>_<yyyy>.<nc|tif>`. Only prcp is `ttl` (total); the others are `avg`. Monthly and annual granules cover **no srad and no dayl**. [seen]
- **HTTPS**: `https://data.ornldaac.earthdata.nasa.gov/protected/daymet/<Short>/data/<file>` -> **302** to `urs.earthdata.nasa.gov/oauth/authorize` ->
  **401** "HTTP Basic: Access denied." (0.6 s; tested daily .nc and monthly .tif). [seen]
- **S3**: `s3://ornl-cumulus-prod-protected/daymet/<Short>/data` (us-west-2); temporary credentials come from `https://data.ornldaac.earthdata.nasa.gov/s3credentials`
  (without EDL: 307 -> the URS login page, 200 HTML). An anonymous bucket listing gave **403 AccessDenied** for both `ornl-cumulus-prod-protected` and `ornl-cumulus-prod-public`.
  The `public` prefix serves documentation (the guide PDFs: 303 -> CloudFront, 200 `application/pdf`); a guessed `/public/.../data/*.nc` gave **404**. [seen]
  S3 direct access is meant for compute running in us-west-2 [inferred from `DirectDistributionInformation.Region`].
- **OPeNDAP (Hyrax)** `https://opendap.earthdata.nasa.gov/collections/<concept-id>/granules/<GranuleUR>` (for example `.../C2532426483-ORNL_CLOUD/granules/Daymet_Daily_V4R1.daymet_v4_daily_hi_tmin_2025.nc.dmr`):
  302 -> `/login/urs` -> **401**. The root page `https://opendap.earthdata.nasa.gov/` is 200. Daily granules list a "USE SERVICE API" OPeNDAP link; the monthly granule
  inspected did not list one, although the monthly collection is associated with service S2874702816 (OPeNDAP). [seen]
- **Harmony**: the monthly and annual collections are associated with "Harmony OPeNDAP SubSetter (HOSS) Geographic" (S2164732315-XYZ_PROV); the daily collection is associated
  only with OPeNDAP S2874702816. `https://harmony.earthdata.nasa.gov/capabilities?collectionId=C2532007210-ORNL_CLOUD` (no auth, 200, 0.81 s) reports
  bbox, dimension, shape and temporal subsetting, no reprojection and no time or area averaging, output NetCDF-4. A subset request
  `/C2532007210-ORNL_CLOUD/ogc-api-coverages/1.0.0/collections/all/coverage/rangeset?subset=lat(..)&subset=lon(..)&subset=time(..)` -> **303 -> URS login page**. [seen]
- **Licence in metadata**: UMM-C `UseConstraints.LicenseURL` = "Data Use Policy" `https://science.nasa.gov/earth-science/earth-science-data/data-information-policy`
  (that URL now returns **404**; the Earthdata page says "NASA promotes the full and open sharing of data..."). `AccessConstraints`: none. [seen]

## 4. Monthly and annual climatology products: sum or mean? [seen, quoted from the V4 R1 user guides]

Monthly guide (`Daymet_Monthly_V4R1.pdf`, revision 2025-11-11), Abstract: "Monthly averages are provided for minimum and maximum temperature, vapor pressure,
and snow water equivalent, and monthly totals are provided for the precipitation variable."
Parameter table (verbatim):

| Abbr | Units | Description |
|---|---|---|
| prcp | mm | "The total accumulated precipitation over the monthly period of the daily total precipitation. Sum of all forms of precipitation converted to a water-equivalent depth." |
| tmax | degrees C | "The average maximum temperature for a daily period over the entire monthly period." |
| tmin | degrees C | "The average minimum temperature for a daily period over the entire monthly period." |
| vp | Pa | "The average of the daily average partial pressure of water vapor over the monthly period." |
| swe | kg m-2 | "The average of the daily snow water equivalent ... over the monthly period." |

The annual guide (revision 2025-09-14) uses the same wording with "annual period". prcp is the annual total in mm; the others are annual means.
Monthly and annual temporal coverage: na and hi 1980-2024, PR 1950-2024. The MPC copy of the V4.0 monthly Zarr carries
`prcp: cell_methods "area: mean time: sum within days time: sum over days", units "mm", long_name "monthly total precipitation"` [seen].

So a monthly **precipitation** file from ORNL holds **monthly totals (mm per month)**, not means. Temperatures, vp and swe are **monthly means of
daily values**. No srad or dayl monthly product exists.
[inferred] Because the Daymet calendar drops Dec 31 in leap years, December totals in leap years cover 30 days; a server computing monthly sums from
daily data reproduces this automatically. A suggested server rule for the two variables ORNL does not summarise: srad = mean of daily
daylight-average W m-2, and optionally total MJ m-2 month-1 = sum(srad x dayl)/1e6 (the conversion formula is from the daily guide, Table 1); dayl = mean s/day.
A comparison of server-computed monthly sums against the ORNL monthly product was **not run** (no EDL; the MPC V4.0 chunks are about 12x2000x2000 float32, too large for a modest test).

## 5. Open cloud copies without credentials

**Microsoft Planetary Computer** [seen]
- STAC `https://planetarycomputer.microsoft.com/api/stac/v1/collections` (200, 1.18 s): `daymet-{daily,monthly,annual}-{na,hi,pr}` still exist.
- They are **Daymet Version 4.0, not V4 R1**, and **stop in 2020**: daily 1980-01-01 to 2020-12-30, monthly to 2020-12-16, annual to 2020-07-01. Zarr attributes are `Version_data "Daymet Data
  Version 4.0"`. Daily `time` shape 14965 (= 41 x 365), monthly 492 (= 41 x 12). `.zmetadata` Last-Modified: 2021-06-18 (daily) and 2021-06-09 (monthly).
  The 2020 data therefore predate the V4 R1 correction of 2020/2021 [inferred from the guide revision note].
- Access: `https://daymeteuwest.blob.core.windows.net/daymet-zarr/daily/na.zarr/.zmetadata` without a token -> **409 "Public access is not permitted on this
  storage account."** An anonymous SAS token from `https://planetarycomputer.microsoft.com/api/sas/v1/token/daymet-daily-na` (200, 0.78 s, no login) -> `.zmetadata`
  200 (0.6-0.7 s, 13 499 bytes). Daily chunks are `[365, 284, 584]` float32 with blosc-lz4 compression, so one point-year reads one chunk of up to about 240 MB uncompressed [inferred].
- STAC `license: proprietary`. Citation for daily-na in STAC: DOI 10.3334/ORNLDAAC/1840; the `sci:citation` field cites 1904 (monthly latency). These are inconsistent.
- Verdict: usable only for 1980-2020 V4.0 research or cross-checks; **not current**.

**AWS Open Data Registry** [seen] `https://registry.opendata.aws/nasa-daymet/` lists the V4 R1 daily, monthly, annual, xval and PR sub-daily collections as
`arn:aws:s3:::ornl-cumulus-prod-protected/daymet/...`, us-west-2, **"Controlled Access"**, "Access requires an Earthdata Login account". Licence line: "Creative Commons BY 4.0".
It is the NASA bucket, not an open copy. `awslabs/open-data-registry/main/datasets/daymet.yaml` -> 404.

**Google Earth Engine** [seen] `NASA/ORNL/DAYMET_V4`: catalog page reports availability 1980-01-01 to 2025-12-31, pixel size 1000 m, DOIs 1840 and 2129, terms "This dataset is in
the public domain and is available without restriction on use and distribution". Use requires an Earth Engine account [inferred; not run].

**ORNL "Daymet Version 4 Monthly Latency"** (DOI 10.3334/ORNLDAAC/1904): landing page temporal coverage 2021-01-01 to 2023-03-31; "Access is restricted for Daymet Version 4
Monthly Latency". Not in CMR (`doi=` search: 0 hits). Not usable. [seen]

## 6. Daymet "gridded subset" web services [seen]

a. **Tile Selection Tool**: `https://daymet.ornl.gov/gridded/` -> 302 -> `/tile-selection-tool-retirement`: "On Wednesday, July 6, the ORNL DAAC retired ... the Tile Selection Tool (TST)".
   2-degree tiles "continue to be available through THREDDS". That THREDDS path is now EDL-gated (§2). Scripts: `github.com/ornldaac/daymet-TDStiles-batch` (200).
b. **SDAT / OGC WCS** (`https://webmap.ornl.gov/ogc/index.jsp`, `dataset.jsp?ds_id=1343`, linked from `daymet.ornl.gov/getdata` as "Climatologies Through SDAT"): **DNS failure**
   (`gaierror -2 Name or service not known`). The service is gone, but the Get Data page still links to it.
c. **ORNL TESViS (MODIS/VIIRS) REST API** `https://modis.ornl.gov/rst/api/v1/` lists product `Daymet` ("Version 4 R1", daily, 1000 m). Bands: dayl s/day, prcp mm/day,
   srad W/m2, swe kg/m2, tmax and tmin degrees C, vp Pa (scale 1).
   - Arbitrary points (`/Daymet/dates?latitude=..&longitude=..`) -> **400 "No Daymet data available for <lat> <lon> location."** (tested at the NM cell and at the
     doc's own Oak Ridge example). Daymet is **fixed-sites only** (3868 sites: AmeriFlux, NEON, AERONET, ...).
   - Fixed site `/Daymet/us_colorado_niwot_ridge/dates` -> 16 790 dates, A1980001..A2025365. The daily dates are labelled with a MODIS-style DOY, and `A2025365` carries
     calendar_date 2025-12-31. `/subset?band=prcp&startDate=A2025001&endDate=A2025002` -> 9x9 cells, `xllcorner -456750, yllcorner -250500, cellsize 1000` (LCC metres,
     consistent with cell centres at x ≡ 250 and y ≡ 0 mod 1000), mm/day values.
   - Latency **9-27 s per request** (products 22.7 s, bands 18.7 s, subset 17.9 s). There is no auth. The doc limits non-site subsets to `kmAboveBelow/kmLeftRight <= 100` and 10 dates per request.
     Tool citation: "ORNL DAAC. 2018. Terrestrial Ecology Subsetting & Visualization Services (TESViS) RESTful Web Service. ... https://doi.org/10.3334/ORNLDAAC/1600".
   - Verdict: a useful credential-free daily grid (9x9 km, about 8 km on a side) **only at listed flux/NEON sites**. Too slow to be a primary backend.

## 7. Reference facts

- **Projection** [seen, guides]: Lambert Conformal Conic, WGS84, standard parallels 25 N and 60 N, central meridian -100, latitude of origin 42.5 N, false easting and northing 0.
  `+proj=lcc +lat_1=25 +lat_2=60 +lat_0=42.5 +lon_0=-100 +x_0=0 +y_0=0 +ellps=WGS84 +units=m +no_defs`. The MPC Zarr grid_mapping agrees
  (semi_major_axis 6378137, inverse_flattening 298.257223563). `sol/sol/Tiff.py` uses `+datum=WGS84` instead of `+ellps=WGS84`, which is numerically equivalent for this purpose [inferred].
- **Calendar** [seen, all three guides]: "All Daymet years, including leap years, have 1–365 days. For leap years, the Daymet data include leap day (February 29) and
  December 31 is discarded from leap years to maintain a 365-day year." Confirmed live: 2024 Dec 31 absent, Feb 29 present (§1); CMR 2024 daily granules end 2024-12-30.
- **Variables (daily guide, Table 1)** [seen]: dayl `s d-1` (daylight duration, flat horizon); prcp `mm` (daily total, all forms as water equivalent; the API labels it mm/day);
  srad `W m-2` (incident shortwave averaged **over the daylight period**; "Daily total radiation (MJ/m2/day) = (srad x dayl)/1,000,000"); swe `kg m-2`;
  tmax and tmin `degrees C` (2 m air); vp `Pa` (daily average partial pressure of water vapor).
- **Coverage** [seen, daily guide]: na and hi 1980-2025; PR 1950-2025. Bounding boxes: na -178.1333..-53.0567 E, 14.0749..82.9143 N; hi -160.3056..-154.772, 17.9539..23.5186;
  pr -67.9927..-64.1196, 16.8444..19.9382. Release cadence: each year is added after it closes (2022 on 2023-03-01, 2023 on 2024-04-23, 2024 on 2025-09-12, 2025 on 2026-05-22).
  "All Daymet data are provisional and subject to revision."
- **Recommended citations** [seen]:
  - Daily: Thornton, M.M., R. Shrestha, Y. Wei, P.E. Thornton, and S-C. Kao. 2022. Daymet: Daily Surface Weather Data on a 1-km Grid for North America, Version 4 R1. ORNL DAAC, Oak Ridge, Tennessee, USA. https://doi.org/10.3334/ORNLDAAC/2129
  - Monthly: ... 2022. Daymet: Monthly Climate Summaries on a 1-km Grid for North America, Version 4 R1. ... https://doi.org/10.3334/ORNLDAAC/2131
  - Annual: ... 2022. Daymet: Annual Climate Summaries on a 1-km Grid for North America, Version 4 R1. ... https://doi.org/10.3334/ORNLDAAC/2130
  - Method (daymet.ornl.gov/citations): Thornton, P.E., R. Shrestha, M. Thornton, S.-C. Kao, Y. Wei, and B.E. Wilson. 2021. Gridded daily weather data for North America with comprehensive uncertainty quantification. Scientific Data 8:190. https://doi.org/10.1038/s41597-021-00973-0 . The page asks for Thornton et al. 2000 (AFM 104:255-271) and Thornton & Running 1999 (AFM 93:211-228) in addition when the radiation and humidity data are used.
  - Single-pixel tool: Thornton, M.M., and R. Devarakonda. 2011. https://doi.org/10.3334/ORNLDAAC/2361
- **User guides** (the `daac.ornl.gov/DAYMET/guides/Daymet_<Daily|Monthly|Annual>_V4R1.html` URLs now 301 to the PDFs) [seen]:
  `https://data.ornldaac.earthdata.nasa.gov/public/daymet/Daymet_Daily_V4R1/comp/Daymet_Daily_V4R1.pdf` (revision 2026-05-22), and the same pattern for Monthly and Annual.
- **Licence**: no single licence string. NASA UMM-C points to the NASA Earth Science Data and Information Policy ("full and open sharing"); AWS registry: CC BY 4.0;
  Earth Engine: "public domain ... without restriction". All providers ask for the dataset DOI citation. [seen] The server should emit the 2129, 2131 or 2130 citation plus the
  tool citation it used. [inferred]

## 8. Not run / open questions

- No request with Earthdata credentials was made, so OPeNDAP, Harmony, HTTPS granule and S3 behaviour **after** login is untested.
- NCSS query semantics on the Hyrax successor: not tested.
- Single-pixel PR data before 1980: not tested.
- Server-computed monthly sums vs the ORNL monthly product: not compared.
- Single-pixel throughput under parallel load: not tested (all calls were sequential). There are no documented limits; politeness (e.g. at most 2-4 concurrent requests and caching) is an [inferred] design choice.
