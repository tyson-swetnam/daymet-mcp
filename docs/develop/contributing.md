---
title: "Contributing"
description: "How to contribute to daymet-mcp: setup, the checks CI runs, code style, commit messages and the documentation rules."
type: Guide
tags:
  - contributing
  - ci
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

# Contributing

```bash
uv sync --all-extras
uv run ruff check src tests scripts && uv run ruff format --check src tests scripts
uv run mypy src
uv run pytest
python scripts/okf_validate.py docs
python scripts/gen_tools_reference.py --check && python scripts/gen_config_reference.py --check
```

* Python 3.11+, full type hints, `mypy --strict`, ruff rules `E,F,I,UP,B,SIM,S,RUF`, line length 100.
* Every source file starts with SPDX lines (`SPDX-FileCopyrightText`, `SPDX-License-Identifier: MIT`).
* Commit subjects start with `FIX:`, `FEATURE:`, `REFACTOR:`, `DOCS:`, `CLEANUP:`, `MODERNIZE:` or
  `UPDATE:`; the body says what changed, why, and how it was tested.
* The build backend is pinned (`hatchling==1.33.0`) and hash-locked in `uv.lock` (`build` group).
  CI and the Dockerfile install it first (`uv sync --frozen ... --no-install-project`) and then
  build the project with `--no-build-isolation`, so nothing unhashed is fetched. A plain local
  `uv sync` still uses an isolated build env (exact version, but no hash check).
* CI (`.github/workflows/ci.yml`, actions pinned by commit SHA) runs lint, type checks and tests on
  Python 3.11-3.13, a conformance job, the docs checks, and a nightly live job.
* Documentation pages carry OKF frontmatter; see `AGENTS.md` for the rules.
