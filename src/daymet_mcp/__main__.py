# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Command line: ``daymet-mcp`` (stdio) or ``daymet-mcp --transport http``.

``--check`` runs an offline self-test (config + schemas); ``--check --live`` adds one
``daymet_ping(check_upstream=true)``. ``--print-config`` prints the effective configuration
with the token redacted. Configuration errors exit with code 2 and never echo values.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from daymet_mcp import __version__
from daymet_mcp.config import Config, ConfigError, load_config


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="daymet-mcp", description="MCP server for Daymet V4 R1 data.")
    p.add_argument("--transport", choices=["stdio", "http"], help="Transport (default stdio).")
    p.add_argument("--host", help="HTTP bind address (default 127.0.0.1).")
    p.add_argument("--port", type=int, help="HTTP port (default 8080).")
    p.add_argument("--config", help="YAML configuration file.")
    p.add_argument("--log-level", help="DEBUG, INFO, WARNING or ERROR.")
    p.add_argument("--downloads-dir", help="Directory for daymet_download_area (stdio).")
    p.add_argument("--check", action="store_true", help="Offline self-test, then exit.")
    p.add_argument("--live", action="store_true", help="With --check: one live upstream request.")
    p.add_argument(
        "--print-config", action="store_true", help="Print the redacted config and exit."
    )
    p.add_argument("--version", action="version", version=f"daymet-mcp {__version__}")
    return p


def cli_overrides(ns: argparse.Namespace) -> dict[str, Any]:
    server: dict[str, Any] = {}
    if ns.transport:
        server["transport"] = ns.transport
    if ns.host:
        server["host"] = ns.host
    if ns.port:
        server["port"] = ns.port
    if ns.log_level:
        server["log_level"] = ns.log_level
    out: dict[str, Any] = {"server": server} if server else {}
    if ns.downloads_dir:
        out["downloads"] = {"dir": ns.downloads_dir}
    return out


async def self_check(config: Config, live: bool) -> dict[str, Any]:
    import jsonschema

    from daymet_mcp.server import create_server

    server = create_server(config, transport=config.server.transport)
    try:
        tools = server.tool_definitions()
        for tool in tools:
            jsonschema.Draft202012Validator.check_schema(tool.input_schema)
            if tool.output_schema is not None:
                jsonschema.Draft202012Validator.check_schema(tool.output_schema)
        report: dict[str, Any] = {
            "ok": True,
            "version": __version__,
            "tools": [t.name for t in tools],
        }
        if live:
            outcome = await server.call("daymet_ping", {"check_upstream": True})
            report["ping"] = outcome.payload
            report["ok"] = not outcome.is_error and bool(
                (outcome.payload.get("upstream") or {}).get("ok")
            )
        return report
    finally:
        await server.aclose()


def main(argv: list[str] | None = None) -> None:
    ns = build_parser().parse_args(argv)
    try:
        config = load_config(ns.config, cli=cli_overrides(ns))
    except ConfigError as exc:
        print(f"daymet-mcp: {exc}", file=sys.stderr)
        sys.exit(2)
    if ns.print_config:
        print(json.dumps(config.model_dump_redacted(), indent=1))
        return
    from daymet_mcp.logging import setup_logging

    setup_logging(config.server.log_level, config.server.transport)
    if ns.check:
        import anyio

        report = anyio.run(self_check, config, ns.live)
        print(json.dumps(report, indent=1))
        sys.exit(0 if report["ok"] else 1)
    from daymet_mcp.server import run

    run(config)


if __name__ == "__main__":
    main()
