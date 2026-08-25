"""Validation helpers for low-confidence style draft selection gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_style_draft_selection(project_dir: Path, *, min_drafts: int = 2) -> list[str]:
    """Return blocking issues for low-confidence style draft selection.

    If style routing does not explicitly require drafts, no issue is reported.
    """
    style_route_path = project_dir / "style_route.json"
    if not style_route_path.exists():
        return []
    try:
        style_route = _load_json(style_route_path)
    except Exception as exc:
        return [f"invalid style_route.json: {exc}"]
    if not isinstance(style_route, dict):
        return ["invalid style_route.json: root must be object"]

    if not bool(style_route.get("requires_style_drafts", False)):
        return []

    style_drafts_path = project_dir / "style_drafts.json"
    if not style_drafts_path.exists():
        return ["missing style_drafts.json"]
    try:
        drafts_payload = _load_json(style_drafts_path)
    except Exception as exc:
        return [f"invalid style_drafts.json: {exc}"]
    if not isinstance(drafts_payload, dict):
        return ["invalid style_drafts.json: root must be object"]

    issues: list[str] = []
    drafts = drafts_payload.get("drafts")
    if not isinstance(drafts, list):
        issues.append("style_drafts.json has no drafts[]")
        drafts = []
    elif len(drafts) < max(1, int(min_drafts)):
        issues.append(f"style_drafts.json requires at least {int(min_drafts)} drafts[] entries")

    draft_index: dict[str, str] = {}
    for item in drafts:
        if not isinstance(item, dict):
            continue
        draft_id = str(item.get("draft_id") or "").strip()
        template_id = str(item.get("template_id") or "").strip()
        if draft_id and template_id:
            draft_index[draft_id] = template_id
    if len(draft_index) < max(1, int(min_drafts)):
        issues.append(
            f"style_drafts.json must contain at least {int(min_drafts)} valid draft_id/template_id pairs"
        )

    selected_template = str(drafts_payload.get("selected_template") or "").strip()
    selected_draft_id = str(drafts_payload.get("selected_draft_id") or "").strip()
    selected_from_draft = draft_index.get(selected_draft_id, "")

    if not selected_template and not selected_draft_id:
        issues.append("style_route requires style drafts, but no selected_template/selected_draft_id is set")
    else:
        if selected_draft_id and selected_draft_id not in draft_index:
            issues.append(f"selected_draft_id={selected_draft_id!r} not found in drafts[]")
        if selected_template and selected_template not in set(draft_index.values()):
            issues.append(f"selected_template={selected_template!r} not found in drafts[].template_id")
        if selected_draft_id and selected_template and selected_from_draft and selected_from_draft != selected_template:
            issues.append(
                f"selected_draft_id={selected_draft_id!r} maps to template {selected_from_draft!r}, "
                f"but selected_template is {selected_template!r}"
            )

    deduped: list[str] = []
    seen: set[str] = set()
    for issue in issues:
        if issue in seen:
            continue
        seen.add(issue)
        deduped.append(issue)
    return deduped


def ensure_style_draft_selection(
    project_dir: Path,
    *,
    auto_select_first: bool = True,
) -> str | None:
    """Ensure low-confidence style routes have a selected draft/template.

    Returns a short note when this function auto-selected a route.
    Returns ``None`` when no action is needed or not applicable.
    """
    style_route_path = project_dir / "style_route.json"
    if not style_route_path.exists():
        return None

    try:
        style_route = _load_json(style_route_path)
    except Exception:
        return None
    if not isinstance(style_route, dict):
        return None
    if not bool(style_route.get("requires_style_drafts", False)):
        return None

    style_drafts_path = project_dir / "style_drafts.json"
    if not style_drafts_path.exists():
        return None
    try:
        drafts_payload = _load_json(style_drafts_path)
    except Exception:
        return None
    if not isinstance(drafts_payload, dict):
        return None

    selected_template = str(drafts_payload.get("selected_template") or "").strip()
    selected_draft_id = str(drafts_payload.get("selected_draft_id") or "").strip()
    if selected_template or selected_draft_id:
        return None

    drafts = drafts_payload.get("drafts")
    if not isinstance(drafts, list) or not drafts:
        return None

    draft_index: dict[str, str] = {}
    for item in drafts:
        if not isinstance(item, dict):
            continue
        draft_id = str(item.get("draft_id") or "").strip()
        template_id = str(item.get("template_id") or "").strip()
        if draft_id and template_id:
            draft_index[draft_id] = template_id
    if not draft_index:
        return None

    if not auto_select_first:
        return None

    chosen_draft_id = next(iter(draft_index))
    chosen_template = draft_index[chosen_draft_id]
    drafts_payload["selected_draft_id"] = chosen_draft_id
    drafts_payload["selected_template"] = chosen_template
    _write_json(style_drafts_path, drafts_payload)
    return (
        "Auto-selected style draft route for low-confidence style routing: "
        f"draft_id={chosen_draft_id}, template={chosen_template}"
    )
