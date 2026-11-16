# Agent guide — daymet-mcp

This repository holds **daymet-mcp**, a [Model Context Protocol](https://modelcontextprotocol.io/)
server (MCP 2026-07-28, stateless core) for Daymet V4 R1 surface weather data, and its
documentation. The server is Python 3.11+ on the `mcp` 2.x SDK: package `daymet_mcp` under
`src/`, console script `daymet-mcp`, tests under `tests/`. `docs/` is an **Open Knowledge Format
(OKF) v0.2 bundle** built with [Zensical](https://zensical.org): every content page carries YAML
frontmatter with `type` (Guide | Tutorial | Reference | Policy | MCP Tool Reference), `title`,
`description`, `tags`, provenance (`generated`, `sources`) and lifecycle (`status`,
`stale_after`). Section `index.md` files are OKF directory listings (no frontmatter);
`docs/log.md` is the dated change log. Conventions follow idss-mesa/neon-mcp (DESIGN.md D1).

## Reading the corpus

- `docs/llms.txt` — linked outline of every page; `docs/llms-full.txt` — the whole corpus.
- `DESIGN.md` — the design and decision register (D1-D21); `RESEARCH.md` — verified upstream facts.
- Pages without a `verified:` key are unverified; `status: draft` pages need review.
- For Daymet *data*, do not read the docs: run the server and call its tools.

## Commands

```bash
uv sync --all-extras                          # runtime + grid + docs + dev extras from uv.lock
uv run pytest                                 # hermetic tests (recorded fixtures; no network)
uv run pytest -m network tests/live           # live tests (ORNL DAAC single-pixel, NASA CMR)
uv run ruff check src tests scripts && uv run ruff format --check src tests scripts
uv run mypy src                               # strict
uv run python scripts/record_fixtures.py check
uv run daymet-mcp --check                     # offline self-test; --check --live adds one request

uv run python scripts/okf_validate.py docs    # OKF conformance (0 errors required)
uv run python scripts/gen_tools_reference.py  # regenerate docs/tools/reference.md
uv run python scripts/gen_config_reference.py # regenerate the settings table
uv run python scripts/gen_llms_txt.py         # regenerate docs/llms.txt and docs/llms-full.txt
uv run zensical build --clean --strict        # must print "No issues found"
```

## Rules

1. **Aggregation is explicit.** Monthly/annual `prcp` is a SUM (mm/month, mm/year); the other
   variables are means unless overridden. Never change a default aggregation, unit or field label
   without updating `daymet/catalog.py`, the aggregation guide, `docs/tools/aggregation.md`,
   DESIGN.md §3.1 and the tests.
2. **The Daymet calendar has 365 days**; leap years drop Dec 31. Never impute it.
3. **No credentials outside the environment.** The Earthdata token comes only from
   `DAYMET_MCP_EARTHDATA__TOKEN`; never read `~/.netrc` or cookies; never log or echo tokens.
4. **Tests stay hermetic.** Upstream calls go through `tests/fixture_router.py`; a test that makes
   an unrouted request fails. Live tests carry the `network` marker. New fixtures come from
   `scripts/record_fixtures.py record` and must pass `check`; synthetic fixtures are labelled
   `origin: synthetic`.
5. **Every tool** has a hermetic test in `tests/tools/`, a live test in `tests/live/test_live.py`
   and an entry in `tests/helpers.EVERY_TOOL_CALL` (enforced by `tests/test_integration_meta.py`).
6. **Docs**: every content page has OKF frontmatter (description 50-160 characters); index pages
   have none; add a `docs/log.md` entry for substantive changes; regenerate the reference,
   configuration table and llms files and commit them (CI fails on drift). Never add `verified:`.
7. **Source files** start with SPDX lines; Python is PEP 8 with full type hints (`mypy --strict`).
8. Commit subjects start with `FIX:`, `FEATURE:`, `REFACTOR:`, `DOCS:`, `CLEANUP:`, `MODERNIZE:` or
   `UPDATE:`; bodies say what, why and how it was tested.
