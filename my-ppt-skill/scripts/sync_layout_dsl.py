#!/usr/bin/env python3
"""Sync layout-dsl.md Expected content blocks from layout_contracts.py.

This keeps docs aligned with contracts without reformatting geometry prose.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from layout_contracts import expected_content, layout_tags

SECTION_RE = re.compile(r"^##\s+\d+\.\s+(?P<tag>[A-Za-z0-9\-]+)\s*$", re.MULTILINE)


def replace_expected_content(md: str, tag: str) -> str:
    """Replace the first ```json block after `Expected content:` within a layout section."""
    skeleton = expected_content(tag)
    block = "```json\n" + json.dumps(skeleton, ensure_ascii=False, indent=2) + "\n```\n"

    matches = list(SECTION_RE.finditer(md))
    for i, m in enumerate(matches):
        if m.group("tag") != tag:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        section = md[start:end]

        expected_idx = section.find("Expected content:")
        if expected_idx < 0:
            return md
        after_expected = section[expected_idx:]
        fence_start = after_expected.find("```json")
        if fence_start < 0:
            return md
        fence_end = after_expected.find("```", fence_start + 1)
        if fence_end < 0:
            return md
        fence_end = after_expected.find("```", fence_end + 3)
        if fence_end < 0:
            return md
        fence_end += 3

        prefix = section[:expected_idx] + after_expected[:fence_start]
        suffix = after_expected[fence_end:]
        new_section = prefix + block + suffix
        return md[:start] + new_section + md[end:]

    return md


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync references/layout-dsl.md from layout contracts.")
    parser.add_argument(
        "--path",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "references" / "layout-dsl.md",
        help="Path to layout-dsl.md",
    )
    args = parser.parse_args(argv)

    path = args.path.resolve()
    md = path.read_text(encoding="utf-8")
    original = md
    for tag in layout_tags():
        md = replace_expected_content(md, tag)

    if md != original:
        path.write_text(md, encoding="utf-8")
        print(f"Updated {path}")
    else:
        print(f"No changes needed: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

