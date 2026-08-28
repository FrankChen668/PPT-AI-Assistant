#!/usr/bin/env python3
"""Copyfit contract validation for dense slides.

Dense slides must provide a slide_plan.json contract before finalize/export.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REQUIRED_BLOCK_KEYS = {"id", "box", "max_lines", "font_size_range", "compress_rule"}
VALID_COMPRESS_RULES = {"shorten", "drop_secondary", "split"}
VALID_PRIORITIES = {"must", "should", "can"}


@dataclass
class ContractFinding:
    severity: str
    code: str
    path: str
    message: str


@dataclass
class ContractReport:
    ok: bool
    errors: int
    warnings: int
    findings: list[ContractFinding]
    dense_slide_ids: list[int]
    covered_dense_slide_ids: list[int]
    report_path: Path


def _emit(findings: list[ContractFinding], severity: str, code: str, path: str, message: str) -> None:
    findings.append(ContractFinding(severity=severity, code=code, path=path, message=message))


def _collect_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_collect_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_collect_text(v) for v in value)
    return ""


def _dense_score(slide: dict[str, Any]) -> int:
    content = slide.get("content", {})
    text_len = len(_collect_text(content))
    list_weight = 0
    if isinstance(content, dict):
        for value in content.values():
            if isinstance(value, list):
                list_weight += len(value) * 40
    return text_len + list_weight


def _list_footprint(slide: dict[str, Any]) -> tuple[int, int]:
    content = slide.get("content", {})
    list_fields = 0
    max_len = 0
    if isinstance(content, dict):
        for value in content.values():
            if isinstance(value, list):
                list_fields += 1
                max_len = max(max_len, len(value))
    return list_fields, max_len


def is_dense_slide(slide: dict[str, Any]) -> bool:
    score = _dense_score(slide)
    list_fields, max_len = _list_footprint(slide)
    tag = str(slide.get("layout_tag", ""))
    if score >= 320:
        return True
    if list_fields >= 3 or max_len >= 5:
        return True
    if tag in {"Grid-Six-Icons", "Flow-Steps", "Capability-Mapping", "Roadmap-MultiPhase"} and max_len >= 4:
        return True
    return False


def _load_blueprint(project_dir: Path, findings: list[ContractFinding]) -> list[dict[str, Any]]:
    path = project_dir / "blueprint.json"
    if not path.exists():
        _emit(
            findings,
            "warning",
            "missing-blueprint",
            str(path),
            "blueprint.json not found; skip dense-slide contract enforcement for this run.",
        )
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        _emit(findings, "warning", "invalid-blueprint", str(path), f"Could not parse JSON: {exc}")
        return []
    slides = payload.get("slides")
    if not isinstance(slides, list):
        _emit(
            findings,
            "warning",
            "invalid-blueprint-slides",
            str(path),
            "blueprint.json slides is invalid; skip dense-slide contract enforcement.",
        )
        return []
    return [slide for slide in slides if isinstance(slide, dict)]


def _load_slide_plan(project_dir: Path, findings: list[ContractFinding]) -> dict[int, list[dict[str, Any]]]:
    path = project_dir / "slide_plan.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _emit(findings, "error", "invalid-slide-plan", str(path), f"Could not parse JSON: {exc}")
        return {}
    if not isinstance(payload, dict):
        _emit(findings, "error", "invalid-slide-plan-root", str(path), "slide_plan.json root must be an object.")
        return {}
    slides = payload.get("slides")
    if not isinstance(slides, list):
        _emit(findings, "error", "invalid-slide-plan-slides", str(path), "slide_plan.json must contain slides array.")
        return {}

    parsed: dict[int, list[dict[str, Any]]] = {}
    for idx, slide in enumerate(slides, start=1):
        base_path = f"{path}/slides/{idx}"
        if not isinstance(slide, dict):
            _emit(findings, "error", "invalid-slide-plan-slide", base_path, "Each slide must be an object.")
            continue
        slide_id = slide.get("slide_id", slide.get("id"))
        if not isinstance(slide_id, int):
            _emit(findings, "error", "invalid-slide-plan-slide-id", base_path, "slide_id must be an integer.")
            continue
        blocks = slide.get("blocks")
        if not isinstance(blocks, list):
            _emit(findings, "error", "invalid-slide-plan-blocks", base_path, "blocks must be an array.")
            continue
        valid_blocks: list[dict[str, Any]] = []
        for bidx, block in enumerate(blocks, start=1):
            bpath = f"{base_path}/blocks/{bidx}"
            if not isinstance(block, dict):
                _emit(findings, "error", "invalid-slide-plan-block", bpath, "block must be an object.")
                continue
            missing = REQUIRED_BLOCK_KEYS - set(block)
            if missing:
                _emit(
                    findings,
                    "error",
                    "missing-slide-plan-block-keys",
                    bpath,
                    f"Missing keys: {', '.join(sorted(missing))}.",
                )
                continue
            if not isinstance(block.get("id"), str) or not block["id"].strip():
                _emit(findings, "error", "invalid-slide-plan-block-id", bpath, "id must be a non-empty string.")
            box = block.get("box")
            if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box)):
                _emit(findings, "error", "invalid-slide-plan-box", bpath, "box must be [x, y, w, h] numbers.")
            max_lines = block.get("max_lines")
            if not isinstance(max_lines, int) or max_lines <= 0:
                _emit(findings, "error", "invalid-slide-plan-max-lines", bpath, "max_lines must be a positive integer.")
            font_range = block.get("font_size_range")
            if not (
                isinstance(font_range, list)
                and len(font_range) == 2
                and all(isinstance(v, (int, float)) for v in font_range)
                and float(font_range[0]) <= float(font_range[1])
            ):
                _emit(
                    findings,
                    "error",
                    "invalid-slide-plan-font-range",
                    bpath,
                    "font_size_range must be [min, max] with numeric values.",
                )
            if block.get("compress_rule") not in VALID_COMPRESS_RULES:
                _emit(
                    findings,
                    "error",
                    "invalid-slide-plan-compress-rule",
                    bpath,
                    f"compress_rule must be one of {sorted(VALID_COMPRESS_RULES)}.",
                )
            priority = block.get("priority")
            if priority is not None and priority not in VALID_PRIORITIES:
                _emit(
                    findings,
                    "warning",
                    "invalid-slide-plan-priority",
                    bpath,
                    f"priority should be one of {sorted(VALID_PRIORITIES)}.",
                )
            valid_blocks.append(block)
        parsed[slide_id] = valid_blocks
    return parsed


def _write_report(project_dir: Path, report: ContractReport) -> None:
    payload = {
        "ok": report.ok,
        "errors": report.errors,
        "warnings": report.warnings,
        "dense_slide_ids": report.dense_slide_ids,
        "covered_dense_slide_ids": report.covered_dense_slide_ids,
        "findings": [asdict(item) for item in report.findings],
    }
    report_json = project_dir / "qa" / "copyfit-contract-report.json"
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Copyfit Contract Report",
        "",
        f"- project: `{project_dir}`",
        f"- ok: `{report.ok}`",
        f"- errors: `{report.errors}`",
        f"- warnings: `{report.warnings}`",
        f"- dense_slide_ids: `{report.dense_slide_ids}`",
        f"- covered_dense_slide_ids: `{report.covered_dense_slide_ids}`",
        "",
        "## Findings",
        "",
    ]
    if not report.findings:
        lines.append("- No findings.")
    else:
        for item in report.findings:
            lines.append(f"- **{item.severity}** `{item.code}` at `{item.path}`: {item.message}")
    report.report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_copyfit_contract(project_dir: Path) -> ContractReport:
    project_dir = project_dir.resolve()
    findings: list[ContractFinding] = []
    slides = _load_blueprint(project_dir, findings)
    dense_slide_ids = sorted(
        slide["id"] for slide in slides if isinstance(slide.get("id"), int) and is_dense_slide(slide)
    )

    plan_path = project_dir / "slide_plan.json"
    if dense_slide_ids and not plan_path.exists():
        _emit(
            findings,
            "error",
            "missing-slide-plan",
            str(plan_path),
            "Dense slides detected; slide_plan.json is required before finalize/export.",
        )
        report = ContractReport(
            ok=False,
            errors=sum(1 for item in findings if item.severity == "error"),
            warnings=sum(1 for item in findings if item.severity == "warning"),
            findings=findings,
            dense_slide_ids=dense_slide_ids,
            covered_dense_slide_ids=[],
            report_path=project_dir / "qa" / "copyfit-contract-report.md",
        )
        _write_report(project_dir, report)
        return report

    slide_plan = _load_slide_plan(project_dir, findings)
    covered_dense_slide_ids: list[int] = []
    for slide_id in dense_slide_ids:
        blocks = slide_plan.get(slide_id, [])
        if not blocks:
            _emit(
                findings,
                "error",
                "missing-dense-slide-blocks",
                str(plan_path),
                f"Dense slide {slide_id} has no contract blocks in slide_plan.json.",
            )
            continue
        covered_dense_slide_ids.append(slide_id)

    errors = sum(1 for item in findings if item.severity == "error")
    warnings = sum(1 for item in findings if item.severity == "warning")
    report = ContractReport(
        ok=errors == 0,
        errors=errors,
        warnings=warnings,
        findings=findings,
        dense_slide_ids=dense_slide_ids,
        covered_dense_slide_ids=covered_dense_slide_ids,
        report_path=project_dir / "qa" / "copyfit-contract-report.md",
    )
    _write_report(project_dir, report)
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Validate dense-slide copyfit contract from slide_plan.json.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    args = parser.parse_args(argv)
    report = validate_copyfit_contract(args.project_dir)
    print(
        "Copyfit contract "
        f"{'passed' if report.ok else 'failed'}: errors={report.errors}, warnings={report.warnings}"
    )
    print(report.report_path)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
