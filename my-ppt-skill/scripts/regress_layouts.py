#!/usr/bin/env python3
"""Exercise all supported Layout DSL tags through render, finalize, export, and QA."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from finalize_svg import finalize_project  # noqa: E402
from layout_contracts import layout_tags, sample_blueprint  # noqa: E402
from qa_project import run_qa  # noqa: E402
from render_svg import render_project  # noqa: E402
from svg_to_pptx import convert  # noqa: E402


def design_spec(page_count: int) -> str:
    return f"""# Design Spec
- canvas: ppt169
- style: regression
- primary_color: #101216
- accent_color: #00C2A8
- secondary_accent: #FF5A5F
- background_color: #F7F8FA
- card_bg: #FFFFFF
- text_color: #101216
- muted_color: #68707D
- data_palette: #00C2A8,#FF5A5F,#1E3A5F,#D4AC0D
- font_ladder: title 44/700 | body 20/400 | caption 12/400
- page_count: {page_count}
- audience: regression
- language: zh-CN
"""


def slide_visual_plan(tags: list[str]) -> dict[str, object]:
    slides: list[dict[str, object]] = []
    for idx, tag in enumerate(tags, start=1):
        slides.append(
            {
                "slide_id": idx,
                "layout_tag": tag,
                "visual_archetype": tag,
                "variation_rule": f"Exercise Layout DSL renderer for {tag} with a unique regression page.",
                "page_prompt_pattern": {
                    "pattern_id": f"layout-regression-{idx:02d}",
                    "conclusion_formula": "renderer contract first",
                    "block_structure": "layout-specific deterministic regions",
                    "composition_cues": ["stable geometry", "safe-area compliance", "export compatibility"],
                    "anti_patterns": ["unsupported SVG", "text outside safe area"],
                },
                "execution_policy": {
                    "scene_type": "layout_regression",
                    "generation_strategy": "deterministic_renderer",
                    "risk_level": "low",
                    "required_loop": "render_finalize_export_qa",
                    "qa_strictness": "non_blocking",
                    "expected_first_pass_rules": ["render succeeds", "native export succeeds", "QA warning-clean"],
                },
                "layout_objective": (
                    f"Validate deterministic geometry, export compatibility, "
                    f"and QA cleanliness for {tag}."
                ),
                "density_budget": {"max_text_nodes": 36, "max_chars": 1200},
                "dominance_map": ["title", "content", "footer"],
                "must_keep_claims": ["AI"],
                "visual_contract": {
                    "scene_type": "layout_regression",
                    "generation_strategy": "deterministic_renderer",
                    "focal_point": "layout contract geometry",
                    "primary_read_path": ["title", "content", "footer"],
                    "composition_grammar": "Layout DSL deterministic geometry",
                    "hierarchy_ladder": "title > section labels > body",
                    "density_budget": {"max_text_nodes": 36, "max_chars": 1200},
                    "whitespace_target": "regression-safe",
                    "template_inheritance": "none; canonical layout sample",
                    "anti_patterns": ["unsafe SVG", "missing text", "safe-area spill"],
                    "critic_checks": ["content shape valid", "export succeeds", "QA stays warning-clean"],
                    "layout_intent": f"cover renderer coverage for {tag}",
                    "bbox_budget": {"safe_area": [60, 60, 1160, 600], "footer_band": [70, 625, 1140, 48]},
                    "text_budget": {"max_chars": 1200, "max_lines_per_block": 4},
                    "deterministic_scaffold": {"renderer": "render_svg.py", "layout_tag": tag},
                    "must_avoid": ["foreignObject", "external assets", "safe-area overflow"],
                    "pre_authoring_checks": ["sample content matches contract", "design tokens are present"],
                },
            }
        )
    return {"slides": slides}


def create_project(project_dir: Path) -> None:
    if project_dir.exists():
        shutil.rmtree(project_dir)
    for name in ("svg_output", "svg_final", "exports", "qa"):
        (project_dir / name).mkdir(parents=True, exist_ok=True)
    tags = layout_tags()
    (project_dir / "design_spec.md").write_text(design_spec(len(tags)), encoding="utf-8")
    (project_dir / "blueprint.json").write_text(
        json.dumps(sample_blueprint(tags), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (project_dir / "art_direction.md").write_text(
        "# Art Direction\n\n- direction: deterministic Layout DSL regression fixture\n",
        encoding="utf-8",
    )
    (project_dir / "reference_pack.json").write_text(
        json.dumps(
            {
                "mode": "free_design",
                "free_design_override_reason": "Layout renderer regression fixture; no delivery template required.",
                "selected_references": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_dir / "slide_visual_plan.json").write_text(
        json.dumps(slide_visual_plan(tags), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (project_dir / "style_route.json").write_text(
        json.dumps(
            {"style_profile": "presentation", "confidence": 1.0, "requires_style_drafts": False},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise RuntimeError(f"Layout regression did not produce {label}: {path}")


def write_manifest(project_dir: Path, pptx_path: Path, slide_count: int, qa_errors: int, qa_warnings: int) -> None:
    exports_dir = project_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "project_name": project_dir.name,
        "timestamp": datetime.now().strftime("%Y%m%d-%H%M"),
        "phase": "layout-regression",
        "mode": "native",
        "output_files": [str(pptx_path.relative_to(project_dir))],
        "slide_count": slide_count,
        "artifact_created": pptx_path.exists(),
        "qa_errors": qa_errors,
        "qa_warnings": qa_warnings,
        "stage_parse_sec": 0.0,
        "stage_render_sec": 0.0,
        "stage_finalize_sec": 0.0,
        "stage_export_sec": 0.0,
        "stage_qa_sec": 0.0,
        "stage_total_sec": 0.0,
        "stage_failure_code": "none",
        "stage_failure_source": "none",
    }
    (exports_dir / "manifest.json").write_text(
        json.dumps({"records": [record]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run(project_dir: Path, snapshots: bool = False) -> int:
    create_project(project_dir)
    tags = layout_tags()
    render_project(project_dir, clean=True)
    finalize_project(project_dir)
    pptx_path = project_dir / "exports" / "layout-regression-native.pptx"
    convert(project_dir, "svg_final", pptx_path, mode="native")
    require_file(pptx_path, "native PPTX")
    report = run_qa(
        project_dir, svg_dir_name="svg_final", pptx="exports/layout-regression-native.pptx", snapshots=snapshots
    )
    require_file(project_dir / "qa" / "report.md", "QA report")
    write_manifest(project_dir, pptx_path, len(tags), report.errors, report.warnings)
    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Layout DSL regression coverage.")
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=ROOT / "projects" / "_layout_regression",
        help="Temporary project directory to create.",
    )
    parser.add_argument("--snapshots", action="store_true", help="Render QA snapshots and contact sheet.")
    args = parser.parse_args(argv)
    return run(args.project_dir, args.snapshots)


if __name__ == "__main__":
    raise SystemExit(main())
