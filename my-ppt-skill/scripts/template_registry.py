#!/usr/bin/env python3
"""Centralized authoritative template registry for layout templates."""

from __future__ import annotations

import json
import re
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPTS_DIR.parent
AUTHORITY_LAYOUTS_DIR = SKILL_DIR / "ppt-ai-core" / "templates" / "layouts"
AUTHORITY_LAYOUTS_INDEX_PATH = AUTHORITY_LAYOUTS_DIR / "layouts_index.json"

_TEMPLATE_ID_RE = re.compile(r"^[A-Za-z0-9_.\-\u4e00-\u9fff]+$")


def _read_authority_layout_map() -> dict[str, object]:
    if not AUTHORITY_LAYOUTS_INDEX_PATH.is_file():
        raise FileNotFoundError(
            "Authority layouts index not found: "
            f"{AUTHORITY_LAYOUTS_INDEX_PATH}"
        )
    payload = json.loads(AUTHORITY_LAYOUTS_INDEX_PATH.read_text(encoding="utf-8"))
    layouts = payload.get("layouts") if isinstance(payload, dict) else None
    if not isinstance(layouts, dict):
        raise ValueError(
            "Invalid layouts index: missing 'layouts' object in "
            f"{AUTHORITY_LAYOUTS_INDEX_PATH}"
        )
    return layouts


def _validate_template_id(template_id: str) -> str:
    candidate = str(template_id).strip()
    if not candidate:
        raise ValueError("Template id must not be empty")
    if "/" in candidate or "\\" in candidate or ".." in candidate:
        raise ValueError(f"Illegal template id: {template_id!r}")
    if not _TEMPLATE_ID_RE.fullmatch(candidate):
        raise ValueError(f"Illegal template id: {template_id!r}")
    return candidate


def list_layout_templates() -> list[dict]:
    """Return layout templates from the authoritative ppt-ai-core source."""
    layouts = _read_authority_layout_map()
    result: list[dict] = []
    for template_id in sorted(str(key) for key in layouts.keys()):
        path = AUTHORITY_LAYOUTS_DIR / template_id
        result.append(
            {
                "id": template_id,
                "source": "ppt-ai-core",
                "path": f"ppt-ai-core/templates/layouts/{template_id}",
                "has_design_spec": (path / "design_spec.md").is_file(),
                "has_layouts_index": (path / "layouts_index.json").is_file(),
            }
        )
    return result


def resolve_layout_template(template_id: str) -> Path:
    """Resolve a template id to the authoritative ppt-ai-core layout path."""
    candidate = _validate_template_id(template_id)
    templates = list_layout_templates()
    canon_map = {item["id"].lower(): item["id"] for item in templates}
    canon_id = canon_map.get(candidate.lower())
    if not canon_id:
        sample = ", ".join(sorted(canon_map.values())[:12])
        tail = "" if len(canon_map) <= 12 else ", ..."
        raise FileNotFoundError(
            f"Unknown template id: {template_id!r}. Available examples: {sample}{tail}"
        )

    resolved = (AUTHORITY_LAYOUTS_DIR / canon_id).resolve()
    root = AUTHORITY_LAYOUTS_DIR.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Resolved path escapes authority root: {resolved}") from exc

    if not resolved.is_dir():
        raise FileNotFoundError(f"Template directory missing: {resolved}")
    return resolved
