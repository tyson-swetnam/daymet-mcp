#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Render docs/tools/reference.md from the live tool registry (no network).

Rewritten after idss-mesa/neon-mcp ``scripts/gen_tools_reference.py`` (MIT; see NOTICE).
Every registered tool gets a section: title, description, surface, transports, token
requirement, annotations, upstream endpoints, an input table (the names clients send) and
the top-level result fields. Tools are sorted by name, so the output is deterministic.
``generated.at`` is kept from the existing file while the body is unchanged.

Usage: python scripts/gen_tools_reference.py [--check] [--generated-at ISO]
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "docs" / "tools" / "reference.md"
sys.path.insert(0, str(ROOT / "src"))

from daymet_mcp import tools as _tools  # noqa: E402,F401  (registration)
from daymet_mcp.registry import ToolSpec, get_registered_tools  # noqa: E402
from daymet_mcp.server import DaymetServer  # noqa: E402


def _type(schema: dict[str, Any], defs: dict[str, Any]) -> str:
    if "$ref" in schema:
        name = str(schema["$ref"]).rsplit("/", 1)[-1]
        target = defs.get(name, {})
        if "enum" in target:
            return " \\| ".join(f"`{v}`" for v in target["enum"])
        return f"object ({name})"
    if "anyOf" in schema:
        parts = [_type(s, defs) for s in schema["anyOf"] if s.get("type") != "null"]
        nullable = any(s.get("type") == "null" for s in schema["anyOf"])
        return " \\| ".join(parts) + (" \\| null" if nullable else "")
    if "enum" in schema:
        return " \\| ".join(f"`{v}`" for v in schema["enum"])
    kind = schema.get("type")
    if kind == "array":
        return f"array of {_type(schema.get('items', {}), defs)}"
    if kind == "object" and isinstance(schema.get("additionalProperties"), dict):
        return f"map of {_type(schema['additionalProperties'], defs)}"
    return str(kind or "any")


def _bounds(schema: dict[str, Any]) -> str:
    parts = []
    for key, sym in (
        ("minimum", ">="),
        ("maximum", "<="),
        ("minLength", "len >="),
        ("maxLength", "len <="),
        ("minItems", "items >="),
        ("maxItems", "items <="),
    ):
        if key in schema:
            parts.append(f"{sym} {schema[key]}")
    if "pattern" in schema:
        parts.append(f"pattern `{schema['pattern']}`")
    for sub in schema.get("anyOf", []):
        if sub.get("type") != "null":
            inner = _bounds(sub)
            if inner:
                parts.append(inner)
    return "; ".join(parts)


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def input_rows(spec: ToolSpec) -> list[str]:
    schema = DaymetServer.input_schema(spec)
    defs = schema.get("$defs", {})
    required = set(schema.get("required", []))
    rows = []
    for name, prop in schema.get("properties", {}).items():
        default_txt = (
            f"`{json.dumps(prop['default'])}`" if "default" in prop and name not in required else ""
        )
        rows.append(
            f"| `{name}` | {_type(prop, defs)} | {'yes' if name in required else 'no'} "
            f"| {default_txt} | {_cell(_bounds(prop))} | {_cell(prop.get('description', ''))} |"
        )
    return rows


def output_fields(spec: ToolSpec) -> str:
    schema = DaymetServer.output_schema(spec)
    names = list(schema.get("properties", {}))
    return ", ".join(f"`{n}`" for n in names)


def render_body() -> str:
    specs = get_registered_tools()
    out = [
        "# Tool reference",
        "",
        "Generated from the tool registry by `scripts/gen_tools_reference.py`; do not edit by "
        "hand. Every result also carries the envelope fields `resolved`, `notes`, `nextSteps` and "
        "`source`, and errors are tool results with `structuredContent.error = {code, message, "
        "details, hint?}`.",
        "",
        "| Tool | Title | Transports | Earthdata token |",
        "| --- | --- | --- | --- |",
    ]
    for spec in specs:
        token = {True: "required", False: "no", "optional": "optional"}[spec.requires_token]
        out.append(
            f"| [`{spec.name}`](#{spec.name}) | {spec.title} | "
            f"{', '.join(sorted(spec.transports))} | {token} |"
        )
    for spec in specs:
        token = {True: "required", False: "no", "optional": "optional (large areas)"}[
            spec.requires_token
        ]
        out += [
            "",
            f"## {spec.name}",
            "",
            f"**{spec.title}.** {spec.description}",
            "",
            f"- Surface: `{spec.surface}`; transports: {', '.join(sorted(spec.transports))}; "
            f"Earthdata token: {token}.",
            f"- Annotations: readOnly={str(spec.read_only).lower()}, "
            f"destructive={str(spec.destructive).lower()}, "
            f"idempotent={str(spec.idempotent).lower()}, "
            f"openWorld={str(spec.open_world).lower()}.",
            "- Upstream: " + (", ".join(f"`{e}`" for e in spec.endpoints) or "none (local)") + ".",
            "",
        ]
        rows = input_rows(spec)
        if rows:
            out += [
                "| Argument | Type | Required | Default | Bounds | Description |",
                "| --- | --- | --- | --- | --- | --- |",
                *rows,
            ]
        else:
            out.append("No arguments.")
        out += ["", f"Result fields: {output_fields(spec)}."]
    return "\n".join(out) + "\n"


FRONT = """---
title: "Tool reference"
description: "Every daymet-mcp tool with its inputs, bounds, result fields, upstream endpoints and annotations, generated from the registry."
type: MCP Tool Reference
tags:
  - tools
  - reference
generated:
  by: "process:scripts/gen_tools_reference.py"
  at: "{at}"
sources:
  - id: registry
    resource: "src/daymet_mcp/registry.py"
    title: "daymet-mcp tool registry"
    author: "team:daymet-mcp"
status: stable
---

"""


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--generated-at")
    args = parser.parse_args()
    body = render_body()
    old = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
    m = re.search(r'^  at: "([^"]+)"', old, re.MULTILINE)
    old_body = old.split("---\n\n", 1)[1] if "---\n\n" in old else ""
    if args.generated_at:
        at = args.generated_at
    elif m and old_body == body:
        at = m.group(1)
    else:
        at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT00:00:00Z")
    new = FRONT.format(at=at) + body
    if args.check:
        if old_body != body:
            print(
                "docs/tools/reference.md is out of date; run python scripts/gen_tools_reference.py"
            )
            return 1
        print("tool reference is up to date")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(new, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(ROOT)} ({len(get_registered_tools())} tools)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
