# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""A real stdio server process whose upstream is the hermetic fixture router.

Used by ``tests/transport/test_stdio.py``: ``python -m tests.helpers.fixture_stdio <downloads>``.
It runs the production :func:`daymet_mcp.transport.stdio.serve_stdio`; only the HTTP
transport underneath the upstream client is replaced, so no network is used.
"""

from __future__ import annotations

import sys

import anyio

from daymet_mcp.config import Config
from daymet_mcp.logging import setup_logging
from daymet_mcp.server import create_server
from daymet_mcp.transport.stdio import serve_stdio
from tests.fixture_router import FixtureRouter


async def _no_sleep(seconds: float) -> None:
    del seconds


def main() -> None:
    setup_logging("info", "stdio")
    router = FixtureRouter()
    config = Config.model_validate({"downloads": {"dir": sys.argv[1]}})
    server = create_server(
        config, transport="stdio", http_transport=router.transport, sleep=_no_sleep
    )
    anyio.run(serve_stdio, server)
    if router.unexpected:
        print(f"unexpected upstream calls: {router.unexpected}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
