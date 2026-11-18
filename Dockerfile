# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
#
# daymet-mcp: stateless Streamable HTTP image (stdio also works: docker run -i ... --transport stdio).
# Base images are pinned by digest: python 3.13.15 (Debian) and uv 0.13.8. Dependencies are
# installed from the hash-pinned uv.lock (`uv sync --frozen` verifies every sha256), and so is the
# build backend: hatchling comes from the locked `build` group, not from an unhashed PyPI resolve.

ARG PYTHON_IMAGE=python@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b
ARG UV_IMAGE=ghcr.io/astral-sh/uv@sha256:81a1340fea1e72ad4a8e9a016128b0c61041cf182ea49fd788023e52842bc147

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /usr/local/bin/uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./
# Runtime dependencies plus the `build` group (hatchling, hash-locked in uv.lock).
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
# Build daymet-mcp with that verified hatchling (no isolated build env resolved from PyPI
# without hashes), then drop the build group from the runtime venv.
RUN uv sync --frozen --no-dev --no-editable --no-build-isolation \
 && uv sync --frozen --no-dev --no-default-groups --no-editable --no-build-isolation

FROM ${PYTHON_IMAGE}
RUN useradd --create-home --uid 10001 --user-group daymet
COPY --from=build --chown=10001:10001 /app/.venv /app/.venv
USER 10001
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    DAYMET_MCP_SERVER__TRANSPORT=http \
    DAYMET_MCP_SERVER__HOST=0.0.0.0 \
    DAYMET_MCP_SERVER__PORT=8080 \
    DAYMET_MCP_DOWNLOADS__DIR=/tmp/daymet-downloads
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4).status == 200 else 1)"]
CMD ["daymet-mcp"]
