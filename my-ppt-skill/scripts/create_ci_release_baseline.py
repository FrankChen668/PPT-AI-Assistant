#!/usr/bin/env python3
"""Create the deterministic one-slide positive fixture for CI baseline delivery."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

from create_ai_trends_demo import (
    ART_DIRECTION,
    BLUEPRINT,
    DESIGN_SPEC,
    REFERENCE_PACK,
    SLIDE_VISUAL_PLAN,
    STYLE_ROUTE,
)
from render_svg import render_project

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
DEFAULT_PROJECT = ROOT / "projects" / "ci-release-baseline"
SOURCE_SLIDE_ID = 6


def _fixture_blueprint() -> dict[str, object]:
    slide = deepcopy(
        next(item for item in BLUEPRINT["slides"] if item["id"] == SOURCE_SLIDE_ID)
    )
    slide["id"] = 1
    return {"slides": [slide]}


def _fixture_visual_plan() -> dict[str, object]:
    plan = deepcopy(
        next(
            item
            for item in SLIDE_VISUAL_PLAN["slides"]
            if item["slide_id"] == SOURCE_SLIDE_ID
        )
    )
    plan["slide_id"] = 1
    plan["variation_rule"] = "Use the deterministic one-page CI baseline composition."
    pattern = plan.get("page_prompt_pattern")
    if isinstance(pattern, dict):
        pattern["pattern_id"] = "ci-release-baseline-01"
    return {"slides": [plan]}


def create_project(project_dir: Path = DEFAULT_PROJECT, *, render: bool = True) -> Path:
    project_dir = project_dir.resolve()
    if project_dir.exists() and any(project_dir.iterdir()):
        raise FileExistsError(f"CI baseline fixture target must be empty: {project_dir}")
    for name in ("svg_output", "svg_final", "exports", "qa"):
        (project_dir / name).mkdir(parents=True, exist_ok=True)

    design_spec = DESIGN_SPEC.replace("- page_count: 10", "- page_count: 1")
    reference_pack = deepcopy(REFERENCE_PACK)
    reference_pack["free_design_override_reason"] = (
        "Deterministic one-slide CI release-safe baseline fixture."
    )

    (project_dir / "design_spec.md").write_text(design_spec, encoding="utf-8")
    (project_dir / "outline.md").write_text(
        "# CI Release Baseline\n\n1. 落地抓手\n",
        encoding="utf-8",
    )
    (project_dir / "blueprint.json").write_text(
        json.dumps(_fixture_blueprint(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (project_dir / "art_direction.md").write_text(ART_DIRECTION, encoding="utf-8")
    (project_dir / "reference_pack.json").write_text(
        json.dumps(reference_pack, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (project_dir / "slide_visual_plan.json").write_text(
        json.dumps(_fixture_visual_plan(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (project_dir / "style_route.json").write_text(
        json.dumps(STYLE_ROUTE, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if render:
        render_project(project_dir, output_dir="svg_output", clean=True)
    return project_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=DEFAULT_PROJECT)
    args = parser.parse_args(argv)
    project = create_project(args.project_dir)
    print(f"Created CI release baseline fixture: {project}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
