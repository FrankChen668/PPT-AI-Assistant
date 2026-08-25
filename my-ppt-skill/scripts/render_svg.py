#!/usr/bin/env python3
"""Render blueprint.json into per-slide SVG files.

The renderer is intentionally layered:

- render_theme.py parses design tokens and text metrics.
- svg_canvas.py owns SVG primitives and wrapping helpers.
- layout_renderers.py maps layout_tag values to geometry rules.
- render_svg.py wires project files to the renderer and exposes the CLI.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from blueprint_schema import validate_blueprint_schema
from layout_renderers import LayoutRenderer
from render_theme import FONT_STACK, SAFE_H, SAFE_W, SAFE_X, SAFE_Y, H, Theme, W, visual_width

__all__ = [
    "FONT_STACK",
    "H",
    "LayoutRenderer",
    "SAFE_H",
    "SAFE_W",
    "SAFE_X",
    "SAFE_Y",
    "Theme",
    "W",
    "render_project",
    "visual_width",
]


def _load_slide_plan_metadata(project_dir: Path) -> dict[int, dict[str, object]]:
    slide_plan_path = project_dir / "slide_plan.json"
    if not slide_plan_path.exists():
        return {}
    try:
        payload = json.loads(slide_plan_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    slides = payload.get("slides")
    if not isinstance(slides, list):
        return {}

    parsed: dict[int, dict[str, object]] = {}
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        slide_id = slide.get("slide_id", slide.get("id"))
        if not isinstance(slide_id, int):
            continue
        parsed[slide_id] = slide
    return parsed


def render_project(project_dir: Path, output_dir: str = "svg_output", clean: bool = False) -> list[Path]:
    project_dir = project_dir.resolve()
    blueprint_path = project_dir / "blueprint.json"
    design_path = project_dir / "design_spec.md"
    if not blueprint_path.exists():
        raise FileNotFoundError(f"Missing blueprint: {blueprint_path}")

    blueprint = json.loads(blueprint_path.read_text(encoding="utf-8-sig"))
    schema_issues = validate_blueprint_schema(blueprint)
    if schema_issues:
        first = schema_issues[0]
        raise ValueError(f"{first.path} {first.code}: {first.message}")
    slides = blueprint.get("slides")
    if not isinstance(slides, list):
        raise ValueError("blueprint.json must contain a slides array")

    out_dir = project_dir / output_dir
    if clean and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    renderer = LayoutRenderer(Theme.from_design_spec(design_path))
    slide_plan = _load_slide_plan_metadata(project_dir)
    written: list[Path] = []
    for index, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            raise ValueError(f"Slide {index} must be an object")
        slide_id = int(slide.get("id") or index)
        enriched_slide = dict(slide)
        raw_content = slide.get("content")
        if isinstance(raw_content, dict):
            enriched_content = dict(raw_content)
        else:
            enriched_content = {}
        slide_plan_meta = slide_plan.get(slide_id)
        if isinstance(slide_plan_meta, dict):
            blocks = slide_plan_meta.get("blocks")
            if isinstance(blocks, list):
                enriched_content["__slot_blocks__"] = blocks
            layout_objective = slide_plan_meta.get("layout_objective")
            if isinstance(layout_objective, str) and layout_objective.strip():
                enriched_content["__layout_objective__"] = layout_objective.strip()
        enriched_slide["content"] = enriched_content
        svg = renderer.render(enriched_slide)
        path = out_dir / f"slide_{slide_id:02d}.svg"
        path.write_text(svg, encoding="utf-8")
        written.append(path)
        print(f"Wrote {path}")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render AI-PPT blueprint.json into SVG slides.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    parser.add_argument("--output-dir", default="svg_output", help="Relative output directory inside the project.")
    parser.add_argument("--clean", action="store_true", help="Delete the output directory before rendering.")
    args = parser.parse_args(argv)

    try:
        render_project(args.project_dir, args.output_dir, args.clean)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
