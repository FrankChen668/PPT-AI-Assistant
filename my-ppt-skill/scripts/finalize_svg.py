#!/usr/bin/env python3
"""Finalize SVG via ppt-ai-core pipeline and shared standards checks."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

from check_svg_encoding import format_issues, validate_project_svg_output
from svg_quality_checker import check_svg_file

SCRIPT_DIR = Path(__file__).resolve().parent
CORE_SCRIPTS_DIR = SCRIPT_DIR.parent / "ppt-ai-core" / "scripts"


def _load_core_finalize_main():
    core_file = CORE_SCRIPTS_DIR / "finalize_svg.py"
    if not core_file.exists():
        raise FileNotFoundError(f"Missing core finalize script: {core_file}")
    spec = importlib.util.spec_from_file_location("ppt_ai_core_finalize_svg", core_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module spec from {core_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "main"):
        raise RuntimeError(f"Core finalize script has no main(): {core_file}")
    return module.main


def _post_finalize_warnings(project_dir: Path) -> int:
    svg_final = project_dir / "svg_final"
    if not svg_final.exists():
        return 0
    warnings = 0
    for svg_file in sorted(svg_final.glob("*.svg")):
        result = check_svg_file(svg_file)
        for item in result.warnings:
            print(f"warning: {svg_file.name}: {item}", file=sys.stderr)
        warnings += len(result.warnings)
    return warnings


def _system_exit_code(exc: SystemExit) -> int:
    if exc.code is None:
        return 0
    return exc.code if isinstance(exc.code, int) else 1


def finalize_project(project_dir: Path) -> int:
    project_dir = project_dir.resolve()
    encoding_issues = validate_project_svg_output(project_dir)
    if encoding_issues:
        raise RuntimeError(format_issues(project_dir, encoding_issues))

    core_main = _load_core_finalize_main()

    prev_cwd = Path.cwd()
    try:
        # Keep relative paths and icon/template discovery in core script stable.
        import os

        os.chdir(SCRIPT_DIR.parent)
        old_argv = list(sys.argv)
        try:
            sys.argv = [str(CORE_SCRIPTS_DIR / "finalize_svg.py"), str(project_dir)]
            try:
                core_main()
            except SystemExit as exc:
                code = _system_exit_code(exc)
                if code != 0:
                    raise RuntimeError(f"Core finalize failed with exit code {code}") from exc
        finally:
            sys.argv = old_argv
    finally:
        import os

        os.chdir(prev_cwd)

    return _post_finalize_warnings(project_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize AI-PPT SVG slides for export.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    args = parser.parse_args(argv)

    try:
        warning_count = finalize_project(args.project_dir)
    except SystemExit as exc:
        return _system_exit_code(exc)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if warning_count:
        print(f"Completed with {warning_count} warning(s).")
    else:
        print("Completed without warnings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
