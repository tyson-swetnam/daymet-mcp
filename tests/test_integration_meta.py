# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Every registered tool has a hermetic unit test and a live (``network``) test."""

from __future__ import annotations

from pathlib import Path

from daymet_mcp import tools as _tools  # noqa: F401  (registration)
from daymet_mcp.registry import get_registered_tools

TESTS = Path(__file__).parent


def test_every_tool_has_unit_and_live_tests() -> None:
    unit = "\n".join(p.read_text(encoding="utf-8") for p in (TESTS / "tools").glob("test_*.py"))
    live = (TESTS / "live" / "test_live.py").read_text(encoding="utf-8")
    for spec in get_registered_tools():
        assert f'"{spec.name}"' in unit, f"{spec.name} has no unit test in tests/tools/"
        assert f'"{spec.name}"' in live, f"{spec.name} has no live test"
