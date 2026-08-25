#!/usr/bin/env python3
"""PPTX export adapter using ppt-ai-core backend.

Public behavior kept for existing callers:
- convert(project_dir, input_dir, output, mode)
- CLI flags: --input-dir / --output / --mode

Authority contract:
- This file is a thin adapter only.
- The authoritative exporter implementation lives in `ppt-ai-core/scripts/svg_to_pptx.py`.
- Default delivery entrypoint remains `scripts/build_project.py --phase finalize --skip-render`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from export.raster import render_svg_to_png as _render_svg_to_png

SCRIPT_DIR = Path(__file__).resolve().parent
CORE_SVG_TO_PPTX = SCRIPT_DIR.parent / "ppt-ai-core" / "scripts" / "svg_to_pptx.py"
NATIVE_CONVERSION_REPORT = "native-conversion-report.json"


def stable_output_name(mode: str) -> str:
    return "output-native.pptx" if mode == "native" else "output.pptx"


def actual_output_path(requested_output: Path, mode: str) -> Path:
    if mode == "raster":
        legacy_output = requested_output.parent / f"{requested_output.stem}_svg{requested_output.suffix}"
        if legacy_output.exists():
            return legacy_output
    return requested_output


def native_conversion_report_path(project_dir: Path) -> Path:
    return project_dir.resolve() / "exports" / NATIVE_CONVERSION_REPORT


def load_native_conversion_report(project_dir: Path) -> dict[str, object]:
    report_path = native_conversion_report_path(project_dir)
    if not report_path.exists():
        raise RuntimeError(f"native_conversion_report_missing: {report_path}")
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"native_conversion_report_invalid: {report_path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("summary"), dict):
        raise RuntimeError(f"native_conversion_report_invalid: {report_path}")
    return payload


def convert(
    project_dir: Path,
    input_dir: str | None,
    output: Path | None,
    mode: str = "native",
    timeout_sec: float | None = None,
) -> Path:
    project_dir = project_dir.resolve()
    if not CORE_SVG_TO_PPTX.exists():
        raise FileNotFoundError(f"Missing core exporter: {CORE_SVG_TO_PPTX}")

    if output:
        out_path = output
    else:
        name = stable_output_name(mode)
        out_path = project_dir / "exports" / name
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if mode not in {"native", "raster"}:
        raise ValueError(f"Unsupported mode: {mode}")

    report_path = native_conversion_report_path(project_dir)
    report_signature_before = None
    if mode == "native" and report_path.exists():
        stat = report_path.stat()
        report_signature_before = (stat.st_mtime_ns, stat.st_size)

    # Mapping:
    # - native -> core --only native
    # - raster -> core --only legacy (image-based compatibility output)
    source = input_dir or "final"
    args = [
        sys.executable,
        str(CORE_SVG_TO_PPTX),
        str(project_dir),
        "-s",
        source,
        "-o",
        str(out_path),
        "--only",
        "native" if mode == "native" else "legacy",
        "-q",
    ]
    timeout = timeout_sec if isinstance(timeout_sec, (int, float)) and timeout_sec and timeout_sec > 0 else None
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"export_timeout: core exporter exceeded timeout ({timeout}s)") from exc
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(details or "ppt-ai-core exporter failed")
    if mode == "native":
        # A zero exit code only means the package was written. Integrity and
        # delivery classification come from the structured conversion report.
        load_native_conversion_report(project_dir)
        stat = report_path.stat()
        if report_signature_before == (stat.st_mtime_ns, stat.st_size):
            raise RuntimeError(f"native_conversion_report_stale: {report_path}")
    return actual_output_path(out_path, mode)


def render_svg_to_png(svg_file: Path, png_file: Path) -> None:
    """Backward-compatible raster helper used by QA snapshots."""
    _render_svg_to_png(svg_file, png_file)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert AI-PPT SVG slides to a PPTX file.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    parser.add_argument(
        "--input-dir",
        help="Relative SVG directory inside the project. Defaults to svg_final, then svg_output.",
    )
    parser.add_argument("--output", type=Path, help="Output PPTX path.")
    parser.add_argument(
        "--mode",
        choices=("raster", "native"),
        default="native",
        help="native (default): editable DrawingML; raster: PNG embed for max visual fidelity.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=None,
        help="Optional export subprocess timeout in seconds; disabled by default.",
    )
    args = parser.parse_args(argv)

    try:
        out_path = convert(args.project_dir, args.input_dir, args.output, args.mode, timeout_sec=args.timeout_sec)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
