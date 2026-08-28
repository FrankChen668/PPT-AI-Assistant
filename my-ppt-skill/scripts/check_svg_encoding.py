#!/usr/bin/env python3
"""Validate that SVG files are strict UTF-8 decodable."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SvgEncodingIssue:
    path: Path
    offset: int
    byte_value: int
    reason: str


def _collect_svg_files(project_dir: Path, pattern: str) -> list[Path]:
    svg_dir = project_dir / "svg_output"
    return sorted(svg_dir.glob(pattern))


def validate_utf8(paths: Iterable[Path]) -> list[SvgEncodingIssue]:
    issues: list[SvgEncodingIssue] = []
    for path in paths:
        payload = path.read_bytes()
        try:
            payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            bad_byte = payload[exc.start] if exc.start < len(payload) else 0
            issues.append(
                SvgEncodingIssue(
                    path=path,
                    offset=exc.start,
                    byte_value=bad_byte,
                    reason=exc.reason,
                )
            )
    return issues


def validate_project_svg_output(project_dir: Path, pattern: str = "slide_*.svg") -> list[SvgEncodingIssue]:
    return validate_utf8(_collect_svg_files(project_dir, pattern))


def format_issues(project_dir: Path, issues: list[SvgEncodingIssue], limit: int = 10) -> str:
    header = [
        "Invalid UTF-8 bytes detected in svg_output/.",
        "Fix the listed SVG files before finalize/export.",
        "Suggested fix: rewrite the affected SVG with explicit UTF-8 encoding, then rerun build.",
    ]
    rows: list[str] = []
    for item in issues[:limit]:
        try:
            rel_path = item.path.relative_to(project_dir)
        except ValueError:
            rel_path = item.path
        rows.append(
            f"- {rel_path}: byte_offset={item.offset}, byte=0x{item.byte_value:02x}, reason={item.reason}"
        )
    if len(issues) > limit:
        rows.append(f"- ... {len(issues) - limit} more file(s)")
    return "\n".join(header + rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check svg_output/slide_*.svg for UTF-8 encoding validity.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    parser.add_argument("--pattern", default="slide_*.svg", help="Glob pattern under svg_output/.")
    args = parser.parse_args(argv)

    project_dir = args.project_dir.resolve()
    svg_dir = project_dir / "svg_output"
    if not svg_dir.exists():
        print(f"error: svg_output directory not found: {svg_dir}", file=sys.stderr)
        return 1

    issues = validate_project_svg_output(project_dir, pattern=args.pattern)
    if issues:
        print(format_issues(project_dir, issues), file=sys.stderr)
        return 1

    print(f"UTF-8 check passed: {len(_collect_svg_files(project_dir, args.pattern))} SVG file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
