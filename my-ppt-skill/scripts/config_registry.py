#!/usr/bin/env python3
"""Mainline configuration registry seam.

Mainline scripts should query canvas specs and SVG forbidden rules from here.
Vendored/upstream compatibility domains (for example `scripts/ppt_master/*`
or `ppt-ai-core/*`) may keep their local config shapes during migration.
"""

from __future__ import annotations

from typing import Any

from ppt_ai_core_standards import (
    CANVAS_SPECS,
    FORBIDDEN_ATTRIBUTES,
    FORBIDDEN_ELEMENTS,
    FORBIDDEN_PATTERNS,
    CanvasSpec,
)
from ppt_ai_core_standards import (
    get_canvas_spec as _get_canvas_spec,
)


def get_canvas_spec(canvas_key: str | None = None) -> CanvasSpec:
    """Return normalized canvas spec from mainline SSOT."""
    return _get_canvas_spec(canvas_key)


def list_canvas_specs() -> list[CanvasSpec]:
    """List all known canvas specs from mainline SSOT."""
    return list(CANVAS_SPECS.values())


def get_svg_forbidden_rules() -> dict[str, Any]:
    """Return forbidden SVG compatibility rules for mainline checkers."""
    return {
        "elements": set(FORBIDDEN_ELEMENTS),
        "attributes": set(FORBIDDEN_ATTRIBUTES),
        "patterns": tuple(FORBIDDEN_PATTERNS),
    }
