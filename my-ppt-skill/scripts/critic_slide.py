#!/usr/bin/env python3
"""Sidecar CLI: generate per-slide critic report for AI-authored SVG."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from canvas_context import load_canvas_context  # noqa: E402
from lint_svg_layout import lint_svg_file  # noqa: E402
from pipeline.critic_report import build_critic_report, write_critic_reports  # noqa: E402
from svg_quality_checker import check_svg_file  # noqa: E402


def _code_from_svg_quality_message(message: str) -> str:
    lowered = (message or "").strip().lower()
    if "contrast too low" in lowered or "contrast low" in lowered:
        return "contrast-too-low"
    if "missing viewbox" in lowered:
        return "missing-viewbox"
    if "unexpected viewbox" in lowered:
        return "invalid-viewbox"
    return "svg-quality"


def _collect_findings(project_dir: Path, svg_file: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    canvas = load_canvas_context(project_dir)

    lint_findings: list[Any] = []
    lint_svg_file(svg_file, lint_findings, canvas)
    for item in lint_findings:
        findings.append(
            {
                "severity": getattr(item, "severity", "warning"),
                "code": getattr(item, "code", "unknown"),
                "source": "lint_svg_layout",
                "message": getattr(item, "message", ""),
            }
        )

    quality = check_svg_file(svg_file, canvas_key=canvas.key)
    for message in quality.errors:
        findings.append(
            {
                "severity": "error",
                "code": _code_from_svg_quality_message(message),
                "source": "svg_quality_checker",
                "message": message,
            }
        )
    for message in quality.warnings:
        findings.append(
            {
                "severity": "warning",
                "code": _code_from_svg_quality_message(message),
                "source": "svg_quality_checker",
                "message": message,
            }
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate sidecar critic report for one SVG slide.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    parser.add_argument("--slide", type=int, required=True, help="Slide id to check (e.g. --slide 4).")
    args = parser.parse_args(argv)

    project_dir = args.project_dir.resolve()
    slide = int(args.slide)
    svg_file = project_dir / "svg_output" / f"slide_{slide:02d}.svg"
    if not svg_file.exists():
        print(f"missing SVG: {svg_file}", file=sys.stderr)
        return 1

    findings = _collect_findings(project_dir, svg_file)
    report = build_critic_report(project_dir, slide, findings)
    json_path, _ = write_critic_reports(report, project_dir / "qa")
    print(f"critic report written: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
