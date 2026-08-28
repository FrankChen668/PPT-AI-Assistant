#!/usr/bin/env python3
"""Prompt pattern catalog for critical absorption of external prompt libraries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_PATTERN_CATALOG = SKILL_DIR / "references" / "prompt-pattern-catalog.json"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Catalog root must be object: {path}")
    return payload


def _patterns(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    raw = payload.get("patterns")
    if not isinstance(raw, list):
        raise ValueError(f"Catalog patterns must be a list: {path}")
    patterns = [item for item in raw if isinstance(item, dict)]
    if not patterns:
        raise ValueError(f"Catalog has no valid patterns: {path}")
    return patterns


def resolve_prompt_pattern(layout_tag: str, catalog_path: Path | None = None) -> dict[str, Any]:
    path = catalog_path.resolve() if catalog_path else DEFAULT_PATTERN_CATALOG.resolve()
    patterns = _patterns(path)
    tag = (layout_tag or "").strip()
    fallback = patterns[-1]

    for pattern in patterns:
        applies = pattern.get("applies_to_tags")
        if isinstance(applies, list) and tag in applies:
            return pattern

    normalized = tag.lower()
    for pattern in patterns:
        pid = str(pattern.get("pattern_id", "")).lower()
        if "strategy" in normalized and pid == "strategy_map":
            return pattern
        if ("architecture" in normalized or "system" in normalized) and pid == "architecture_system":
            return pattern
        if ("data-" in normalized or "chart-" in normalized) and pid == "value_case":
            return pattern
        if ("timeline" in normalized or "flow" in normalized) and pid == "roadmap_execution":
            return pattern
        if ("risk" in normalized or "governance" in normalized) and pid == "risk_governance":
            return pattern
        if ("grid-" in normalized or "content-" in normalized) and pid == "default_consulting":
            return pattern

    return fallback

