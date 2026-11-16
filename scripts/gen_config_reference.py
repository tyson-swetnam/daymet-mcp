#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Render the settings table in docs/getting-started/configuration.md.

Adapted from idss-mesa/neon-mcp ``scripts/gen_config_reference.py`` (MIT; see NOTICE).
Walks ``daymet_mcp.config.Config`` and writes one row per setting (YAML path, environment
variable ``DAYMET_MCP_<SECTION>__<FIELD>``, type, default, description) between the
``BEGIN GENERATED CONFIG`` / ``END GENERATED CONFIG`` markers. Deterministic.

Usage: python scripts/gen_config_reference.py [--check]
"""

from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path
from typing import Any, Union, get_args, get_origin

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "docs" / "getting-started" / "configuration.md"
BEGIN = "<!-- BEGIN GENERATED CONFIG (scripts/gen_config_reference.py; do not edit) -->"
END = "<!-- END GENERATED CONFIG -->"
sys.path.insert(0, str(ROOT / "src"))

from pydantic import BaseModel  # noqa: E402

from daymet_mcp.config import Config  # noqa: E402


def _type_name(annotation: Any) -> str:
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        return " \\| ".join(_type_name(a) for a in get_args(annotation))
    if origin is list:
        return f"list[{_type_name(get_args(annotation)[0])}]"
    if type(annotation).__name__ == "_LiteralGenericAlias":
        return " \\| ".join(f"`{a}`" for a in get_args(annotation))
    if annotation is type(None):
        return "null"
    return getattr(annotation, "__name__", str(annotation))


def _default(field: Any) -> str:
    if field.default_factory is not None:
        value = field.default_factory()
        if isinstance(value, BaseModel):
            return ""
    else:
        value = field.default
    if value is None:
        return "unset"
    if isinstance(value, bool):
        return "`true`" if value else "`false`"
    if isinstance(value, list):
        return "`[" + ", ".join(str(v) for v in value) + "]`"
    return f"`{value}`"


def rows(model: type[BaseModel], path: tuple[str, ...] = ()) -> list[str]:
    out: list[str] = []
    for name, field in model.model_fields.items():
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            out.extend(rows(annotation, (*path, name)))
            continue
        dotted = ".".join((*path, name))
        env = "DAYMET_MCP_" + "__".join(p.upper() for p in (*path, name))
        desc = (field.description or "").replace("|", "\\|")
        if dotted == "earthdata.token":
            dotted += " (env only)"
        out.append(
            f"| `{dotted}` | `{env}` | {_type_name(annotation)} | {_default(field)} | {desc} |"
        )
    return out


def render() -> str:
    header = (
        "| Setting (YAML path) | Environment variable | Type | Default | Description |\n"
        "| --- | --- | --- | --- | --- |"
    )
    return f"{BEGIN}\n\n{header}\n" + "\n".join(rows(Config)) + f"\n\n{END}"


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = TARGET.read_text(encoding="utf-8")
    start, end = text.find(BEGIN), text.find(END)
    if start < 0 or end < 0:
        print(f"markers missing in {TARGET}", file=sys.stderr)
        return 2
    new = text[:start] + render() + text[end + len(END) :]
    if args.check:
        if new != text:
            print("configuration table is out of date; run python scripts/gen_config_reference.py")
            return 1
        print("configuration table is up to date")
        return 0
    TARGET.write_text(new, encoding="utf-8")
    print(f"wrote configuration table ({len(rows(Config))} settings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
