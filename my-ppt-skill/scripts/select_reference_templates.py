#!/usr/bin/env python3
"""Select reference templates for a PPT-AI-Assistant project.

Inputs:
- projects/<project_name>/clarification_brief.json
- projects/<project_name>/design_spec.md
- templates/template_catalog.json

Output:
- projects/<project_name>/reference_pack.json

This command only writes reference metadata. It does not generate SVG and does
not call render_svg.py.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from template_catalog import DEFAULT_MAX_TEMPLATES, build_reference_pack_from_catalog

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_TEMPLATE_CATALOG = SKILL_DIR / "templates" / "template_catalog.json"


def _required_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {label}: {path}")


def select_reference_templates(
    project_dir: Path,
    *,
    catalog_path: Path | None = None,
    mode: str | None = None,
    max_templates: int = DEFAULT_MAX_TEMPLATES,
) -> Path:
    """Write reference_pack.json and return its path."""
    project_dir = project_dir.resolve()
    if not project_dir.is_dir():
        raise FileNotFoundError(f"Project directory not found: {project_dir}")

    catalog = (catalog_path or DEFAULT_TEMPLATE_CATALOG).resolve()
    _required_file(project_dir / "clarification_brief.json", "clarification_brief.json")
    _required_file(project_dir / "design_spec.md", "design_spec.md")
    _required_file(catalog, "template_catalog.json")

    pack = build_reference_pack_from_catalog(
        project_dir,
        catalog,
        requested_mode=mode,
        max_templates=max_templates,
    )
    out_path = project_dir / "reference_pack.json"
    out_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select 1-3 reference templates for a project.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    parser.add_argument("--catalog", type=Path, help="Path to template_catalog.json.")
    parser.add_argument(
        "--mode",
        choices=["hybrid", "template-guided", "free-design"],
        help="Override retrieval mode. Defaults to project template_preference, then hybrid.",
    )
    parser.add_argument(
        "--max-templates",
        type=int,
        default=DEFAULT_MAX_TEMPLATES,
        help="Maximum selected templates. Values above 3 are capped to 3.",
    )
    args = parser.parse_args(argv)

    try:
        out_path = select_reference_templates(
            args.project_dir,
            catalog_path=args.catalog,
            mode=args.mode,
            max_templates=args.max_templates,
        )
        payload = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"error: {exc}")
        return 1

    references = payload.get("references")
    count = len(references) if isinstance(references, list) else 0
    print(f"reference_pack: {out_path}")
    print(f"mode: {payload.get('mode')}")
    print(f"references: {count}")
    print(f"requires_style_drafts: {payload.get('requires_style_drafts')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
