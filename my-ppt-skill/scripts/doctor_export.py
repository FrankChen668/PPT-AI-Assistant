#!/usr/bin/env python3
"""Pre-export doctor checks for the SVG -> PPTX pipeline."""

from __future__ import annotations

import argparse
import importlib.util
import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from build_config.fallback_policy import load_fallback_policy

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_EXPECTED_CWD = SCRIPT_DIR.parent
CORE_EXPORTER = DEFAULT_EXPECTED_CWD / "ppt-ai-core" / "scripts" / "svg_to_pptx.py"

BAD_TAGS = {"foreignObject", "script"}


@dataclass
class DoctorFinding:
    severity: str
    code: str
    path: str
    message: str


@dataclass
class DoctorReport:
    project: str
    ok: bool
    errors: int
    warnings: int
    findings: list[DoctorFinding]
    scanned_svg_files: int
    report_md: Path
    report_json: Path


def _emit(findings: list[DoctorFinding], severity: str, code: str, path: Path, message: str) -> None:
    findings.append(DoctorFinding(severity=severity, code=code, path=str(path), message=message))


def _guidance(reason: str, correct_command: str, forbidden_action: str) -> str:
    return f"Reason: {reason} | Correct: {correct_command} | Forbidden: {forbidden_action}"


def _dependency_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[1] if "}" in tag else tag


def _is_output_locked(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with path.open("ab"):
            pass
        return False
    except PermissionError:
        return True
    except OSError:
        return True


def run_export_doctor(
    project_dir: Path,
    *,
    expected_cwd: Path | None = None,
    check_output_lock: bool = True,
) -> DoctorReport:
    project_dir = project_dir.resolve()
    expected_dir = (expected_cwd or DEFAULT_EXPECTED_CWD).resolve()
    findings: list[DoctorFinding] = []
    fallback_policy = load_fallback_policy(SCRIPT_DIR / "build_config" / "fallback_policy.json")

    qa_dir = project_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    report_md = qa_dir / "doctor-export-report.md"
    report_json = qa_dir / "doctor-export-report.json"

    if Path.cwd().resolve() != expected_dir:
        _emit(
            findings,
            "warning",
            "cwd-not-my-ppt-skill",
            Path.cwd(),
            _guidance(
                reason=f"Working directory is {Path.cwd()}, expected {expected_dir}",
                correct_command=f'cd "{expected_dir}"',
                forbidden_action="bypassing project pipeline with ad-hoc toolchains",
            ),
        )

    dependencies = [
        ("python-pptx", "pptx"),
        ("cairosvg", "cairosvg"),
        ("Pillow", "PIL"),
        ("lxml", "lxml"),
        ("defusedxml", "defusedxml"),
    ]
    for display_name, import_name in dependencies:
        if not _dependency_available(import_name):
            _emit(
                findings,
                "error",
                "missing-dependency",
                project_dir / "scripts" / "requirements.txt",
                _guidance(
                    reason=f"Missing dependency {display_name} (import: {import_name})",
                    correct_command="pip install -r scripts/requirements.txt",
                    forbidden_action="ad-hoc npm/pptxgenjs/custom python-pptx export scripts",
                ),
            )

    required_paths = [
        project_dir / "blueprint.json",
        project_dir / "design_spec.md",
    ]
    for path in required_paths:
        if not path.exists():
            _emit(
                findings,
                "error",
                "missing-required-file",
                path,
                _guidance(
                    reason=f"Required contract file is missing: {path.name}",
                    correct_command=(
                        f"python scripts/build_project.py {project_dir} --phase authoring --skip-render"
                    ),
                    forbidden_action="forcing finalize export without contract files",
                ),
            )

    svg_dir = project_dir / "svg_output"
    svg_files = sorted(svg_dir.glob("slide_*.svg"))
    if not svg_files:
        _emit(
            findings,
            "error",
            "missing-svg-output",
            svg_dir,
            _guidance(
                reason="No svg_output/slide_*.svg found (return to State 3 / Executor)",
                correct_command=f"python scripts/build_project.py {project_dir} --phase authoring --skip-render",
                forbidden_action="switching to Node.js/pptxgenjs/manual converter scripts",
            ),
        )

    for svg_file in svg_files:
        try:
            content = svg_file.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            _emit(
                findings,
                "error",
                "invalid-svg-utf8",
                svg_file,
                _guidance(
                    reason=f"Invalid UTF-8 at byte {exc.start}: {exc.reason}",
                    correct_command="Re-save the SVG file as UTF-8 and rerun doctor",
                    forbidden_action="changing exporter toolchain as first response",
                ),
            )
            continue

        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            _emit(
                findings,
                "error",
                "invalid-svg-xml",
                svg_file,
                _guidance(
                    reason=f"XML parse error: {exc}",
                    correct_command="Fix malformed SVG XML and rerun doctor",
                    forbidden_action="attempting export with malformed SVG",
                ),
            )
            continue

        for elem in root.iter():
            tag_name = _local_name(elem.tag)
            if tag_name in BAD_TAGS:
                _emit(
                    findings,
                    "error",
                    "forbidden-svg-node",
                    svg_file,
                    _guidance(
                        reason=f"Forbidden node <{tag_name}> detected",
                        correct_command="Use native SVG text/shape only and rerun doctor",
                        forbidden_action="embedding script/foreignObject nodes in delivery SVG",
                    ),
                )
                break

    if not CORE_EXPORTER.exists():
        _emit(
            findings,
            "error",
            "missing-core-exporter",
            CORE_EXPORTER,
            _guidance(
                reason="Core exporter entry is missing",
                correct_command="Restore ppt-ai-core/scripts/svg_to_pptx.py",
                forbidden_action="creating a temporary replacement exporter as default path",
            ),
        )

    output_native = project_dir / "exports" / "output-native.pptx"
    if check_output_lock and _is_output_locked(output_native):
        recovery_action = (
            "python scripts/build_project.py projects/<project> --phase finalize --skip-render "
            "--artifact-name semantic --enable-layout-lint --enable-visual-qa --strict "
            "--safe-area-profile presentation --snapshots"
            if fallback_policy.fallback_on_locked_stable_target
            else "python scripts/build_project.py projects/<project> --phase finalize --skip-render "
            "--enable-layout-lint --enable-visual-qa --strict --safe-area-profile presentation --snapshots"
        )
        _emit(
            findings,
            "error",
            "locked-output-pptx",
            output_native,
            _guidance(
                reason="Target PPTX appears locked by PowerPoint/WPS",
                correct_command=recovery_action,
                forbidden_action="repeated overwrite attempts while file lock remains",
            ),
        )

    errors = sum(1 for item in findings if item.severity == "error")
    warnings = sum(1 for item in findings if item.severity == "warning")
    ok = errors == 0

    payload: dict[str, Any] = {
        "project": str(project_dir),
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "scanned_svg_files": len(svg_files),
        "expected_cwd": str(expected_dir),
        "fallback_policy_version": fallback_policy.version,
        "findings": [asdict(item) for item in findings],
    }
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Export Doctor Report",
        "",
        f"- project: `{project_dir}`",
        f"- ok: `{ok}`",
        f"- errors: `{errors}`",
        f"- warnings: `{warnings}`",
        f"- scanned_svg_files: `{len(svg_files)}`",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("- No findings.")
    else:
        for item in findings:
            lines.append(f"- **{item.severity}** `{item.code}` at `{item.path}`: {item.message}")
    report_md.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    return DoctorReport(
        project=str(project_dir),
        ok=ok,
        errors=errors,
        warnings=warnings,
        findings=findings,
        scanned_svg_files=len(svg_files),
        report_md=report_md,
        report_json=report_json,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run export doctor checks before finalize export.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    parser.add_argument(
        "--expected-cwd",
        type=Path,
        default=DEFAULT_EXPECTED_CWD,
        help="Expected working directory (defaults to my-ppt-skill).",
    )
    parser.add_argument(
        "--no-output-lock-check",
        action="store_true",
        help="Disable output PPTX lock check.",
    )
    args = parser.parse_args(argv)

    report = run_export_doctor(
        args.project_dir,
        expected_cwd=args.expected_cwd,
        check_output_lock=not args.no_output_lock_check,
    )
    print(
        f"Export doctor {'passed' if report.ok else 'failed'}: "
        f"errors={report.errors}, warnings={report.warnings}, scanned_svg_files={report.scanned_svg_files}"
    )
    print(report.report_md)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
