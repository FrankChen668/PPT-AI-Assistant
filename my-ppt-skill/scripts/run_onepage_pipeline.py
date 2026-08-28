#!/usr/bin/env python3
"""[experimental] Run one-click pipeline for one-page PPT projects.

Flow:
1) route_style_profile
2) generate_art_direction
3) ensure style draft route is selected when required
4) generate_slide_plan
5) run authoring/release gates
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = SCRIPT_DIR.parent
EXPERIMENTAL_LABEL = "experimental"


@dataclass
class StyleDraftSelection:
    required: bool
    selected: bool
    selected_template: str | None
    selected_draft_id: str | None


def _project_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    return (Path.cwd() / path).resolve()


def _run(cmd: list[str]) -> int:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=False, cwd=WORKSPACE_DIR).returncode


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ensure_style_draft_selected(
    project_dir: Path,
    *,
    auto_select_first: bool,
    selected_draft_id: str | None,
    selected_template: str | None,
) -> StyleDraftSelection:
    style_route_path = project_dir / "style_route.json"
    if not style_route_path.exists():
        return StyleDraftSelection(False, False, None, None)

    style_route = _load_json(style_route_path)
    required = bool(style_route.get("requires_style_drafts", False))
    if not required:
        return StyleDraftSelection(False, False, None, None)

    drafts_path = project_dir / "style_drafts.json"
    if not drafts_path.exists():
        raise RuntimeError("style_route requires drafts, but style_drafts.json is missing.")

    payload = _load_json(drafts_path)
    drafts = payload.get("drafts")
    if not isinstance(drafts, list) or not drafts:
        raise RuntimeError("style_route requires drafts, but style_drafts.json has no drafts[].")

    draft_index: dict[str, str] = {}
    for item in drafts:
        if not isinstance(item, dict):
            continue
        draft_id = str(item.get("draft_id") or "").strip()
        template_id = str(item.get("template_id") or "").strip()
        if draft_id and template_id:
            draft_index[draft_id] = template_id

    if not draft_index:
        raise RuntimeError("style_drafts.json contains no valid draft_id/template_id pairs.")

    existing_template = str(payload.get("selected_template") or "").strip()
    existing_draft_id = str(payload.get("selected_draft_id") or "").strip()

    chosen_draft_id = (selected_draft_id or existing_draft_id).strip()
    chosen_template = (selected_template or existing_template).strip()

    if chosen_draft_id and chosen_draft_id not in draft_index:
        raise RuntimeError(f"selected_draft_id={chosen_draft_id!r} not found in style_drafts.json.")

    if not chosen_template and chosen_draft_id:
        chosen_template = draft_index[chosen_draft_id]

    if chosen_template and chosen_template not in set(draft_index.values()):
        raise RuntimeError(f"selected_template={chosen_template!r} not found in style_drafts.json drafts[].")

    if chosen_draft_id and chosen_template and draft_index.get(chosen_draft_id) != chosen_template:
        raise RuntimeError(
            "selected_draft_id and selected_template mismatch: "
            f"{chosen_draft_id!r} -> {draft_index.get(chosen_draft_id)!r}, got {chosen_template!r}."
        )

    if not chosen_draft_id and not chosen_template:
        if not auto_select_first:
            raise RuntimeError(
                "Low-confidence route requires draft selection. "
                "Provide --selected-draft-id/--selected-template or enable auto selection."
            )
        first_draft_id = next(iter(draft_index.keys()))
        chosen_draft_id = first_draft_id
        chosen_template = draft_index[first_draft_id]

    if not chosen_draft_id and chosen_template:
        for draft_id, template_id in draft_index.items():
            if template_id == chosen_template:
                chosen_draft_id = draft_id
                break

    payload["selected_draft_id"] = chosen_draft_id or None
    payload["selected_template"] = chosen_template or None
    _write_json(drafts_path, payload)

    return StyleDraftSelection(
        required=True,
        selected=bool(chosen_template or chosen_draft_id),
        selected_template=chosen_template or None,
        selected_draft_id=chosen_draft_id or None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one-click style->art-direction->build pipeline.")
    parser.add_argument("project_dir", help="Project path, usually projects/<project_name>.")
    parser.add_argument(
        "--mode",
        choices=["dev-fast", "release-safe", "premium"],
        default="release-safe",
        help="Pipeline strictness mode for the final gate.",
    )
    parser.add_argument(
        "--overwrite-artifacts",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Overwrite art_direction/reference_pack/slide_visual_plan/style_drafts by default.",
    )
    parser.add_argument(
        "--overwrite-slide-plan",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Overwrite slide_plan.json by default.",
    )
    parser.add_argument(
        "--auto-select-first-draft",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Auto-select first draft when style_route requires drafts and none selected.",
    )
    parser.add_argument("--selected-draft-id", help="Explicit draft_id to select in style_drafts.json.")
    parser.add_argument("--selected-template", help="Explicit template_id to select in style_drafts.json.")
    parser.add_argument(
        "--layout-exploration",
        choices=["auto", "on", "off"],
        default="auto",
        help="Dual-candidate exploration policy (auto: on for release-safe/premium, off for dev-fast).",
    )
    parser.add_argument("--skip-authoring", action="store_true", help="Skip authoring-phase build gate.")
    parser.add_argument("--slide", type=int, help="Single-slide QA scope in dev-fast mode.")
    parser.add_argument("--snapshots", action="store_true", help="Enable snapshots in dev-fast mode.")
    args = parser.parse_args(argv)
    print(
        "[experimental] run_onepage_pipeline is a research orchestrator; use scripts/run_mode.py for mainline delivery."
    )

    project_dir = _project_path(args.project_dir)
    if not project_dir.exists():
        print(f"error: project_dir not found: {project_dir}")
        return 2

    py = sys.executable
    route_cmd = [py, str(SCRIPT_DIR / "route_style_profile.py"), str(project_dir)]
    if _run(route_cmd) != 0:
        return 1

    resolved_layout_exploration = args.layout_exploration
    if resolved_layout_exploration == "auto":
        resolved_layout_exploration = "on" if args.mode in {"release-safe", "premium"} else "off"
    art_cmd = [
        py,
        str(SCRIPT_DIR / "generate_art_direction.py"),
        str(project_dir),
        "--layout-exploration",
        resolved_layout_exploration,
        "--candidate-count",
        "2",
    ]
    if args.overwrite_artifacts:
        art_cmd.append("--overwrite")
    if _run(art_cmd) != 0:
        return 1

    try:
        selection = _ensure_style_draft_selected(
            project_dir,
            auto_select_first=args.auto_select_first_draft,
            selected_draft_id=args.selected_draft_id,
            selected_template=args.selected_template,
        )
    except Exception as exc:
        print(f"error: {exc}")
        return 1

    if selection.required and selection.selected:
        print(
            "Selected style draft route: "
            f"draft_id={selection.selected_draft_id or 'n/a'}, "
            f"template={selection.selected_template or 'n/a'}"
        )

    slide_plan_cmd = [py, str(SCRIPT_DIR / "generate_slide_plan.py"), str(project_dir)]
    if args.overwrite_slide_plan:
        slide_plan_cmd.append("--overwrite")
    if _run(slide_plan_cmd) != 0:
        return 1

    if not args.skip_authoring:
        authoring_cmd = [
            py,
            str(SCRIPT_DIR / "build_project.py"),
            str(project_dir),
            "--phase",
            "authoring",
            "--skip-render",
            "--enable-layout-lint",
            "--safe-area-profile",
            "presentation",
        ]
        if _run(authoring_cmd) != 0:
            return 1

    run_mode_cmd = [py, str(SCRIPT_DIR / "run_mode.py"), args.mode, str(project_dir)]
    if args.mode == "dev-fast":
        if args.slide is not None:
            run_mode_cmd += ["--slide", str(args.slide)]
        if args.snapshots:
            run_mode_cmd.append("--snapshots")
    return _run(run_mode_cmd)


if __name__ == "__main__":
    raise SystemExit(main())
