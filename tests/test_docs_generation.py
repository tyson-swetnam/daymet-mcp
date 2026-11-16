# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""The generated docs (tool reference, configuration table) match the code; OKF is valid."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    "args",
    [
        ["scripts/gen_tools_reference.py", "--check"],
        ["scripts/gen_config_reference.py", "--check"],
        ["scripts/okf_validate.py", "docs"],
    ],
)
def test_generated_docs_in_sync(args: list[str]) -> None:
    proc = subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True, timeout=120, check=False
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_llms_txt_lists_every_content_page() -> None:
    llms = (ROOT / "docs" / "llms.txt").read_text(encoding="utf-8")
    full = (ROOT / "docs" / "llms-full.txt").read_text(encoding="utf-8")
    pages = [p for p in (ROOT / "docs").rglob("*.md") if p.name not in ("index.md", "log.md")]
    for page in pages:
        rel = page.relative_to(ROOT / "docs").with_suffix("")
        assert f"/{rel.as_posix()}/" in llms, rel
        assert page.read_text(encoding="utf-8").strip()[:200] in full, rel
