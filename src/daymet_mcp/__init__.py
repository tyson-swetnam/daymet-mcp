# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""daymet-mcp: an MCP server for Daymet V4 R1 surface weather data."""

__version__ = "0.1.0"

USER_AGENT = f"daymet-mcp/{__version__} (+https://github.com/idss-mesa)"

__all__ = ["USER_AGENT", "__version__"]
