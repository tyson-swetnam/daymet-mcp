# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Live tests (marker ``network``; run with ``pytest -m network``). Real upstream, no router."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from daymet_mcp.config import Config
from daymet_mcp.server import DaymetServer, create_server


@pytest.fixture
async def live_server(tmp_path: Path) -> AsyncIterator[DaymetServer]:
    config = Config.model_validate({"downloads": {"dir": str(tmp_path / "downloads")}})
    server = create_server(config, transport="stdio")
    yield server
    await server.aclose()
