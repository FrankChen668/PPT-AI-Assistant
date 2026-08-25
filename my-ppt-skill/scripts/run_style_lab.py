#!/usr/bin/env python3
"""[experimental] Run style-lab regression across multiple style profiles on the same project."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from generate_art_direction import generate_art_direction
from qa_project import run_qa
from route_style_profile import generate_style_route

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_OUT_ROOT = SKILL_DIR / "projects" / "style-lab" / "experiments"
DEFAULT_PROFILES = (
    "executive_exhibit",
    "luxury_finance",
    "engineering_blueprint",
    "ai_product_keynote",
    "editorial_report",
)


@dataclass
class StyleLabRow:
    profile: str
    project_dir: str
    ok: bool
    errors: int
    warnings: int
    advisories: int
    visual_score: float | None
    visual_diversity_warning_count: int
    style_over_cardization: bool
    style_rhythm_monotony: bool
    conclusion_first: bool
    takeaway_bar_present: bool
    visual_whitespace_ratio: float
    visual_hierarchy_depth_score: float
    visual_dominant_point_count: int
    visual_repetition_penalty: float
    visual_alignment_quality_score: float
    qa_report_path: str


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _set_style_profile(project_dir: Path, style_profile: str) -> None:
    spec = project_dir / "design_spec.md"
    if not spec.exists():
        raise FileNotFoundError(f"Missing design_spec.md: {spec}")
    lines = spec.read_text(encoding="utf-8").splitlines()
    style_written = False
    profile_written = False
    updated: list[str] = []
    for raw in lines:
        line = raw.strip()
        if line.startswith("- style:"):
            updated.append(f"- style: {style_profile}")
            style_written = True
            continue
        if line.startswith("- style_profile:"):
            updated.append(f"- style_profile: {style_profile}")
            profile_written = True
            continue
        updated.append(raw)
    if not style_written:
        updated.append(f"- style: {style_profile}")
    if not profile_written:
        updated.append(f"- style_profile: {style_profile}")
    spec.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def _auto_select_style_draft(project_dir: Path) -> None:
    drafts_path = project_dir / "style_drafts.json"
    if not drafts_path.exists():
        return
    payload = _load_json(drafts_path)
    if payload.get("mode") != "style_drafts":
        return
    selected_template = payload.get("selected_template")
    selected_draft = payload.get("selected_draft_id")
    if selected_template and selected_draft:
        return
    drafts = payload.get("drafts")
    if not isinstance(drafts, list) or not drafts:
        return
    first = drafts[0] if isinstance(drafts[0], dict) else {}
    draft_id = str(first.get("draft_id") or "").strip()
    template_id = str(first.get("template_id") or "").strip()
    if not draft_id or not template_id:
        return
    payload["selected_draft_id"] = draft_id
    payload["selected_template"] = template_id
    drafts_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_style_lab_metrics(qa_payload: dict[str, Any]) -> dict[str, Any]:
    metrics = qa_payload.get("metrics")
    findings = qa_payload.get("findings")
    if not isinstance(metrics, dict):
        metrics = {}
    if not isinstance(findings, list):
        findings = []
    codes = {
        str(item.get("code"))
        for item in findings
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }
    style_checks = metrics.get("style_profile_checks")
    if not isinstance(style_checks, dict):
        style_checks = {}

    return {
        "visual_score": qa_payload.get("visual_score"),
        "visual_diversity_warning_count": int(metrics.get("visual_diversity_warning_count") or 0),
        "style-over-cardization": "style-over-cardization" in codes,
        "style-rhythm-monotony": "style-rhythm-monotony" in codes,
        "conclusion-first": "style-conclusion-first-weak" not in codes,
        "takeaway_bar_present": bool(style_checks.get("takeaway_bar_present", False)),
        "visual_whitespace_ratio": float(metrics.get("visual_whitespace_ratio") or 0.0),
        "visual_hierarchy_depth_score": float(metrics.get("visual_hierarchy_depth_score") or 0.0),
        "visual_dominant_point_count": int(metrics.get("visual_dominant_point_count") or 0),
        "visual_repetition_penalty": float(metrics.get("visual_repetition_penalty") or 0.0),
        "visual_alignment_quality_score": float(metrics.get("visual_alignment_quality_score") or 0.0),
    }


def _write_reports(case_dir: Path, rows: list[StyleLabRow]) -> tuple[Path, Path]:
    json_path = case_dir / "style-lab-report.json"
    md_path = case_dir / "style-lab-report.md"
    payload = {
        "case_dir": str(case_dir),
        "profiles": [asdict(row) for row in rows],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Style Lab Report",
        "",
        f"- profiles tested: `{len(rows)}`",
        "",
        (
            "| profile | visual_score | whitespace | hierarchy_depth | dominant_pts | "
            "repetition_penalty | alignment_quality | diversity_warn | cardization | "
            "rhythm_monotony | conclusion_first | takeaway_bar | ok |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|---|",
    ]
    for row in rows:
        score = f"{row.visual_score:.2f}" if isinstance(row.visual_score, (int, float)) else "n/a"
        lines.append(
            f"| {row.profile} | {score} | "
            f"{row.visual_whitespace_ratio:.2f} | "
            f"{row.visual_hierarchy_depth_score:.2f} | "
            f"{row.visual_dominant_point_count} | "
            f"{row.visual_repetition_penalty:.2f} | {row.visual_alignment_quality_score:.2f} | "
            f"{row.visual_diversity_warning_count} | "
            f"{'Y' if row.style_over_cardization else 'N'} | "
            f"{'Y' if row.style_rhythm_monotony else 'N'} | "
            f"{'Y' if row.conclusion_first else 'N'} | {'Y' if row.takeaway_bar_present else 'N'} | "
            f"{'PASS' if row.ok else 'FAIL'} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def run_style_lab(
    source_project: Path,
    *,
    profiles: list[str],
    out_root: Path = DEFAULT_OUT_ROOT,
    quality_mode: str = "premium",
) -> tuple[Path, Path]:
    source_project = source_project.resolve()
    if not source_project.exists():
        raise FileNotFoundError(f"Project not found: {source_project}")
    case_dir = (out_root.resolve() / source_project.name)
    case_dir.mkdir(parents=True, exist_ok=True)

    rows: list[StyleLabRow] = []
    for profile in profiles:
        variant_dir = case_dir / profile
        if variant_dir.exists():
            shutil.rmtree(variant_dir)
        shutil.copytree(source_project, variant_dir)
        _set_style_profile(variant_dir, profile)
        generate_style_route(variant_dir, overwrite=True)
        generate_art_direction(variant_dir, overwrite=True)
        _auto_select_style_draft(variant_dir)
        report = run_qa(
            variant_dir,
            svg_dir_name="svg_output",
            enable_visual_qa=True,
            quality_mode=quality_mode,
            strict=False,
        )
        qa_payload = _load_json(variant_dir / "qa" / "report.json")
        metrics = extract_style_lab_metrics(qa_payload)
        rows.append(
            StyleLabRow(
                profile=profile,
                project_dir=str(variant_dir),
                ok=report.ok,
                errors=report.errors,
                warnings=report.warnings,
                advisories=report.advisories,
                visual_score=metrics["visual_score"],
                visual_diversity_warning_count=metrics["visual_diversity_warning_count"],
                style_over_cardization=bool(metrics["style-over-cardization"]),
                style_rhythm_monotony=bool(metrics["style-rhythm-monotony"]),
                conclusion_first=bool(metrics["conclusion-first"]),
                takeaway_bar_present=bool(metrics["takeaway_bar_present"]),
                visual_whitespace_ratio=float(metrics["visual_whitespace_ratio"]),
                visual_hierarchy_depth_score=float(metrics["visual_hierarchy_depth_score"]),
                visual_dominant_point_count=int(metrics["visual_dominant_point_count"]),
                visual_repetition_penalty=float(metrics["visual_repetition_penalty"]),
                visual_alignment_quality_score=float(metrics["visual_alignment_quality_score"]),
                qa_report_path=str(variant_dir / "qa" / "report.json"),
            )
        )

    return _write_reports(case_dir, rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run style-lab across multiple style profiles.")
    parser.add_argument("project_dir", type=Path, help="Source project path to clone for style-lab.")
    parser.add_argument(
        "--profiles",
        default=",".join(DEFAULT_PROFILES),
        help="Comma-separated style profiles (2-5 recommended).",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=DEFAULT_OUT_ROOT,
        help="Output root for experiments: projects/style-lab/experiments/<case>/",
    )
    parser.add_argument(
        "--quality-mode",
        choices=("dev-fast", "release-safe", "premium"),
        default="premium",
        help="QA severity mode for cross-profile scoring.",
    )
    args = parser.parse_args(argv)
    print("[experimental] run_style_lab is a research utility; use scripts/run_mode.py for mainline delivery.")

    profiles = [item.strip() for item in args.profiles.split(",") if item.strip()]
    if len(profiles) < 2 or len(profiles) > 5:
        print("error: --profiles should include 2-5 style profiles for meaningful comparison.")
        return 2
    try:
        json_path, md_path = run_style_lab(
            args.project_dir,
            profiles=profiles,
            out_root=args.out_root,
            quality_mode=args.quality_mode,
        )
    except Exception as exc:
        print(f"error: {exc}")
        return 1

    print(json_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
