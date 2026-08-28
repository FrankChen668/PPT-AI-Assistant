#!/usr/bin/env python3
"""Guardrail checks for mainline import paths."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for path in (ROOT).rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("ppt_master/"):
            continue
        files.append(path)
    return sorted(files)


def main() -> int:
    issues: list[str] = []
    forbidden_patterns = (
        re.compile(r"^\s*from\s+config\.build_options\s+import\s+", re.MULTILINE),
        re.compile(r"^\s*from\s+config(?:\.[A-Za-z_][A-Za-z0-9_]*)?\s+import\s+", re.MULTILINE),
        re.compile(r"^\s*import\s+config(?:\s|$|\.)", re.MULTILINE),
    )

    for path in _iter_python_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in forbidden_patterns:
            if pattern.search(text):
                issues.append(f"{path}: forbidden mainline config import matched `{pattern.pattern}`")
                break

    stages_path = ROOT / "pipeline" / "stages.py"
    if stages_path.exists():
        stages_text = stages_path.read_text(encoding="utf-8", errors="replace")
        if "from build_config.build_options import PhaseOptions" not in stages_text:
            issues.append(
                f"{stages_path}: expected import `from build_config.build_options import PhaseOptions` not found."
            )

    if issues:
        print("Mainline import guard failed:", file=sys.stderr)
        for item in issues:
            print(f"- {item}", file=sys.stderr)
        return 1

    print("Mainline import guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
