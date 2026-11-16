# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Shared fixtures: hermetic router, config, server factory."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from daymet_mcp.config import Config
from daymet_mcp.logging import forget_secrets
from daymet_mcp.server import DaymetServer, create_server
from tests.fixture_router import FixtureRouter


class FakeSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


@pytest.fixture(autouse=True)
def _isolate() -> Iterator[None]:
    yield
    forget_secrets()


@pytest.fixture
def router() -> Iterator[FixtureRouter]:
    r = FixtureRouter()
    yield r
    assert not r.unexpected, f"unexpected upstream calls: {r.unexpected}"


@pytest.fixture
def fake_sleep() -> FakeSleep:
    return FakeSleep()


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config.model_validate({"downloads": {"dir": str(tmp_path / "downloads")}})


@pytest.fixture
async def make_server(
    config: Config, router: FixtureRouter, fake_sleep: FakeSleep
) -> AsyncIterator[Callable[..., DaymetServer]]:
    servers: list[DaymetServer] = []

    def _make(
        *,
        transport: str = "stdio",
        token: str | None = None,
        config: Config | None = None,
        **_: Any,
    ) -> DaymetServer:
        cfg = (config or base).model_copy(deep=True)
        if token:
            cfg.earthdata.token = SecretStr(token)
        server = create_server(
            cfg,
            transport=transport,
            http_transport=router.transport,  # type: ignore[arg-type]
            sleep=fake_sleep,
        )
        servers.append(server)
        return server

    base = config
    yield _make
    for s in servers:
        await s.aclose()


@pytest.fixture
async def server(make_server: Callable[..., DaymetServer]) -> DaymetServer:
    return make_server()


@pytest.fixture
async def http_server(make_server: Callable[..., DaymetServer]) -> DaymetServer:
    return make_server(transport="http")
