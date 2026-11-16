# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Importing this package registers every tool (side effect)."""

from daymet_mcp.tools import area, catalog, cell, citation, core, point

__all__ = ["area", "catalog", "cell", "citation", "core", "point"]
